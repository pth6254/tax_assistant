"""Seed the statutory figures of the real-estate capital gains calculator.

Values and effective dates were read from the archived official text of 소득세법 (law_history)
and the current 소득세법·시행령 on 2026-10-10:
- 제89조 제1항 제3호: 고가주택 기준 실지거래가액 12억원, from the 2021-12-08 version.
- 제95조 제2항 표1: 3년 이상 보유 시 연 2%(100분의 6~30), 15년 이상 30%, from the 2019-01-01 version.
- 제95조 제2항 표2: 보유 연 4%(최대 40%)와 거주 연 4%(2년 이상 3년 미만 8%, 최대 40%), from the
  2021-01-01 version.
- 제104조 제1항 제2호·제3호: 1년 이상 2년 미만 40%(주택 60%), 1년 미만 50%(주택 70%); the 주택 rates
  from the 2021-06-01 version, the others from 2014-01-01.
- 제104조 제7항: 조정대상지역 2주택 20%p, 3주택 이상 30%p 가산, from the 2021-06-01 version.
- 지방세법 제103조의3: 양도소득분 지방소득세 세율은 소득세 세율의 10분의 1.
The old short-term categories (`단기1년미만`/`단기2년미만`) and `장기보유특별공제_*` rows are left
as they were; the calculator no longer reads them.
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
from alembic import op

revision = '20261010_0012'
down_revision = '20261008_0011'
branch_labels = None
depends_on = None

DEDUCTIONS = [
    ('고가주택기준금액', '1200000000', 'NULL', '2021-12-08', '소득세법 제89조'),
    ('장기보유특별공제_일반_연공제율', 'NULL', '0.0200', '2019-01-01', '소득세법 제95조'),
    ('장기보유특별공제_일반_한도', 'NULL', '0.3000', '2019-01-01', '소득세법 제95조'),
    ('장기보유특별공제_1주택_보유_연공제율', 'NULL', '0.0400', '2021-01-01', '소득세법 제95조'),
    ('장기보유특별공제_1주택_보유_한도', 'NULL', '0.4000', '2021-01-01', '소득세법 제95조'),
    ('장기보유특별공제_1주택_거주_연공제율', 'NULL', '0.0400', '2021-01-01', '소득세법 제95조'),
    ('장기보유특별공제_1주택_거주_한도', 'NULL', '0.4000', '2021-01-01', '소득세법 제95조'),
    ('다주택중과_2주택', 'NULL', '0.2000', '2021-06-01', '소득세법 제104조'),
    ('다주택중과_3주택이상', 'NULL', '0.3000', '2021-06-01', '소득세법 제104조'),
    ('지방소득세_비율', 'NULL', '0.1000', '2014-01-01', '지방세법 제103조의3'),
]
SHORT_RATES = [
    ('주택_1년미만', '0.7000', '2021-06-01'),
    ('주택_2년미만', '0.6000', '2021-06-01'),
    ('토지건물_1년미만', '0.5000', '2014-01-01'),
    ('토지건물_2년미만', '0.4000', '2014-01-01'),
]


def upgrade():
    for name, amount, rate, effective, source in DEDUCTIONS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '양도소득세', '{name}', {amount}, {rate}, NULL, '{{}}', DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions
                              WHERE tax_type = '양도소득세' AND deduction_name = '{name}'
                                AND effective_date = DATE '{effective}')""")
    for category, rate, effective in SHORT_RATES:
        op.execute(f"""
            INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction,
                                      effective_date, source_article)
            SELECT '양도소득세', '{category}', 0, NULL, {rate}, 0, DATE '{effective}', '소득세법 제104조'
            WHERE NOT EXISTS (SELECT 1 FROM tax_brackets
                              WHERE tax_type = '양도소득세' AND category = '{category}'
                                AND effective_date = DATE '{effective}')""")


def downgrade():
    names = ", ".join(f"'{row[0]}'" for row in DEDUCTIONS)
    categories = ", ".join(f"'{row[0]}'" for row in SHORT_RATES)
    op.execute(f"DELETE FROM tax_deductions WHERE tax_type = '양도소득세' AND deduction_name IN ({names})")
    op.execute(f"DELETE FROM tax_brackets WHERE tax_type = '양도소득세' AND category IN ({categories})")
