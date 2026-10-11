"""Seed the figures of the finishing calculator options and allow retirement consultations.

Values and effective dates were read from the archived official text (law_history) on 2026-10-11:
- 소득세법 제129조 제1항 제5호의3: 퇴직소득을 연금수령하면 연금외수령 원천징수세율의 100분의 70 (2015-01-01 version),
  실제 수령연차 10년 초과분 100분의 60 (2020-01-01 version), 20년 초과분 100분의 50 (2026-01-01 version).
- 소득세법 제25조 제1항·시행령 제53조 제1항·제3항·시행규칙 제23조 제1항: 주택 보증금 간주임대료 =
  (보증금 - 3억원) x 60% x 정기예금이자율 연 1천분의 31 (시행규칙 2025-03-21 version). 3주택 이상·보증금 3억원 초과,
  또는 2주택(기준시가 12억원 이하 제외)·보증금 12억원 초과(시행령 2025-02-28 신설, 2026년 과세기간부터).
- 소득세법 시행령 제87조 제3호: 종교인소득 필요경비 80% / 1,600만원+50% / 2,600만원+30% / 3,200만원+20%
  (2018-01-01 version).
- 국세기본법 제47조의2 제2항 제2호·제47조의3 제2항 제2호: 영세율과세표준의 1천분의 5 (2012-01-01 version).
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
import json

from alembic import op

revision = '20261011_0021'
down_revision = '20261011_0020'
branch_labels = None
depends_on = None

ROWS = [
    ('소득세', '이연퇴직소득_연금수령_감경', None, None, {"bands": [[None, "0.7"]]}, '2015-01-01', '소득세법 제129조'),
    ('소득세', '이연퇴직소득_연금수령_감경', None, None, {"bands": [[10, "0.7"], [None, "0.6"]]}, '2020-01-01',
     '소득세법 제129조'),
    ('소득세', '이연퇴직소득_연금수령_감경', None, None, {"bands": [[10, "0.7"], [20, "0.6"], [None, "0.5"]]},
     '2026-01-01', '소득세법 제129조'),
    ('소득세', '간주임대료_주택', 300000000, '0.0310',
     {"ratio": "0.6", "house_count": 3, "two_house_deposit": 1200000000, "two_house_from": "2026-01-01"},
     '2025-03-21', '소득세법 제25조'),
    ('소득세', '종교인소득_필요경비', None, None,
     {"bands": [[20000000, "0.8", 0, 0], [40000000, "0.5", 16000000, 20000000],
                [60000000, "0.3", 26000000, 40000000], [None, "0.2", 32000000, 60000000]]},
     '2018-01-01', '소득세법 시행령 제87조'),
    ('가산세', '영세율과세표준_불성실', None, '0.0050', {}, '2012-01-01', '국세기본법 제47조의2'),
]
KINDS = "'income_tax','capital_gains','inheritance','gift','vat','penalty_tax'"


def _sql(value):
    return "NULL" if value is None else str(value)


def upgrade():
    for tax_type, name, amount, rate, condition, effective, source in ROWS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date,
                                        source_article)
            SELECT '{tax_type}', '{name}', {_sql(amount)}, {_sql(rate)}, NULL, '{json.dumps(condition)}'::jsonb,
                   DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions WHERE tax_type = '{tax_type}' AND deduction_name = '{name}'
                              AND effective_date = DATE '{effective}')""")
    op.execute("ALTER TABLE consultation_cases DROP CONSTRAINT consultation_cases_kind_check")
    op.execute(f"""ALTER TABLE consultation_cases ADD CONSTRAINT consultation_cases_kind_check
        CHECK (kind IN ({KINDS},'retirement'))""")


def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM consultation_cases WHERE kind = 'retirement') THEN
                RAISE EXCEPTION 'Cannot downgrade while retirement consultations exist';
            END IF;
        END $$""")
    op.execute("ALTER TABLE consultation_cases DROP CONSTRAINT consultation_cases_kind_check")
    op.execute(f"ALTER TABLE consultation_cases ADD CONSTRAINT consultation_cases_kind_check CHECK (kind IN ({KINDS}))")
    names = ", ".join(sorted({f"'{name}'" for _, name, *_ in ROWS}))
    op.execute(f"DELETE FROM tax_deductions WHERE deduction_name IN ({names})")
