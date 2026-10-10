"""Seed the statutory figures of the gift tax calculator.

Values and effective dates were read from the archived official text of 상속세 및 증여세법
(law_history) on 2026-10-10:
- 제53조의2: 혼인·출산 증여재산공제 1억원(수증자 기준 합계 한도), from the 2024-01-01 version.
- 제57조 제1항: 세대생략 할증 100분의 30, 미성년자이면서 증여재산가액 20억원 초과는 100분의 40,
  from the 2016-01-01 version.
- 제69조 제2항: 신고세액공제 100분의 3. The 2018-01-01 version already prints 3; 2018 gifts kept
  5% under the supplementary provision, so the row starts at 2019-01-01.
- 제55조 제2항: 과세표준 50만원 미만은 부과하지 않음 (unchanged in every archived version from 2013).
The existing 증여재산공제 rows (2024-01-01) and brackets are left as they are.
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
from alembic import op

revision = '20261010_0014'
down_revision = '20261010_0013'
branch_labels = None
depends_on = None

ROWS = [
    ('증여재산공제_혼인출산', '100000000', 'NULL', '2024-01-01', '상속세 및 증여세법 제53조의2'),
    ('세대생략할증률', 'NULL', '0.3000', '2016-01-01', '상속세 및 증여세법 제57조'),
    ('세대생략할증률_미성년_고액', '2000000000', '0.4000', '2016-01-01', '상속세 및 증여세법 제57조'),
    ('신고세액공제율', 'NULL', '0.0300', '2019-01-01', '상속세 및 증여세법 제69조'),
    ('과세최저한', '500000', 'NULL', '2013-01-01', '상속세 및 증여세법 제55조'),
]


def upgrade():
    for name, amount, rate, effective, source in ROWS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '증여세', '{name}', {amount}, {rate}, NULL, '{{}}', DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions
                              WHERE tax_type = '증여세' AND deduction_name = '{name}'
                                AND effective_date = DATE '{effective}')""")


def downgrade():
    names = ", ".join(f"'{row[0]}'" for row in ROWS)
    op.execute(f"DELETE FROM tax_deductions WHERE tax_type = '증여세' AND deduction_name IN ({names})")
