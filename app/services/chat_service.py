"""
services/chat_service.py — RAG 채팅 비즈니스 로직
질문 세목 분류 → 벡터 검색 → 메모리 조회 → Ollama 답변 → 메모리 저장.
"""
import json
import uuid as _uuid

import httpx

from config import CHAT_MODEL, MEMORY_TURNS, OLLAMA_BASE_URL, TOP_K, TAVILY_API_KEY
from app.database import get_pool
from app.utils.embeddings import embed_texts
from app.services.law.hybrid_search_service import fetch_hybrid_context

_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"

_TAVILY_URL = "https://api.tavily.com/search"

# 세목 키워드 매핑
_LAW_KW: dict[str, list[str]] = {
    "소득세법":         ["소득세", "종합소득", "원천징수", "근로소득", "사업소득", "기타소득"],
    "부가가치세법":     ["부가세", "부가가치세", "vat", "간이과세", "일반과세"],
    "법인세법":         ["법인세", "법인소득"],
    "상속세및증여세법": ["상속세", "증여세", "상속", "증여"],
    "지방세법":         ["지방세", "취득세", "재산세", "주민세"],
    "조세특례제한법":   ["조세특례", "감면", "공제", "세액공제", "조특법"],
    "국세기본법":       ["국세기본", "가산세", "경정청구", "불복"],
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
                    },
                },
            )
            resp.raise_for_status()
            result = resp.json()["message"]["content"].strip()
            return result if result in _LAW_KW else "ALL"
    except Exception:
        return "ALL"


async def _fetch_context(q_emb: list[float], law_filter: str) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM match_documents($1::vector, $2, $3)",
            q_emb, TOP_K, law_filter,
        )
    if not rows:
        return "관련 문서를 찾지 못했습니다."
    
    # ↓ category를 위계 순서로 정렬 후 포맷
    CATEGORY_ORDER = {"법령": 0, "시행령": 1, "시행규칙": 2, "집행기준": 3, "기타": 4}
    
    sorted_rows = sorted(
        rows,
        key=lambda r: CATEGORY_ORDER.get(r['metadata'].get('category', '기타'), 4)
    )
    
    return "\n\n---\n\n".join(
        f"[출처: {r['metadata'].get('source','?')} | "
        f"{r['metadata'].get('law_name','?')} | "
        f"📌 {r['metadata'].get('category','?')}]\n"  # category 추가
        f"{r['content']}"
        for r in sorted_rows
    )


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

# ── 1단계: 자료 검색기 ─────────────────────────────────────────
_RAG_PROMPT = (
    "당신은 대한민국 세무 법령 전문 AI 어시스턴트입니다.\n"
    "검색된 자료의 출처 유형(source_type)에 따라 아래 우선순위를 엄격히 적용하세요.\n\n"

    "## 자료 출처 우선순위\n"
    "| 우선순위 | source_type     | 설명                          | 용도                     |\n"
    "|----------|-----------------|-------------------------------|---------------------------|\n"
    "| 1        | law             | 공식 법률 조문 (법령)         | 최우선 근거, 반드시 인용  |\n"
    "| 2        | regulation      | 대통령령 (시행령)             | 법률 요건의 세부 기준     |\n"
    "| 3        | rule            | 총리령·부령 (시행규칙)        | 절차·서식 세부 사항       |\n"
    "| 4        | practice_pdf    | 집행기준·실무자료 PDF         | 해설·사례 보완, 구속력 없음 |\n"
    "| 5        | user_pdf        | 사용자 업로드 PDF             | 참고용, 법적 효력 없음    |\n\n"

    "## 근거 사용 규칙\n"
    "1. 공식 법령 조문(law)을 최우선 근거로 사용한다.\n"
    "2. 시행령(regulation)·시행규칙(rule)은 법률의 세부 요건 보완 자료로 사용한다.\n"
    "3. PDF 실무자료(practice_pdf, user_pdf)는 해설 또는 사례 보완으로만 사용한다.\n"
    "4. 법령(law)과 PDF 자료가 충돌하면 법령을 우선한다.\n"
    "5. 제공된 자료에서 명확한 근거를 찾지 못한 경우, "
    "추정하거나 일반론을 제시하지 말고 "
    "'제공된 자료에서 명확한 근거를 찾지 못했습니다'라고 명시한다.\n"
    "6. 세무 리스크가 있는 판단은 반드시 '전문가 확인 권장'을 표시한다.\n\n"

    "## 세법 일반 원칙\n"
    "- 특별법 우선: 조세특례제한법이 일반 세법보다 우선 적용\n"
    "- 신법 우선: 같은 위계의 법령은 최신 개정령이 우선\n"
    "- 엄격 해석: 비과세·감면 요건은 명확한 조문 근거가 있어야 함\n\n"

    "## 출력 형식\n"
    "## 1. 💡 결론\n"
    "## 2. 📖 상세 설명\n"
    "## 3. ⚖️ 법적 근거\n"
    "## 4. ⚡ 실무 주의사항\n"
    "## 5. ❓ 추가 확인 필요 사항\n\n"
    "## 📋 근거 출처 목록\n"
    "(아래 형식으로 인용한 자료를 모두 나열)\n"
    "[법률] 법령명 제X조 - 조문제목\n"
    "[시행령] 법령명 시행령 제X조\n"
    "[시행규칙] 법령명 시행규칙 제X조\n"
    "[실무자료] 출처명 (구속력 없음)\n\n"

    "규칙:\n"
    "- 항상 마크다운으로 작성\n"
    "- 법적 근거는 조문 번호까지 명시\n"
    "- 근거 없는 내용은 절대 추정하지 말 것\n"
    "- <think> 태그 내용은 출력하지 말 것\n"
)

