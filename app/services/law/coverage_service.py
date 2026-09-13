"""Explicit national-tax coverage; discovery ministry names are not a manifest."""
from app.database import get_pool

NATIONAL_TAX_LAWS = (
    '국세기본법', '소득세법', '법인세법', '부가가치세법',
    '상속세 및 증여세법', '조세특례제한법', '관세법',
)
REQUIRED_SUBORDINATE_LAWS = tuple(
    {'law_name': f'{name} {suffix}', 'tax_type': name}
    for name in NATIONAL_TAX_LAWS for suffix in ('시행령', '시행규칙')
)


async def missing_subordinate_laws():
    """Presence check only, not a completeness/as-of-date guarantee."""
    pool = await get_pool()
    rows = await pool.fetch('''
        SELECT DISTINCT law_name FROM law_articles
        WHERE is_current = TRUE AND law_type <> '법령해석례'
    ''')
    existing = {''.join(row['law_name'].split()) for row in rows}
    return [dict(t) for t in REQUIRED_SUBORDINATE_LAWS
            if ''.join(t['law_name'].split()) not in existing]
