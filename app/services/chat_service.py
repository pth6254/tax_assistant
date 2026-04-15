"""
services/chat_service.py — RAG 채팅 비즈니스 로직
질문 세목 분류 → 벡터 검색 → 메모리 조회 → Ollama 답변 → 메모리 저장.
"""
import json
import uuid as _uuid

import httpx

from config import CHAT_MODEL, MEMORY_TURNS, OLLAMA_BASE_URL, TOP_K
from app.database import get_pool
from app.utils.embeddings import embed_texts

_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"

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

_SYSTEM_PROMPT = (
    "당신은 대한민국 최고의 'AI 세무 자동화 어시스턴트'입니다.\n"
    "세무 법령 DB에서 검색된 자료를 1순위 근거로 사용하고, "
    "부족한 경우 세법 일반 원칙을 적용하여 답변하세요.\n\n"
    "답변 형식 (마크다운):\n"
    "## 1. 💡 핵심 요약\n"
    "## 2. 📖 상세 가이드\n"
    "## 3. ⚖️ 법적 근거\n"
    "## 4. ⚡ 실무 대응 팁\n\n"
    "규칙:\n"
    "- 항상 마크다운으로 작성\n"
    "- 법적 근거는 조문 번호까지 명시\n"
    "- 불확실한 내용은 반드시 '전문가 상담 권장' 표시\n"
    "- <think> 태그 내용은 출력하지 말 것"  # Qwen3.5 thinking 모드 제어
)


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
    """pgvector 유사도 검색 → 컨텍스트 문자열 반환."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM match_documents($1::vector, $2, $3)",
            q_emb, TOP_K, law_filter,
        )
    if not rows:
        return "관련 문서를 찾지 못했습니다."
    return "\n\n---\n\n".join(
        f"[출처: {r['metadata'].get('source','?')} | "
        f"{r['metadata'].get('law_name','?')}]\n{r['content']}"
        for r in rows
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


async def process_chat(
    query: str,
    user_id: str,
) -> str:
    """
    RAG 채팅 파이프라인 전체 실행.
    반환: Ollama 답변 문자열
    """
    session_id = _uuid.UUID(user_id)

    # 1. 세목 분류
    law_filter = await detect_law_name(query)

    # 2. 질문 임베딩
    q_emb = (await embed_texts([query]))[0]

    # 3. 벡터 검색
    context = await _fetch_context(q_emb, law_filter)

    # 4. 채팅 메모리 조회
    history = await _fetch_history(session_id)

    # 5. Ollama 답변 생성
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": (
        f"[검색된 세무 법령 자료]\n{context}\n\n[사용자 질문]\n{query}"
    )})

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            _CHAT_URL,
            json={
                "model":   CHAT_MODEL,
                "messages": messages,
                "stream":   False,
                "options": {
                    "temperature":  0.3,
                    "num_predict":  2000,
                    "num_ctx":      8192,  # 컨텍스트 윈도우
                },
            },
        )
        resp.raise_for_status()

    answer = resp.json()["message"]["content"]

    # 6. 메모리 저장
    await _save_history(session_id, query, answer)

    return answer