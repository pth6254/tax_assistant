"""
services/chat_service.py — RAG 채팅 비즈니스 로직
질문 세목 분류 → 벡터 검색 → 메모리 조회 → Ollama 답변 → 메모리 저장.
"""
import asyncio
import json
import logging
import re
import time
import uuid as _uuid
from typing import AsyncGenerator

import httpx

from config import CHAT_MODEL, MEMORY_TURNS, OLLAMA_BASE_URL, TOP_K, TAVILY_API_KEY
from app.database import get_pool
from app.services.law.hybrid_search_service import (
    format_hybrid_context,
    hybrid_search_multi,
)

logger = logging.getLogger(__name__)

_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"

_TAVILY_URL = "https://api.tavily.com/search"

# DB 최고 유사도가 이 값 미만일 때만 웹 검색 실행
_WEB_SEARCH_THRESHOLD = 0.65

# 세목 키워드 매핑
_LAW_KW: dict[str, list[str]] = {
    "소득세법":              ["소득세", "종합소득", "원천징수", "근로소득", "사업소득", "기타소득", "양도소득"],
    "부가가치세법":          ["부가세", "부가가치세", "vat", "간이과세", "일반과세", "매입세액", "매출세액"],
    "법인세법":              ["법인세", "법인소득", "법인 세금"],
    "상속세및증여세법":      ["상속세", "증여세", "상속", "증여", "유산"],
    "지방세법":              ["지방세", "취득세", "재산세", "주민세", "자동차세", "등록면허세"],
    "조세특례제한법":        ["조세특례", "감면", "공제", "세액공제", "조특법", "세제혜택"],
    "국세기본법":            ["국세기본", "가산세", "경정청구", "불복", "과세전적부심사"],
    "종합부동산세법":        ["종합부동산세", "종부세"],
    "개별소비세법":          ["개별소비세", "특별소비세"],
    "교통에너지환경세법":    ["교통에너지환경세", "교통세"],
    "주세법":                ["주세", "주류세"],
    "인지세법":              ["인지세"],
    "농어촌특별세법":        ["농어촌특별세", "농특세"],
    "교육세법":              ["교육세"],
    "증권거래세법":          ["증권거래세"],
    "국세징수법":            ["국세징수", "체납", "압류", "공매"],
    "조세범처벌법":          ["조세범", "세금포탈", "조세포탈"],
    "국제조세조정에관한법률": ["국제조세", "이전가격", "조세조약", "해외금융계좌"],
    "관세법":                ["관세", "수입세", "수출입", "관세청"],
    "지방세기본법":          ["지방세기본", "지방세 불복", "지방세 경정"],
    "지방세특례제한법":      ["지방세특례", "지방세 감면"],
    "지방세징수법":          ["지방세징수", "지방세 체납"],
}



async def detect_law_name(query: str) -> str:
    """질문에서 세목명 추출. 불명확하면 'ALL' 반환."""
    q = query.lower()
    for law, kws in _LAW_KW.items():
        if any(kw in q for kw in kws):
            return law

    # 키워드 매핑 실패 시 Ollama로 판단
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _CHAT_URL,
                json={
                    "model": CHAT_MODEL,
                    "messages": [{"role": "user", "content": (
                        "다음 질문이 어떤 세법과 관련 있는지 하나만 답하세요.\n"
                        "후보: 소득세법, 부가가치세법, 법인세법, 상속세및증여세법, "
                        "지방세법, 조세특례제한법, 국세기본법, ALL\n"
                        f"질문: {query}\n오직 세법 이름 하나만 출력하세요."
                    )}],
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 20,
                        "think": False,
                    },
                },
            )
            resp.raise_for_status()
            result = resp.json()["message"]["content"].strip()
            return result if result in _LAW_KW else "ALL"
    except Exception:
        return "ALL"



async def _fetch_history(session_id: _uuid.UUID) -> list[dict]:
    """Postgres에서 최근 대화 메모리 조회."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT message FROM chat_logs
               WHERE session_id = $1
               ORDER BY created_at DESC LIMIT $2""",
            session_id, MEMORY_TURNS * 2,
        )
    history = []
    for r in reversed(rows):
        msg = r["message"]
        history.append(json.loads(msg) if isinstance(msg, str) else msg)
    return history


