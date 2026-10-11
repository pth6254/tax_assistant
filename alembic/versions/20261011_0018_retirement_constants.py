"""Seed the statutory figures of the retirement income tax calculator.

Values and effective dates were read from the archived official text of 소득세법 (law_history) on 2026-10-11:
- 제48조 제1항 제1호 근속연수공제: 30만원·150만원+50만원·400만원+80만원·1,200만원+120만원 (2016-01-01 version),
  100만원·500만원+200만원·1,500만원+250만원·4,000만원+300만원 (2023-01-01 version).
- 제48조 제1항 제2호 환산급여공제: 800만원 이하 100%, 800만원+60%, 4,520만원+55%, 6,170만원+45%, 1억5,170만원+35%
  (2016-01-01 version), stored as rate x 환산급여 + 상수.
- 지방세법 제92조·제103조의3 계열: 퇴직소득분 지방소득세는 소득세 세율의 10분의 1 (shown apart).
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
import json

from alembic import op

revision = '20261011_0018'
down_revision = '20261011_0017'
branch_labels = None
depends_on = None

SERVICE = [
    ('2016-01-01', [[5, 0, 300000, 0], [10, 1500000, 500000, 5], [20, 4000000, 800000, 10], [None, 12000000, 1200000, 20]]),
    ('2023-01-01', [[5, 0, 1000000, 0], [10, 5000000, 2000000, 5], [20, 15000000, 2500000, 10], [None, 40000000, 3000000, 20]]),
]
CONVERTED = [(0, '1.0000', 0), (8000000, '0.6000', -3200000), (70000000, '0.5500', -6700000),
             (100000000, '0.4500', -16700000), (300000000, '0.3500', -46700000)]


def upgrade():
    for effective, tiers in SERVICE:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '소득세', '퇴직소득_근속연수공제', NULL, NULL, NULL, '{json.dumps({"tiers": tiers})}'::jsonb,
                   DATE '{effective}', '소득세법 제48조'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions WHERE tax_type = '소득세'
                              AND deduction_name = '퇴직소득_근속연수공제' AND effective_date = DATE '{effective}')""")
    op.execute("""
        INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date,
                                    source_article)
        SELECT '소득세', '퇴직소득_지방소득세_비율', NULL, 0.1000, NULL, '{}'::jsonb, DATE '2014-01-01', '지방세법 제92조'
        WHERE NOT EXISTS (SELECT 1 FROM tax_deductions WHERE tax_type = '소득세'
                          AND deduction_name = '퇴직소득_지방소득세_비율')""")
    for lower, rate, constant in CONVERTED:
        op.execute(f"""
            INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction,
                                      effective_date, source_article)
            SELECT '소득세', '퇴직_환산급여공제', {lower}, NULL, {rate}, {constant}, DATE '2016-01-01', '소득세법 제48조'
            WHERE NOT EXISTS (SELECT 1 FROM tax_brackets WHERE tax_type = '소득세' AND category = '퇴직_환산급여공제'
                              AND bracket_from = {lower} AND effective_date = DATE '2016-01-01')""")


def downgrade():
    op.execute("DELETE FROM tax_deductions WHERE tax_type = '소득세' "
               "AND deduction_name IN ('퇴직소득_근속연수공제', '퇴직소득_지방소득세_비율')")
    op.execute("DELETE FROM tax_brackets WHERE tax_type = '소득세' AND category = '퇴직_환산급여공제'")
