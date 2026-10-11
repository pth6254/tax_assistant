"""Seed capital gains rates for presale rights, unregistered and non-business land, stocks, derivatives and trusts.

Values and effective dates were read from the archived official text (law_history) on 2026-10-11:
- 소득세법 제104조 제1항 제1호·제3호: 분양권 60%, 1년 미만 70% (2021-06-01 version).
- 제104조 제1항 제10호: 미등기양도자산 70% (2010-01-01). 제8호: 비사업용 토지 기본세율 + 10%p (16~55% table,
  2016-01-01).
- 제104조 제1항 제11호: 대주주 주식 20%(3억원 초과분 25%, 2018-01-01), 중소기업 외 대주주 1년 미만 30%,
  대주주 아닌 자 중소기업 10%·그 밖 20%; 제12호: 국외주식 중소기업 10%·그 밖 20% (current wording from the
  2025-01-01 version). 제13호·시행령 제167조의9: 파생상품 탄력세율 10% (2016-01-01). 제14호: 신탁 수익권 20%·25%
  (2021-01-01, the same table as 대주주 주식).
The 대주주 table is stored as brackets (rate x 과세표준 - 누진공제 1,500만원 above 3억원).
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
from alembic import op

revision = '20261011_0019'
down_revision = '20261011_0018'
branch_labels = None
depends_on = None

RATES = [
    ('분양권_1년미만', '0.7000', '2021-06-01', '소득세법 제104조'),
    ('분양권', '0.6000', '2021-06-01', '소득세법 제104조'),
    ('미등기', '0.7000', '2010-01-01', '소득세법 제104조'),
    ('비사업용토지_가산율', '0.1000', '2016-01-01', '소득세법 제104조'),
    ('주식_대주주_단기_비중소', '0.3000', '2025-01-01', '소득세법 제104조'),
    ('주식_소액_중소', '0.1000', '2025-01-01', '소득세법 제104조'),
    ('주식_소액_비중소', '0.2000', '2025-01-01', '소득세법 제104조'),
    ('주식_국외_중소', '0.1000', '2025-01-01', '소득세법 제104조'),
    ('주식_국외', '0.2000', '2025-01-01', '소득세법 제104조'),
    ('파생상품_탄력세율', '0.1000', '2016-01-01', '소득세법 시행령 제167조의9'),
]
MAJOR = [(0, '0.2000', 0), (300000000, '0.2500', 15000000)]


def upgrade():
    for name, rate, effective, source in RATES:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '양도소득세', '{name}', NULL, {rate}, NULL, '{{}}', DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions WHERE tax_type = '양도소득세'
                              AND deduction_name = '{name}' AND effective_date = DATE '{effective}')""")
    for lower, rate, constant in MAJOR:
        op.execute(f"""
            INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction,
                                      effective_date, source_article)
            SELECT '양도소득세', '주식_대주주', {lower}, NULL, {rate}, {constant}, DATE '2018-01-01', '소득세법 제104조'
            WHERE NOT EXISTS (SELECT 1 FROM tax_brackets WHERE tax_type = '양도소득세' AND category = '주식_대주주'
                              AND bracket_from = {lower} AND effective_date = DATE '2018-01-01')""")


def downgrade():
    names = ", ".join(f"'{row[0]}'" for row in RATES)
    op.execute(f"DELETE FROM tax_deductions WHERE tax_type = '양도소득세' AND deduction_name IN ({names})")
    op.execute("DELETE FROM tax_brackets WHERE tax_type = '양도소득세' AND category = '주식_대주주'")
