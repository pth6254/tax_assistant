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

from config import (
    CHAT_MODEL,
    MEMORY_TURNS,
    TOP_K,
    TAVILY_API_KEY,
    THINK_ENABLED,
)
from app.services.calculator.engine import CalcRun, run_calculation_for_query
from app.services.citation_guard import apply_citation_guard, build_citation_footer
from app.services.llm_client import call_llm, stream_llm
from app.services.search.web_search import tavily_search
from app.database import get_pool
from app.services.search.hybrid_search_service import (
    format_hybrid_context,
    hybrid_search,
)

logger = logging.getLogger(__name__)

# 상위 3개 평균 유사도가 이 값 미만일 때만 웹 검색 실행
# 임베딩 점수 분포상 정답을 top-1으로 찾은 질문도 0.47~0.58 수준이라
# 0.7이면 사실상 매번 웹 검색이 실행됨 (질문당 +2~5초) → 0.55로 조정
_WEB_SEARCH_THRESHOLD = 0.55

# 세목 키워드 매핑
_LAW_KW: dict[str, list[str]] = {
    "소득세법":              ["소득세", "종합소득", "원천징수", "근로소득", "사업소득", "기타소득", "양도소득",
                              "퇴직소득", "연금소득", "이자소득", "배당소득", "임대소득",
                              "연말정산", "근로장려금", "자녀장려금", "인적공제", "부양가족공제"],
    "부가가치세법":          ["부가세", "부가가치세", "vat", "간이과세", "일반과세", "매입세액", "매출세액",
                              "세금계산서", "전자세금계산서", "영세율", "면세사업자", "의제매입세액",
                              "부가세 신고", "예정신고", "확정신고"],
    "법인세법":              ["법인세", "법인소득", "법인 세금", "업무용승용차", "법인차량", "법인 리스",
                              "손금", "익금", "결손금", "접대비 한도", "기부금 한도", "법인 감가상각"],
    "상속세 및 증여세법":    ["상속세", "증여세", "상속", "증여", "유산",
                              "가업승계", "상속공제", "증여공제", "연부연납", "물납"],
    "지방세법":              ["지방세", "취득세", "재산세", "주민세", "자동차세", "등록면허세",
                              "지방소득세", "지방소비세", "레저세", "담배소비세", "지방교육세"],
    # "공제"/"감면"/"세액공제"는 모든 세목에 공통으로 등장하는 일반 용어라 제외.
    # 인적공제·표준세액공제 등 다른 세목 질문까지 조세특례제한법으로 오분류시키는 원인이었음.
    "조세특례제한법":        ["조세특례", "조특법", "세제혜택",
                              "투자세액공제", "연구개발비 세액공제", "고용증대세액공제",
                              "중소기업 특별세액", "창업 세액감면", "청년 창업"],
    "국세기본법":            ["국세기본", "가산세", "경정청구", "불복", "과세전적부심사",
                              "심사청구", "심판청구", "이의신청", "기한후신고",
                              "세무조사", "납부기한 연장", "분할납부"],
    "종합부동산세법":        ["종합부동산세", "종부세", "공시가격", "다주택자", "주택 보유세"],
    "개별소비세법":          ["개별소비세", "특별소비세"],
    "교통에너지환경세법":    ["교통에너지환경세", "교통세"],
    "주세법":                ["주세", "주류세"],
    "인지세법":              ["인지세"],
    "농어촌특별세법":        ["농어촌특별세", "농특세"],
    "교육세법":              ["교육세"],
    "증권거래세법":          ["증권거래세"],
    "국세징수법":            ["국세징수", "체납", "압류", "공매",
                              "체납처분", "납부고지", "압류해제", "징수유예", "결손처분"],
    "조세범처벌법":          ["조세범", "세금포탈", "조세포탈"],
    "국제조세조정에관한법률": ["국제조세", "이전가격", "조세조약", "해외금융계좌",
                              "해외직접투자", "해외법인"],
    "관세법":                ["관세", "수입세", "수출입", "관세청",
                              "통관", "원산지 증명", "관세환급", "보세구역"],
    "지방세기본법":          ["지방세기본", "지방세 불복", "지방세 경정"],
    "지방세특례제한법":      ["지방세특례", "지방세 감면"],
    "지방세징수법":          ["지방세징수", "지방세 체납"],
}


