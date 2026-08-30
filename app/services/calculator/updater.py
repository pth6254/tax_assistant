import json
import logging
import re
from datetime import date

from app.database import get_pool
from app.services.llm_client import call_llm

logger = logging.getLogger(__name__)

_TARGET_ARTICLES = {
    "소득세법": {"제55조": "소득세"},
    "상속세 및 증여세법": {"제26조": "상속세"},
}

_EXTRACT_PROMPT = (
    "다음 세법 조문에서 세율 구간을 JSON으로 추출하라. "
    "형식: [{\"bracket_from\": 0, \"bracket_to\": 14000000, \"rate\": 0.06, \"progressive_deduction\": 0}, ...] "
    "bracket_to가 없는 최고 구간은 null로 표시. JSON 배열만 출력하라."
)


async def _call_ollama_extract(article_text: str) -> list[dict] | None:
    try:
        raw = await call_llm(
            [
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": article_text},
            ],
            temperature=0.0,
            num_predict=500,
        )
        text = raw.split("</think>")[-1].strip()
        fence = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
        candidate = fence.group(1).strip() if fence else text
        match = re.search(r"\[[\s\S]*?\]", candidate)
        if match:
            brackets = json.loads(match.group(0))
            if isinstance(brackets, list):
                return brackets
    except Exception as e:
        logger.warning("LLM 세율 추출 실패: %s", e)
    return None


async def update_tax_rules_from_law(law_name: str, article_no: str, article_text: str) -> bool:
    """조문 텍스트에서 세율 구간을 추출하여 tax_brackets 테이블 업데이트."""
    tax_type = _TARGET_ARTICLES.get(law_name, {}).get(article_no)
    if not tax_type:
        logger.warning("업데이트 대상 아님: %s %s", law_name, article_no)
        return False

    brackets = await _call_ollama_extract(article_text)
    if not brackets:
        logger.warning("세율 구간 추출 실패: %s %s", law_name, article_no)
        return False

    effective_date = date.today()
    source_article = f"{law_name} {article_no}"

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO tax_brackets
                        (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction, effective_date, source_article)
                    VALUES ($1, 'default', $2, $3, $4, $5, $6, $7)
                    """,
                    [
                        (
                            tax_type,
                            int(b.get('bracket_from', 0)),
                            int(b['bracket_to']) if b.get('bracket_to') is not None else None,
                            float(b.get('rate', 0)),
                            int(b.get('progressive_deduction', 0)),
                            effective_date,
                            source_article,
                        )
                        for b in brackets
                        if isinstance(b, dict) and 'bracket_from' in b and 'rate' in b
                    ],
                )
        logger.warning("세율 업데이트 완료: %s %s — %d구간", law_name, article_no, len(brackets))
        return True
    except Exception as e:
        logger.warning("세율 DB 업데이트 실패: %s", e)
        return False