# ── 2단계: 웹 검색 Gap Analysis 프롬프트 ──────────────────────
_GAP_PROMPT = (
    "너는 1차 답변을 검토하여 부족한 부분을 웹 검색으로 보완하는 '지식 보완 전문가'이다.\n\n"

    "## Task\n"
    "아래 1차 답변에서 '명확한 근거를 찾지 못했습니다', '근거 없음', '전문가 확인 권장'으로 "
    "표시된 부분을 찾아 웹 검색 쿼리를 생성하라.\n\n"

    "## 검색 쿼리 생성 규칙\n"
    "1. 구어체를 법률 용어로 변환 (예: '알바비' → '인적용역 원천징수')\n"
    "2. 아래 3가지 관점으로 쿼리 생성:\n"
    "   - 법령/조문 관점: '소득세법 제XX조' 등 근거 검색\n"
    "   - 실무/해석 관점: '국세청 유권해석', '최신 예규' 검색\n"
    "   - 계산/방법 관점: 세액 산출 공식, 신고 방법 검색\n"
    "3. 검색어 뒤에 '2026년' 또는 '최신' 키워드 포함\n\n"

    "## 출력 형식 (JSON)\n"
    "{\n"
    '  "gap_found": "부족했던 정보 설명",\n'
    '  "search_queries": ["검색어1", "검색어2", "검색어3"],\n'
    '  "search_required": true/false\n'
    "}\n\n"

    "search_required가 false면 검색 없이 SKIP.\n"
    "오직 JSON만 출력하세요.\n"
    "- <think> 태그 내용은 출력하지 말 것\n"
)

# ── 3단계: 최종 답변 요약 프롬프트 ───────────────────────────
_SUMMARY_PROMPT = (
    "너는 내부 법령 DB 검색 결과와 외부 웹 검색 결과를 합성하여 "
    "최종 답변을 생성하는 세무 법령 전문 AI이다.\n\n"

    "## 합성 전략\n"
    "1. 내부 DB의 공식 법령 조문(source_type=law)을 최우선 근거로 사용한다.\n"
    "2. 시행령·시행규칙은 법률 요건의 세부 기준으로 보완한다.\n"
    "3. 웹 검색 결과는 DB가 다루지 못한 최신 해석·예규 보완에만 사용한다.\n"
    "4. 이전 대화 맥락을 반영하여 맞춤형 답변을 생성한다.\n"
    "5. 근거가 없는 내용은 추정하지 말고 '근거 없음'으로 명시한다.\n\n"

    "## 최종 출력 형식\n"
    "## 1. 💡 결론 요약\n"
    "## 2. 📖 상세 내용\n"
    "## 3. ⚖️ 법적 근거\n"
    "## 4. ⚡ 실무 주의사항\n\n"
    "## 📋 근거 출처 목록\n"
    "(인용한 모든 자료를 아래 형식으로 나열)\n"
    "[법률] 법령명 제X조 - 조문제목\n"
    "[시행령] 법령명 시행령 제X조\n"
    "[시행규칙] 법령명 시행규칙 제X조\n"
    "[웹출처] URL 또는 자료명\n"
    "[실무자료] 출처명 (구속력 없음)\n\n"

    "규칙:\n"
    "- 항상 마크다운으로 작성\n"
    "- 법적 근거는 조문 번호까지 명시\n"
    "- 불확실한 내용은 반드시 '전문가 확인 권장' 표시\n"
    "- 근거 없는 내용은 절대 추정하지 말 것\n"
    "- <think> 태그 내용은 출력하지 말 것\n"
)