def _match_laws_by_keyword(query: str) -> list[str]:
    """키워드 매칭으로 후보 세목을 찾는다.

    같은 위치에서 여러 세목의 키워드가 겹치면(예: '체납' vs '지방세 체납',
    '소득세' vs '지방소득세') 더 긴(구체적인) 키워드만 채택하여 불필요한
    다중 매칭 → ALL 폴백을 줄인다.
    """
    q = query.lower()
    spans: list[tuple[int, int, str]] = []
    for law, kws in _LAW_KW.items():
        for kw in kws:
            start = 0
            while (idx := q.find(kw, start)) != -1:
                spans.append((idx, idx + len(kw), law))
                start = idx + 1

    spans.sort(key=lambda s: s[0] - s[1])  # 길이 내림차순(긴 구간 우선)
    kept: list[tuple[int, int, str]] = []
    for start, end, law in spans:
        if any(start < k_end and end > k_start for k_start, k_end, _ in kept):
            continue
        kept.append((start, end, law))

    return sorted({law for _, _, law in kept})


async def detect_law_name(query: str) -> str:
    """질문에서 세목명 추출. 불명확하면 'ALL' 반환."""
    q = query.lower()
    for law, kws in _LAW_KW.items():
        if any(kw in q for kw in kws):
            return law

    # 키워드 매핑 실패 시 LLM으로 판단
    try:
        raw = await call_llm(
            [{"role": "user", "content": (
                "다음 질문이 어떤 세법과 관련 있는지 하나만 답하세요.\n"
                "후보: 소득세법, 부가가치세법, 법인세법, 상속세 및 증여세법, "
                "지방세법, 조세특례제한법, 국세기본법, ALL\n"
                f"질문: {query}\n오직 세법 이름 하나만 출력하세요."
            )}],
            temperature=0.0,
            num_predict=20,
        )
        result = raw.strip()
        return result if result in _LAW_KW else "ALL"
    except Exception:
        return "ALL"



async def _fetch_history(conversation_id: _uuid.UUID) -> list[dict]:
    """Postgres에서 최근 대화 메모리 조회."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT message FROM chat_logs
               WHERE conversation_id = $1
               ORDER BY created_at DESC LIMIT $2""",
            conversation_id, MEMORY_TURNS * 2,
        )
    history = []
    for r in reversed(rows):
        msg = r["message"]
        history.append(json.loads(msg) if isinstance(msg, str) else msg)
    return history


