import logging
from datetime import date

from app.database import get_pool
from app.services.calculator.errors import CalculationError, classify_error

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
            raise CalculationError("missing_tax_data")
        latest_date = rows[0]['effective_date']
        return [dict(r) for r in rows if r['effective_date'] == latest_date]
    except Exception as exc:
        raise classify_error(exc, operation="tax_repository") from exc


async def get_deduction(tax_type: str, deduction_name: str, as_of: date | None = None) -> dict | None:
    """단일 공제 항목 조회."""
    as_of = as_of or date.today()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT amount, rate, max_amount, source_article, condition, effective_date
                FROM tax_deductions
                WHERE tax_type = $1 AND deduction_name = $2 AND effective_date <= $3
                ORDER BY effective_date DESC
                LIMIT 1
            """, tax_type, deduction_name, as_of)
        if row is None:
            raise CalculationError("missing_tax_data")
        return dict(row)
    except Exception as exc:
        raise classify_error(exc, operation="tax_repository") from exc


async def get_source_articles(tax_type: str, as_of: date | None = None) -> list[str]:
    """Return source names used by the latest available bracket and deduction rows."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT source_article FROM (
                    SELECT source_article FROM tax_brackets
                    WHERE tax_type = $1 AND source_article IS NOT NULL
                      AND effective_date = (SELECT max(effective_date) FROM tax_brackets
                                            WHERE tax_type = $1 AND effective_date <= $2)
                    UNION
                    SELECT d.source_article FROM tax_deductions d
                    WHERE d.tax_type = $1 AND d.source_article IS NOT NULL
                      AND d.effective_date = (SELECT max(x.effective_date) FROM tax_deductions x
                                              WHERE x.tax_type = d.tax_type
                                                AND x.deduction_name = d.deduction_name
                                                AND x.effective_date <= $2)
                ) t
            """, tax_type, as_of or date.today())
        return [r['source_article'] for r in rows]
    except Exception as exc:
        raise classify_error(exc, operation="tax_repository") from exc
