import logging
from datetime import date

from app.database import get_pool

logger = logging.getLogger(__name__)


async def get_brackets(tax_type: str, category: str = 'default', as_of: date | None = None) -> list[dict]:
    """해당 세목·구분의 최신 유효 세율 구간 조회."""
    as_of = as_of or date.today()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT bracket_from, bracket_to, rate, progressive_deduction, source_article, effective_date
                FROM tax_brackets
                WHERE tax_type = $1 AND category = $2 AND effective_date <= $3
                ORDER BY effective_date DESC, bracket_from ASC
                LIMIT 20
            """, tax_type, category, as_of)
        if not rows:
            return []
        latest_date = rows[0]['effective_date']
        return [dict(r) for r in rows if r['effective_date'] == latest_date]
    except Exception as e:
        logger.warning("get_brackets 실패 tax_type=%s category=%s: %s", tax_type, category, e)
        return []


async def get_deduction(tax_type: str, deduction_name: str, as_of: date | None = None) -> dict | None:
    """단일 공제 항목 조회."""
    as_of = as_of or date.today()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT amount, rate, max_amount, source_article, condition
                FROM tax_deductions
                WHERE tax_type = $1 AND deduction_name = $2 AND effective_date <= $3
                ORDER BY effective_date DESC
                LIMIT 1
            """, tax_type, deduction_name, as_of)
        return dict(row) if row else None
    except Exception as e:
        logger.warning("get_deduction 실패 tax_type=%s name=%s: %s", tax_type, deduction_name, e)
        return None


async def get_source_articles(tax_type: str) -> list[str]:
    """해당 세목의 모든 근거 조문 목록."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT source_article FROM (
                    SELECT source_article FROM tax_brackets WHERE tax_type = $1 AND source_article IS NOT NULL
                    UNION
                    SELECT source_article FROM tax_deductions WHERE tax_type = $1 AND source_article IS NOT NULL
                ) t
            """, tax_type)
        return [r['source_article'] for r in rows]
    except Exception as e:
        logger.warning("get_source_articles 실패 tax_type=%s: %s", tax_type, e)
        return []