async def _save_history(
    conversation_id: _uuid.UUID,
    query: str,
    answer: str,
    is_first: bool = False,
) -> None:
    """대화 턴을 chat_logs에 저장. 첫 메시지면 대화 제목도 자동 업데이트."""
    title = query[:28].rstrip() + ("..." if len(query) > 28 else "")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO chat_logs (conversation_id, message) VALUES ($1, $2)",
            [
                (conversation_id, json.dumps({"role": "user",      "content": query},  ensure_ascii=False)),
                (conversation_id, json.dumps({"role": "assistant", "content": answer}, ensure_ascii=False)),
            ],
        )
        if is_first:
            await conn.execute(
                "UPDATE conversations SET title = $1, updated_at = now() WHERE id = $2",
                title, conversation_id,
            )
        else:
            await conn.execute(
                "UPDATE conversations SET updated_at = now() WHERE id = $1",
                conversation_id,
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
    "| 4        | interpretation  | 기획재정부·국세청 등 유권해석 | 행정 해석 근거, 법령과 충돌 시 법령 우선 |\n"
    "| 5        | practice_pdf    | 집행기준·실무자료 PDF         | 해설·사례 보완, 구속력 없음 |\n"
    "| 6        | user_pdf        | 사용자 업로드 PDF             | 참고용, 법적 효력 없음    |\n"
    "| 7        | 웹 검색 결과    | 최신 인터넷 자료              | DB 미수록 최신 해석·예규만 |\n\n"

    "## 근거 사용 규칙\n"
    "1. 공식 법령 조문(law)을 최우선 근거로 사용한다.\n"
    "2. 시행령(regulation)·시행규칙(rule)은 법률의 세부 요건 보완 자료로 사용한다.\n"
    "3. 유권해석(interpretation)은 실무 적용례로 사용하되, 법령과 내용이 다르면 법령을 따른다.\n"
    "4. PDF 실무자료(practice_pdf, user_pdf)는 해설 또는 사례 보완으로만 사용한다.\n"
    "5. 웹 검색 결과는 DB가 다루지 못한 최신 해석·예규 보완에만 사용한다.\n"
    "6. 법령(law)과 다른 자료가 충돌하면 법령을 우선한다.\n"
    "7. A와 B를 직접 비교하는 단일 조문이 없어도, 각 항목에 적용되는 법령 조문을 "
    "각각 근거로 삼아 비교 분석하고 결론을 제시한다. "
    "단, 법령 근거 없는 내용은 절대 추정·일반론으로 서술하지 않는다.\n"
    "8. 어떤 항목에 대한 법령 근거가 전혀 없는 경우에만 "
    "'해당 내용에 대한 명확한 법령 근거를 찾지 못했습니다'라고 항목별로 명시한다.\n"
    "9. 세무 리스크가 있는 판단은 반드시 '전문가 확인 권장'을 표시한다.\n"
    "10. '요건은?', '조건은?', '대상은?'처럼 서술형 질문이거나 여러 조문을 함께 "
    "설명해야 하는 경우에도, 표나 자유 서술로만 답하지 말고 아래 '## 출력 형식'과 "
    "'## 📋 근거 출처 목록'을 예외 없이 그대로 포함한다. 언급한 조문이 여러 개면 "
    "근거 출처 목록에 모두 나열한다.\n\n"

    "## 세법 일반 원칙\n"
    "- 특별법 우선: 조세특례제한법이 일반 세법보다 우선 적용\n"
    "- 신법 우선: 같은 위계의 법령은 최신 개정령이 우선\n"
    "- 엄격 해석: 비과세·감면 요건은 명확한 조문 근거가 있어야 함\n\n"

    "## 출력 형식\n"
    "**비교 질문(A vs B)인 경우**: 결론에서 어느 쪽이 유리한지 명확히 제시하고, "
    "상세 설명에 항목별 비교표(| 구분 | A | B |)를 포함한다.\n"
    "**단일 질문인 경우**: 아래 형식을 그대로 사용한다.\n\n"
    "## 1. 💡 결론\n"
    "(비교 질문이면 '○○가 유리하다' 또는 '상황에 따라 ○○가 유리하다'로 명확히 제시)\n"
    "## 2. 📖 상세 설명\n"
    "## 3. ⚖️ 법적 근거\n"
    "## 4. ⚡ 실무 주의사항\n\n"
    "## 📋 근거 출처 목록\n"
    "(아래 형식으로 인용한 자료를 모두 나열)\n"
    "[법률] 법령명 제X조 - 조문제목\n"
    "[시행령] 법령명 시행령 제X조\n"
    "[시행규칙] 법령명 시행규칙 제X조\n"
    "[유권해석] 안건번호 - 안건명 요약\n"
    "[웹출처] URL 또는 자료명\n"
    "[실무자료] 출처명 (구속력 없음)\n\n"

    "규칙:\n"
    "- 항상 마크다운으로 작성\n"
    "- 법적 근거는 조문 번호까지 명시\n"
    "- 근거 없는 내용은 절대 추정하지 말 것\n"
    "- '## 📋 근거 출처 목록' 섹션과 [법률]/[시행령]/[시행규칙]/[유권해석] 브래킷 형식은 "
    "모든 답변에 예외 없이 포함할 것 — 서술형 질문이라도 생략 금지\n"
    "- <think> 태그 내용은 출력하지 말 것\n"
)

