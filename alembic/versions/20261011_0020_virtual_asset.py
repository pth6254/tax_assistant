"""Seed the virtual asset income figures.

소득세법 제64조의3 제2항 (2027-01-01 version, archived in law_history on 2026-10-11): 가상자산소득금액에서 250만원을 뺀
금액의 100분의 20. 개인지방소득세는 소득세의 10%(지방세법 제103조의3 계열, shown apart).
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
from alembic import op

revision = '20261011_0020'
down_revision = '20261011_0019'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date,
                                    source_article)
        SELECT '소득세', '가상자산소득', 2500000, 0.2000, NULL, '{"local_ratio": "0.1"}'::jsonb, DATE '2027-01-01',
               '소득세법 제64조의3'
        WHERE NOT EXISTS (SELECT 1 FROM tax_deductions WHERE tax_type = '소득세' AND deduction_name = '가상자산소득')""")


def downgrade():
    op.execute("DELETE FROM tax_deductions WHERE tax_type = '소득세' AND deduction_name = '가상자산소득'")
