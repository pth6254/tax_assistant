"""Seed the statutory figures of financial income comprehensive taxation.

Each value and effective date was read from the archived official text of 소득세법
(law_history) on 2026-10-08:
- 제14조 제3항 제6호: 이자소득등의 종합과세기준금액 2천만원 (4천만원 until 2012, 2천만원 from the
  2013-01-01 version).
- 제129조 제1항: 그 밖의 이자소득·배당소득 100분의 14, 비영업대금의 이익 100분의 25 (same wording
  from the 2009-12-31 version on).
- 제17조 제3항 단서: 배당가산 100분의 11 (text states 100분의 12 for 2009~2010 dividends, so 11
  from 2011), 100분의 10 from the 2024-01-01 version, 100분의 11 again in the version effective
  2027-01-01 (promulgated 2025-12-23).
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
from alembic import op

revision = '20261008_0011'
down_revision = '20260930_0010'
branch_labels = None
depends_on = None

ROWS = [
    ('이자소득등종합과세기준금액', '20000000', 'NULL', '2013-01-01', '소득세법 제14조'),
    ('금융소득원천징수율', 'NULL', '0.1400', '2009-12-31', '소득세법 제129조'),
    ('비영업대금이익원천징수율', 'NULL', '0.2500', '2009-12-31', '소득세법 제129조'),
    ('배당가산율', 'NULL', '0.1100', '2011-01-01', '소득세법 제17조'),
    ('배당가산율', 'NULL', '0.1000', '2024-01-01', '소득세법 제17조'),
    ('배당가산율', 'NULL', '0.1100', '2027-01-01', '소득세법 제17조'),
]


def upgrade():
    for name, amount, rate, effective, source in ROWS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '소득세', '{name}', {amount}, {rate}, NULL, '{{}}', DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions
                              WHERE tax_type = '소득세' AND deduction_name = '{name}'
                                AND effective_date = DATE '{effective}')""")


def downgrade():
    names = ", ".join(f"'{name}'" for name in dict.fromkeys(row[0] for row in ROWS))
    op.execute(f"DELETE FROM tax_deductions WHERE tax_type = '소득세' AND deduction_name IN ({names})")