# ── 멀티쿼리 생성 프롬프트 ────────────────────────────
_MULTI_QUERY_PROMPT = (
    "한국 세무 법령 검색을 위한 검색어 3개를 서로 다른 관점으로 생성하라.\n\n"
    "## 관점\n"
    "1. 법령/조문 관점: 관련 법령명·조문 번호·법령 용어 중심\n"
    "2. 요건/대상 관점: 적용 대상·요건·예외사항 중심\n"
    "3. 계산/절차 관점: 세액 산출·신고 방법·실무 절차 중심\n\n"
    "## 비교 질문(A vs B) 특별 규칙\n"
    "- 질문이 두 가지 옵션을 비교하는 경우, A와 B 각각에 대한 쿼리를 최소 1개씩 생성하라.\n"
    "  예: '리스 vs 장기렌트' → '법인 업무용승용차 리스 손금산입' + '법인 업무용승용차 장기렌트 임차료 손금'\n\n"
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
    "   후보: 소득세법, 부가가치세법, 법인세법, 상속세 및 증여세법,\n"
    "         지방세법, 조세특례제한법, 국세기본법, ALL\n"
    "2. queries: 서로 다른 관점의 검색어 3개 (각 50자 이내)\n"
    "   - 법령/조문 관점, 요건/대상 관점, 계산/절차 관점\n"
    "   - 구어체 → 법령 용어 변환\n\n"
    '출력 형식 (JSON만, 다른 내용 없음):\n'
    '{"law": "소득세법", "queries": ["검색어1", "검색어2", "검색어3"]}\n'
    "- <think> 태그 내용은 출력하지 말 것\n"
)

# 비스트리밍 답변도 스트리밍과 동일하게 길이 제한 없음(-1).
# 과거 num_predict=500으로 답변이 ~900자에서 잘려 마지막 섹션(근거 출처 목록)이
# 통째로 사라졌다 — 인용 정확도 측정에서 무인용 실패 17건의 주원인으로 지목됨.
_NUM_PREDICT_DEFAULT     = -1
_NUM_PREDICT_MULTI_QUERY = 150

# Qwen3 계열 모델에서만 /no_think 접두사 사용 (다른 모델에는 노이즈)
_QWEN3_NO_THINK_PREFIX = "/no_think\n\n" if (
    not THINK_ENABLED and any(k in CHAT_MODEL.lower() for k in ("qwen3",))
) else ""

# 스트리밍 완료 후 백그라운드로 실행되는 DB 저장 태스크 참조 보관 (GC 방지)
_bg_tasks: set[asyncio.Task] = set()


async def close_chat_client() -> None:
    """앱 종료 시 정리 훅. LangChain의 ChatOllama는 호출마다 자체 클라이언트를 관리하므로 no-op."""
    return


async def _call_ollama(
    messages: list[dict],
    temperature: float = 0.3,
    num_predict: int = _NUM_PREDICT_DEFAULT,
) -> str:
    """LLM 비스트리밍 호출 (llm_client 경유)."""
    return await call_llm(messages, temperature=temperature, num_predict=num_predict)