async def _call_ollama(messages: list[dict], temperature: float = 0.3) -> str:
    """Ollama 호출 공통 함수."""
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            _CHAT_URL,
            json={
                "model":    CHAT_MODEL,
                "messages": messages,
                "stream":   False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 2000,
                    "num_ctx":     8192,
                },
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


async def _tavily_search(queries: list[str]) -> str:
    """Tavily 웹 검색 실행."""
    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for query in queries[:3]:  # 최대 3개 쿼리
            try:
                resp = await client.post(
                    _TAVILY_URL,
                    headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
                    json={
                        "query":        query,
                        "search_depth": "advanced",
                        "max_results":  3,
                        "include_domains": [
                            "nts.go.kr",    # 국세청
                            "law.go.kr",    # 법제처
                            "moef.go.kr",   # 기획재정부
                        ],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                for r in data.get("results", []):
                    results.append(
                        f"[출처: {r.get('url','?')}]\n{r.get('content','')[:500]}"
                    )
            except Exception:
                continue

    return "\n\n---\n\n".join(results) if results else "웹 검색 결과 없음"


async def process_chat(query: str, user_id: str) -> str:
    """
    3단계 RAG 파이프라인
    1단계: 내부 법령 DB 검색 → 1차 답변
    2단계: Gap Analysis → Tavily 웹 검색
    3단계: 최종 답변 합성
    """
    answer = ""
    session_id = _uuid.UUID(user_id)

    # 세목 분류
    law_filter = await detect_law_name(query)

    # 하이브리드 검색 (law_articles + documents 병합)
    context = await fetch_hybrid_context(query, law_filter)

    # 메모리 조회
    history = await _fetch_history(session_id)

    # ── 1단계: 자료 검색기 ──────────────────────────────────────
    messages_1 = [{"role": "system", "content": _RAG_PROMPT}]
    messages_1.extend(history)
    messages_1.append({"role": "user", "content": (
        f"[검색된 세무 법령 자료]\n{context}\n\n[사용자 질문]\n{query}"
    )})

    rag_answer = await _call_ollama(messages_1, temperature=0.3)

    # ── 2단계: Gap Analysis + Tavily 웹 검색 ───────────────────
    web_results = "웹 검색 생략"

    if TAVILY_API_KEY:
        messages_2 = [
            {"role": "system", "content": _GAP_PROMPT},
            {"role": "user",   "content": (
                f"[사용자 질문]\n{query}\n\n"
                f"[1차 답변]\n{rag_answer}"
            )},
        ]
        gap_raw = await _call_ollama(messages_2, temperature=0.0)

        try:
            # <think> 태그 제거 후 JSON 파싱
            clean = gap_raw.split("</think>")[-1].strip()
            gap   = json.loads(clean)

            if gap.get("search_required") and gap.get("search_queries"):
                web_results = await _tavily_search(gap["search_queries"])
        except Exception:
            pass  # Gap Analysis 실패 시 웹 검색 생략

    # ── 3단계: 최종 답변 요약 ──────────────────────────────────
    messages_3 = [{"role": "system", "content": _SUMMARY_PROMPT}]
    messages_3.extend(history)
    messages_3.append({"role": "user", "content": (
        f"[사용자 질문]\n{query}\n\n"
        f"[내부 DB 검색 결과]\n{rag_answer}\n\n"
        f"[웹 검색 결과]\n{web_results}"
    )})

    answer = await _call_ollama(messages_3, temperature=0.3)

    # 메모리 저장
    await _save_history(session_id, query, answer)

    return answer