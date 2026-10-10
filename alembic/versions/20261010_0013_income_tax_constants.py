"""Seed the statutory figures of the comprehensive income tax calculator.

Values and effective dates were read from the archived official text of 소득세법 (law_history)
and the current text on 2026-10-10:
- 제47조 제1항: 근로소득공제 표(70%·40%·15%·5%·2%)와 공제 한도 2천만원, from the 2020-01-01 version
  (the cap was added by the 2019-12-31 amendment). Each band is stored as rate x 총급여 + constant,
  so `progressive_deduction` holds the negated constant: 350만+(총급여-500만)x40% = 0.4x총급여+150만.
- 제59조 제1항: 근로소득세액공제 55%, 130만원 초과분 71만5천원+30%; 제2항 한도 74만원/66만원/50만원/20만원
  with the 1억2천만원 band, from the 2023-01-01 version (2022-12-31 amendment). Earlier years are not
  seeded: the 2015~2022 limit had three bands, and a calculation for those years reports missing data.
- 제59조의4 제9항: 표준세액공제 근로소득자 13만원, 성실사업자 12만원, 그 밖의 종합소득자 7만원,
  from the 2021-01-01 version.
The existing `표준세액공제_사업자` (12만원) row is left as it was; the calculator no longer reads it,
because 12만원 is the 성실사업자 amount and other business owners receive 7만원.
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
import json

from alembic import op

revision = '20261010_0013'
down_revision = '20261010_0012'
branch_labels = None
depends_on = None

DEDUCTIONS = [
    ('근로소득공제_한도', '20000000', '2020-01-01', '소득세법 제47조', {}),
    ('표준세액공제_근로', '130000', '2021-01-01', '소득세법 제59조의4', {}),
    ('표준세액공제_성실사업자', '120000', '2021-01-01', '소득세법 제59조의4', {}),
    ('표준세액공제_그밖', '70000', '2021-01-01', '소득세법 제59조의4', {}),
    # (총급여 초과 기준, 기준 한도, 초과 급여액에 곱해 빼는 비율, 최소 한도)
    ('근로소득세액공제_한도', 'NULL', '2023-01-01', '소득세법 제59조', {'tiers': [
        [0, 740000, '0', 740000],
        [33000000, 740000, '0.008', 660000],
        [70000000, 660000, '0.5', 500000],
        [120000000, 500000, '0.5', 200000],
    ]}),
]
BRACKETS = {
    ('근로소득공제', '2020-01-01', '소득세법 제47조'): [
        (0, '0.7000', 0), (5000000, '0.4000', -1500000), (15000000, '0.1500', -5250000),
        (45000000, '0.0500', -9750000), (100000000, '0.0200', -12750000)],
    ('근로소득세액공제', '2023-01-01', '소득세법 제59조'): [(0, '0.5500', 0), (1300000, '0.3000', -325000)],
}


def upgrade():
    for name, amount, effective, source, condition in DEDUCTIONS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '소득세', '{name}', {amount}, NULL, NULL, '{json.dumps(condition)}'::jsonb,
                   DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions
                              WHERE tax_type = '소득세' AND deduction_name = '{name}'
                                AND effective_date = DATE '{effective}')""")
    for (category, effective, source), bands in BRACKETS.items():
        for lower, rate, deduction in bands:
            op.execute(f"""
                INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction,
                                          effective_date, source_article)
                SELECT '소득세', '{category}', {lower}, NULL, {rate}, {deduction}, DATE '{effective}', '{source}'
                WHERE NOT EXISTS (SELECT 1 FROM tax_brackets
                                  WHERE tax_type = '소득세' AND category = '{category}' AND bracket_from = {lower}
                                    AND effective_date = DATE '{effective}')""")


def downgrade():
    names = ", ".join(f"'{row[0]}'" for row in DEDUCTIONS)
    categories = ", ".join(f"'{key[0]}'" for key in BRACKETS)
    op.execute(f"DELETE FROM tax_deductions WHERE tax_type = '소득세' AND deduction_name IN ({names})")
    op.execute(f"DELETE FROM tax_brackets WHERE tax_type = '소득세' AND category IN ({categories})")