async def _stream_ollama_response(
    messages: list[dict],
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    LLM 스트리밍 호출 (llm_client 경유). <think> 블록은 버퍼 누적 없이 실시간으로 건너뜀.

    기존 방식은 </think>를 찾을 때까지 모든 토큰을 buf에 쌓아 TTFT가 매우 길었음.
    개선: in_think 상태에서 최대 8자(</think> 경계 감지용)만 보관하고 나머지는 즉시 버림.
    """
    in_think = False
    buf = ""   # 태그 경계 감지에만 사용 — 최대 수십 자 이내로 유지

    async for chunk in stream_llm(messages, temperature=temperature, num_predict=_NUM_PREDICT_DEFAULT):
        if chunk:
            buf += chunk

            if in_think:
                end = buf.find("</think>")
                if end != -1:
                    in_think = False
                    buf = buf[end + 8:]   # 8 = len("</think>")
                else:
                    # think 블록 내부 — 경계 감지에 필요한 최소분만 보관
                    buf = buf[-7:] if len(buf) > 7 else buf

            if not in_think and buf:
                start = buf.find("<think>")
                if start != -1:
                    before = buf[:start]
                    if before:
                        yield before
                    in_think = True
                    logger.info("[STREAM] <think> 블록 감지 — think:False 미적용 상태")
                    buf = buf[start + 7:]   # 7 = len("<think>")
                    # 같은 청크에 </think>가 함께 있는 경우
                    end = buf.find("</think>")
                    if end != -1:
                        in_think = False
                        buf = buf[end + 8:]
                    else:
                        buf = buf[-7:] if len(buf) > 7 else buf
                else:
                    # think 없음 — 마지막 6자는 '<think' 시작 가능성 보존
                    safe = buf[:-6] if len(buf) > 6 else ""
                    if safe:
                        yield safe
                        buf = buf[len(safe):]

    if buf and not in_think:
        yield buf




async def generate_search_queries(query: str) -> list[str]:
    """질문으로부터 다각도 검색 쿼리 3개 생성. 실패 시 원본만 반환."""
    try:
        raw = await _call_ollama(
            [
                {"role": "system", "content": _MULTI_QUERY_PROMPT},
                {"role": "user",   "content": query},
            ],
            temperature=0.0,
            num_predict=_NUM_PREDICT_MULTI_QUERY,
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


async def _classify_and_generate_queries(
    query: str,
    history: list[dict] | None = None,
) -> tuple[str, list[str]]:
    """세목 분류 + 검색 쿼리 생성을 1회 LLM 호출로 처리. 실패 시 키워드 분류 + 원본 쿼리 반환.

    여러 세목 키워드가 동시에 감지되면 ALL(전체 검색)을 사용한다.
    history가 전달되면 직전 2턴 맥락을 쿼리 생성 프롬프트에 포함한다.
    """
    matched_laws = _match_laws_by_keyword(query)
    keyword_law = matched_laws[0] if len(matched_laws) == 1 else "ALL"
    if len(matched_laws) > 1:
        logger.info("[CLASSIFY] 다중 세목 감지(%s) — ALL 전체 검색", matched_laws)

    # 키워드만으로 세목이 명확히 하나로 확정되면 분류 LLM 호출 자체를 생략한다
    # (멀티쿼리 다양성은 포기하되 TTFT를 약 3초 단축 — 회귀 여부는 scripts/eval_rag.py로 검증)
    if len(matched_laws) == 1:
        logger.info("[CLASSIFY] 키워드로 세목 확정(%s) — 분류 LLM 생략, 원본 쿼리로 검색", keyword_law)
        return keyword_law, [query]

    # 직전 2턴(user+assistant 각 1회) 맥락 구성
    user_content = query
    if history:
        recent = history[-4:]
        parts = [
            ("사용자" if m.get("role") == "user" else "AI")
            + ": "
            + str(m.get("content", ""))[:150].replace("\n", " ")
            for m in recent
        ]
        user_content = "[이전 대화 맥락]\n" + "\n".join(parts) + f"\n\n[현재 질문]\n{query}"

    try:
        raw = await _call_ollama(
            [
                {"role": "system", "content": _COMBINED_CLASSIFY_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.0,
            num_predict=_NUM_PREDICT_MULTI_QUERY,
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
    conversation_id: _uuid.UUID,
    user_id: str,
) -> tuple[str, str, list[dict], CalcRun | None]:
    """
    세목 분류·법령 검색·웹 검색·세금 계산기를 수행하고
    (context, web_results, history, calc_run)를 반환한다.
    DB 유사도가 충분하면 웹 검색을 생략하여 불필요한 지연을 제거한다.
    계산기는 RAG 검색과 병렬로 실행되며 계산 질문이 아니면 None.
    """
    t0 = time.perf_counter()

    # 계산 질문이면 계산기를 RAG와 병렬로 실행 (아니면 즉시 None 반환되는 no-op)
    calc_task = asyncio.create_task(run_calculation_for_query(query))

    # 히스토리를 먼저 조회한 뒤 맥락을 쿼리 생성에 주입 (후속 질문 품질 향상)
    history = await _fetch_history(conversation_id)
    law_filter, search_queries = await _classify_and_generate_queries(query, history)
    logger.info("[RAG] 세목=%s | 히스토리=%d턴 | 검색쿼리=%d개", law_filter, len(history) // 2, len(search_queries))

    results = await hybrid_search(search_queries, law_filter, user_id=user_id, original_query=query)
    context = format_hybrid_context(results)
    logger.info("[RAG] 하이브리드 검색 완료 (%.1fs)", time.perf_counter() - t0)

    web_results = "웹 검색 생략"
    if TAVILY_API_KEY:
        top3 = results[:3]
        top3_avg = sum(r.similarity_score for r in top3) / len(top3) if top3 else 0.0
        if top3_avg < _WEB_SEARCH_THRESHOLD:
            logger.info("[RAG] 상위 3개 평균 유사도 낮음(%.2f) — 웹 검색 실행", top3_avg)
            web_results = await tavily_search([query])
        else:
            logger.info("[RAG] 상위 3개 평균 유사도 충분(%.2f) — 웹 검색 생략", top3_avg)

    try:
        calc_run = await calc_task
    except Exception as e:
        logger.warning("[RAG] 계산기 실행 오류 — 계산 없이 진행: %s", e)
        calc_run = None

    logger.info("[RAG] 준비 단계 총 소요: %.1fs | 계산기=%s", time.perf_counter() - t0, "실행" if calc_run else "미실행")
    return context, web_results, history, calc_run


def _build_final_messages(
    query: str,
    context: str,
    web_results: str,
    history: list[dict],
    calc_run: CalcRun | None = None,
) -> list[dict]:
    """최종 답변용 메시지 목록을 생성한다."""
    messages = [{"role": "system", "content": _COMBINED_PROMPT}]
    messages.extend(history)
    user_content = _QWEN3_NO_THINK_PREFIX
    user_content += f"[검색된 세무 법령 자료]\n{context}"
    if web_results and web_results != "웹 검색 생략":
        user_content += f"\n\n[웹 검색 결과]\n{web_results}"
    if calc_run:
        user_content += (
            f"\n\n[세금 계산기 결과 — DB 세율표 기반 정확한 계산]\n{calc_run.context}\n"
            "위 계산 결과를 결론에 반영하고, 상세 설명에 계산 단계를 표(| 항목 | 금액 |)로 제시하라. "
            "계산 수치를 임의로 바꾸지 말 것. 근거 조문은 법적 근거 섹션에 포함하라."
        )
    user_content += f"\n\n[사용자 질문]\n{query}"
    messages.append({"role": "user", "content": user_content})
    return messages


def _calc_meta(calc_run: CalcRun | None) -> dict | None:
    """프론트엔드 계산기 화면 프리필용 메타데이터(도구명 + 파라미터)."""
    return {"tool": calc_run.tool, "params": calc_run.params} if calc_run else None


async def process_chat(query: str, conversation_id: str, user_id: str) -> tuple[str, dict | None]:
    """RAG 파이프라인 실행 후 (최종 답변, 계산기 메타데이터)를 반환한다 (비스트리밍)."""
    logger.info("[CHAT] 요청 수신: %.40s...", query)
    t0 = time.perf_counter()

    conv_id = _uuid.UUID(conversation_id)
    context, web_results, history, calc_run = await _fetch_rag_and_web_context(query, conv_id, user_id)

    messages = _build_final_messages(query, context, web_results, history, calc_run)
    answer   = await _call_ollama(messages, temperature=0.3)
    answer   = apply_citation_guard(answer, context, calc_run.context if calc_run else None)

    await _save_history(conv_id, query, answer, is_first=len(history) == 0)
    logger.info("[CHAT] 응답 완료 — 총 %.1fs | 답변 %d자", time.perf_counter() - t0, len(answer))
    return answer, _calc_meta(calc_run)


async def stream_chat_response(
    query: str,
    conversation_id: str,
    user_id: str,
) -> AsyncGenerator[dict, None]:
    """RAG 파이프라인 실행 후 이벤트를 yield한다 (스트리밍).

    {"type": "chunk", "text": ...} — 답변 토큰/각주
    {"type": "calc", "tool": ..., "params": ...} — 계산기가 실행된 경우, 스트림 종료 직전 1회
    """
    logger.info("[STREAM] 요청 수신: %.40s...", query)
    t0 = time.perf_counter()

    conv_id = _uuid.UUID(conversation_id)
    context, web_results, history, calc_run = await _fetch_rag_and_web_context(query, conv_id, user_id)

    messages     = _build_final_messages(query, context, web_results, history, calc_run)
    full_answer: list[str] = []
    is_first = len(history) == 0

    logger.info("[STREAM] 최종 답변 스트리밍 시작")
    async for chunk in _stream_ollama_response(messages, temperature=0.3):
        full_answer.append(chunk)
        yield {"type": "chunk", "text": chunk}

    answer = "".join(full_answer)
    calc_context = calc_run.context if calc_run else None
    footer = build_citation_footer(answer, context, calc_context)
    if footer:
        yield {"type": "chunk", "text": footer}
        answer += footer

    calc_meta = _calc_meta(calc_run)
    if calc_meta:
        yield {"type": "calc", **calc_meta}

    logger.info("[STREAM] 완료 — 총 %.1fs | 답변 %d자", time.perf_counter() - t0, len(answer))
    task = asyncio.create_task(_save_history(conv_id, query, answer, is_first=is_first))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)