async def _save_history(
    session_id: _uuid.UUID,
    query: str,
    answer: str,
) -> None:
    """대화 턴을 chat_logs에 저장."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO chat_logs (session_id, message) VALUES ($1, $2)",
            [
                (session_id, json.dumps({"role": "user",      "content": query},  ensure_ascii=False)),
                (session_id, json.dumps({"role": "assistant", "content": answer}, ensure_ascii=False)),
            ],
        )

# 채팅 답변 제시

# ── 단일 답변 프롬프트 (RAG 컨텍스트 + 웹 검색 결과 통합) ────────
_COMBINED_PROMPT = (
    "당신은 대한민국 세무 법령 전문 AI 어시스턴트입니다.\n"
    "검색된 자료의 출처 유형(source_type)에 따라 아래 우선순위를 엄격히 적용하세요.\n\n"

    "## 자료 출처 우선순위\n"
    "| 우선순위 | source_type     | 설명                          | 용도                     |\n"
    "|----------|-----------------|-------------------------------|---------------------------|\n"
    "| 1        | law             | 공식 법률 조문 (법령)         | 최우선 근거, 반드시 인용  |\n"
    "| 2        | regulation      | 대통령령 (시행령)             | 법률 요건의 세부 기준     |\n"
    "| 3        | rule            | 총리령·부령 (시행규칙)        | 절차·서식 세부 사항       |\n"
    "| 4        | practice_pdf    | 집행기준·실무자료 PDF         | 해설·사례 보완, 구속력 없음 |\n"
    "| 5        | user_pdf        | 사용자 업로드 PDF             | 참고용, 법적 효력 없음    |\n"
    "| 6        | 웹 검색 결과    | 최신 인터넷 자료              | DB 미수록 최신 해석·예규만 |\n\n"

    "## 근거 사용 규칙\n"
    "1. 공식 법령 조문(law)을 최우선 근거로 사용한다.\n"
    "2. 시행령(regulation)·시행규칙(rule)은 법률의 세부 요건 보완 자료로 사용한다.\n"
    "3. PDF 실무자료(practice_pdf, user_pdf)는 해설 또는 사례 보완으로만 사용한다.\n"
    "4. 웹 검색 결과는 DB가 다루지 못한 최신 해석·예규 보완에만 사용한다.\n"
    "5. 법령(law)과 다른 자료가 충돌하면 법령을 우선한다.\n"
    "6. 제공된 자료에서 명확한 근거를 찾지 못한 경우, "
    "추정하거나 일반론을 제시하지 말고 "
    "'제공된 자료에서 명확한 근거를 찾지 못했습니다'라고 명시한다.\n"
    "7. 세무 리스크가 있는 판단은 반드시 '전문가 확인 권장'을 표시한다.\n\n"

    "## 세법 일반 원칙\n"
    "- 특별법 우선: 조세특례제한법이 일반 세법보다 우선 적용\n"
    "- 신법 우선: 같은 위계의 법령은 최신 개정령이 우선\n"
    "- 엄격 해석: 비과세·감면 요건은 명확한 조문 근거가 있어야 함\n\n"

    "## 출력 형식\n"
    "## 1. 💡 결론\n"
    "## 2. 📖 상세 설명\n"
    "## 3. ⚖️ 법적 근거\n"
    "## 4. ⚡ 실무 주의사항\n\n"
    "## 📋 근거 출처 목록\n"
    "(아래 형식으로 인용한 자료를 모두 나열)\n"
    "[법률] 법령명 제X조 - 조문제목\n"
    "[시행령] 법령명 시행령 제X조\n"
    "[시행규칙] 법령명 시행규칙 제X조\n"
    "[웹출처] URL 또는 자료명\n"
    "[실무자료] 출처명 (구속력 없음)\n\n"

    "규칙:\n"
    "- 항상 마크다운으로 작성\n"
    "- 법적 근거는 조문 번호까지 명시\n"
    "- 근거 없는 내용은 절대 추정하지 말 것\n"
    "- <think> 태그 내용은 출력하지 말 것\n"
)

# ── 멀티쿼리 생성 프롬프트 ────────────────────────────
_MULTI_QUERY_PROMPT = (
    "한국 세무 법령 검색을 위한 검색어 3개를 서로 다른 관점으로 생성하라.\n\n"
    "## 관점\n"
    "1. 법령/조문 관점: 관련 법령명·조문 번호·법령 용어 중심\n"
    "2. 요건/대상 관점: 적용 대상·요건·예외사항 중심\n"
    "3. 계산/절차 관점: 세액 산출·신고 방법·실무 절차 중심\n\n"
    "## 규칙\n"
    "- 구어체를 법령 용어로 변환 (예: '알바비' → '인적용역 원천징수')\n"
    "- 각 검색어는 50자 이내 키워드 나열\n"
    "- JSON 배열만 출력: [\"검색어1\", \"검색어2\", \"검색어3\"]\n"
    "- <think> 태그 내용은 출력하지 말 것\n"
)

# ── 세목 분류 + 쿼리 생성 통합 프롬프트 ─────────────────
_COMBINED_CLASSIFY_PROMPT = (
    "한국 세무 법령 질문을 분석하여 JSON만 출력하라.\n\n"
    "1. law: 관련 세법 하나\n"
    "   후보: 소득세법, 부가가치세법, 법인세법, 상속세및증여세법,\n"
    "         지방세법, 조세특례제한법, 국세기본법, ALL\n"
    "2. queries: 서로 다른 관점의 검색어 3개 (각 50자 이내)\n"
    "   - 법령/조문 관점, 요건/대상 관점, 계산/절차 관점\n"
    "   - 구어체 → 법령 용어 변환\n\n"
    '출력 형식 (JSON만, 다른 내용 없음):\n'
    '{"law": "소득세법", "queries": ["검색어1", "검색어2", "검색어3"]}\n'
    "- <think> 태그 내용은 출력하지 말 것\n"
)

_OLLAMA_OPTIONS             = {"temperature": 0.3, "num_predict": 500,  "num_ctx": 4096, "think": False}
_OLLAMA_OPTIONS_STREAM      = {"temperature": 0.3, "num_predict": -1,   "num_ctx": 8192, "think": False}
_OLLAMA_OPTIONS_MULTI_QUERY = {"temperature": 0.0, "num_predict": 150,  "num_ctx": 2048, "think": False}


async def _call_ollama(
    messages: list[dict],
    temperature: float = 0.3,
    options: dict | None = None,
) -> str:
    """Ollama 비스트리밍 호출."""
    merged_options = {**(options or _OLLAMA_OPTIONS), "temperature": temperature}
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            _CHAT_URL,
            json={
                "model":    CHAT_MODEL,
                "messages": messages,
                "stream":   False,
                "options":  merged_options,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _stream_ollama_response(
    messages: list[dict],
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    Ollama 스트리밍 호출. 토큰 청크를 yield한다.
    <think>...</think> 블록은 필터링하여 출력하지 않는다.
    num_predict 제한으로 </think>가 미출력된 경우도 처리한다.
    """
    buf = ""
    past_think = False

    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST",
            _CHAT_URL,
            json={
                "model":    CHAT_MODEL,
                "messages": messages,
                "stream":   True,
                "options":  {**_OLLAMA_OPTIONS_STREAM, "temperature": temperature},
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue

                chunk = data.get("message", {}).get("content", "")

                if past_think:
                    if chunk:
                        yield chunk
                else:
                    buf += chunk
                    if "</think>" in buf:
                        _, after = buf.split("</think>", 1)
                        past_think = True
                        buf = ""
                        if after:
                            yield after
                    elif "<think>" not in buf and len(buf) > 30:
                        past_think = True
                        yield buf
                        buf = ""

                if data.get("done"):
                    break

    # </think> 없이 스트림 종료된 경우 (<think> 블록 강제 제거 후 출력)
    if buf:
        if "<think>" in buf:
            # </think> 미출력 → <think> 이후 내용을 답변으로 사용
            after_think = buf.split("<think>", 1)[-1]
            if after_think.strip():
                logger.warning("[STREAM] </think> 미출력 — 버퍼 내용을 답변으로 사용 (%d자)", len(after_think))
                yield after_think
        else:
            yield buf


async def _tavily_search(queries: list[str]) -> str:
    """Tavily 웹 검색 — 최대 3개 쿼리를 병렬 실행."""
    _DOMAINS = ["nts.go.kr", "law.go.kr", "moef.go.kr"]

    async def _fetch_one(client: httpx.AsyncClient, query: str) -> list[str]:
        try:
            resp = await client.post(
                _TAVILY_URL,
                headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
                json={
                    "query":           query,
                    "search_depth":    "advanced",
                    "max_results":     3,
                    "include_domains": _DOMAINS,
                },
            )
            resp.raise_for_status()
            return [
                f"[출처: {r.get('url','?')}]\n{r.get('content','')[:500]}"
                for r in resp.json().get("results", [])
            ]
        except Exception:
            return []

    async with httpx.AsyncClient(timeout=30.0) as client:
        nested = await asyncio.gather(*[_fetch_one(client, q) for q in queries[:3]])

    results = [item for sub in nested for item in sub]
    return "\n\n---\n\n".join(results) if results else "웹 검색 결과 없음"


async def generate_search_queries(query: str) -> list[str]:
    """질문으로부터 다각도 검색 쿼리 3개 생성. 실패 시 원본만 반환."""
    try:
        raw = await _call_ollama(
            [
                {"role": "system", "content": _MULTI_QUERY_PROMPT},
                {"role": "user",   "content": query},
            ],
            temperature=0.0,
            options=_OLLAMA_OPTIONS_MULTI_QUERY,
        )
        text  = raw.split("</think>")[-1].strip()
        fence = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
        candidate = fence.group(1).strip() if fence else text
        match = re.search(r"\[[\s\S]*?\]", candidate)
        if match:
            queries = json.loads(match.group(0))
            if isinstance(queries, list):
                result = [q for q in queries if isinstance(q, str) and q.strip()][:3]
                if result:
                    logger.info("[MULTI-QUERY] %d개 생성: %s", len(result), result)
                    return result
    except Exception as e:
        logger.warning("[MULTI-QUERY] 생성 실패 — 원본 사용: %s", e)
    return [query]


async def _classify_and_generate_queries(query: str) -> tuple[str, list[str]]:
    """세목 분류 + 검색 쿼리 생성을 1회 LLM 호출로 처리. 실패 시 키워드 분류 + 원본 쿼리 반환."""
    q_lower = query.lower()
    keyword_law = "ALL"
    for law, kws in _LAW_KW.items():
        if any(kw in q_lower for kw in kws):
            keyword_law = law
            break

    try:
        raw = await _call_ollama(
            [
                {"role": "system", "content": _COMBINED_CLASSIFY_PROMPT},
                {"role": "user",   "content": query},
            ],
            temperature=0.0,
            options=_OLLAMA_OPTIONS_MULTI_QUERY,
        )
        text = raw.split("</think>")[-1].strip()
        fence = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
        candidate = fence.group(1).strip() if fence else text
        match = re.search(r"\{[\s\S]*?\}", candidate)
        if match:
            data = json.loads(match.group(0))
            llm_law = data.get("law", "ALL")
            # 키워드로 확정된 세목 우선, 없으면 LLM 판단 사용
            final_law = keyword_law if keyword_law != "ALL" else (
                llm_law if (llm_law in _LAW_KW or llm_law == "ALL") else "ALL"
            )
            queries = data.get("queries", [])
            if isinstance(queries, list):
                clean = [q for q in queries if isinstance(q, str) and q.strip()][:3]
                if clean:
                    logger.info("[CLASSIFY] 세목=%s | 쿼리=%d개: %s", final_law, len(clean), clean)
                    return final_law, clean
    except Exception as e:
        logger.warning("[CLASSIFY] 통합 분류 실패 — 키워드+원본 사용: %s", e)

    return keyword_law, [query]


async def _fetch_rag_and_web_context(
    query: str,
    session_id: _uuid.UUID,
    user_id: str,
) -> tuple[str, str, list[dict]]:
    """
    세목 분류·법령 검색·웹 검색을 수행하고 (context, web_results, history)를 반환한다.
    DB 유사도가 충분하면 웹 검색을 생략하여 불필요한 지연을 제거한다.
    """
    t0 = time.perf_counter()

    (law_filter, search_queries), history = await asyncio.gather(
        _classify_and_generate_queries(query),
        _fetch_history(session_id),
    )
    logger.info("[RAG] 세목=%s | 히스토리=%d턴 | 검색쿼리=%d개", law_filter, len(history) // 2, len(search_queries))

    results = await hybrid_search_multi(search_queries, law_filter, user_id=user_id, original_query=query)
    context = format_hybrid_context(results)
    logger.info("[RAG] 하이브리드 검색 완료 (%.1fs)", time.perf_counter() - t0)

    web_results = "웹 검색 생략"
    if TAVILY_API_KEY:
        top_score = max((r.similarity_score for r in results), default=0.0)
        if top_score < _WEB_SEARCH_THRESHOLD:
            logger.info("[RAG] DB 유사도 낮음(%.2f) — 웹 검색 실행", top_score)
            web_results = await _tavily_search([query])
        else:
            logger.info("[RAG] DB 유사도 충분(%.2f) — 웹 검색 생략", top_score)

    logger.info("[RAG] 준비 단계 총 소요: %.1fs", time.perf_counter() - t0)
    return context, web_results, history


def _build_final_messages(
    query: str,
    context: str,
    web_results: str,
    history: list[dict],
) -> list[dict]:
    """최종 답변용 메시지 목록을 생성한다."""
    messages = [{"role": "system", "content": _COMBINED_PROMPT}]
    messages.extend(history)
    user_content = f"[검색된 세무 법령 자료]\n{context}"
    if web_results and web_results != "웹 검색 생략":
        user_content += f"\n\n[웹 검색 결과]\n{web_results}"
    user_content += f"\n\n[사용자 질문]\n{query}"
    messages.append({"role": "user", "content": user_content})
    return messages


async def process_chat(query: str, user_id: str) -> str:
    """RAG 파이프라인 실행 후 최종 답변을 반환한다 (비스트리밍)."""
    logger.info("[CHAT] 요청 수신: %.40s...", query)
    t0 = time.perf_counter()

    session_id = _uuid.UUID(user_id)
    context, web_results, history = await _fetch_rag_and_web_context(query, session_id, user_id)

    messages = _build_final_messages(query, context, web_results, history)
    answer   = await _call_ollama(messages, temperature=0.3)

    await _save_history(session_id, query, answer)
    logger.info("[CHAT] 응답 완료 — 총 %.1fs | 답변 %d자", time.perf_counter() - t0, len(answer))
    return answer


async def stream_chat_response(
    query: str,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """RAG 파이프라인 실행 후 최종 답변을 토큰 단위로 yield한다 (스트리밍)."""
    logger.info("[STREAM] 요청 수신: %.40s...", query)
    t0 = time.perf_counter()

    session_id = _uuid.UUID(user_id)
    context, web_results, history = await _fetch_rag_and_web_context(query, session_id, user_id)

    messages     = _build_final_messages(query, context, web_results, history)
    full_answer: list[str] = []

    logger.info("[STREAM] 최종 답변 스트리밍 시작")
    async for chunk in _stream_ollama_response(messages, temperature=0.3):
        full_answer.append(chunk)
        yield chunk

    answer = "".join(full_answer)
    await _save_history(session_id, query, answer)
    logger.info("[STREAM] 완료 — 총 %.1fs | 답변 %d자", time.perf_counter() - t0, len(answer))