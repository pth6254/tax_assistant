"""Seed the statutory figures for pension, other, rental, estimated business and daily-wage income.

Values and effective dates were read from the archived official text (law_history) on 2026-10-11:
- 소득세법 제47조의2: 연금소득공제 표(350만원 이하 전액, 40%·20%·10%), 한도 900만원 (2011-01-01·2006-01-01 versions).
- 제14조 제3항 제9호: 사적연금 연 1,500만원 이하 분리과세 (2024-01-01; 1,200만원 from 2015-01-01).
  제64조의4: 1,500만원 초과 사적연금 15% 분리과세 선택 (2023-01-01 version). 제129조 제1항 제5호의2: 연금수령
  원천징수 70세 미만 5%, 80세 미만 4%, 80세 이상 3%.
- 제14조 제3항 제8호: 기타소득금액 300만원 이하 분리과세 선택 (2007-01-01), 제129조: 기타소득 20% (2009-12-31).
  시행령 제87조: 강연료·원고료 등 필요경비 의제 60% (2019-01-01; 2018-04-01~12-31 70%), 공익법인 상금 등 80% (2005).
- 제64조의2: 분리과세 주택임대소득 필요경비 50%(등록임대 60%), 다른 종합소득금액 2천만원 이하면 200만원(400만원) 차감,
  14% (2019-01-01). 제14조 제3항 제7호: 주택임대 총수입금액 2천만원 이하.
- 시행령 제143조 제3항: 기준경비율 소득금액, 복식부기의무자 기준경비율 1/2 (2011-01-01); 시행규칙 제67조: 배율
  간편장부대상자 2.8, 복식부기의무자 3.4 (2020-03-13).
- 제47조 제2항: 일용근로자 근로소득공제 1일 15만원 (2019-01-01), 제129조: 6% (2011-01-01), 제59조 제3항: 55% 공제
  (2010-01-01), 제86조: 소액부징수 1천원 미만 (2003-07-30).
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
import json

from alembic import op

revision = '20261011_0017'
down_revision = '20261010_0016'
branch_labels = None
depends_on = None

DEDUCTIONS = [
    # (name, amount, rate, max_amount, effective, source, condition)
    ('연금소득공제_한도', '9000000', 'NULL', 'NULL', '2006-01-01', '소득세법 제47조의2', {}),
    ('사적연금_분리과세_기준', '15000000', 'NULL', 'NULL', '2024-01-01', '소득세법 제14조', {}),
    ('사적연금_분리과세_기준', '12000000', 'NULL', 'NULL', '2015-01-01', '소득세법 제14조', {}),
    ('사적연금_분리과세율', 'NULL', '0.1500', 'NULL', '2023-01-01', '소득세법 제64조의4', {}),
    ('연금수령_원천징수율', 'NULL', 'NULL', 'NULL', '2015-01-01', '소득세법 제129조', {
        'bands': [[69, '0.05'], [79, '0.04'], [None, '0.03']]}),
    ('기타소득_분리과세_기준', '3000000', 'NULL', 'NULL', '2007-01-01', '소득세법 제14조', {}),
    ('기타소득_원천징수율', 'NULL', '0.2000', 'NULL', '2009-12-31', '소득세법 제129조', {}),
    ('기타소득_필요경비의제_60', 'NULL', '0.6000', 'NULL', '2019-01-01', '소득세법 시행령 제87조', {}),
    ('기타소득_필요경비의제_80', 'NULL', '0.8000', 'NULL', '2005-02-19', '소득세법 시행령 제87조', {}),
    ('주택임대_분리과세_기준', '20000000', 'NULL', 'NULL', '2019-01-01', '소득세법 제14조', {}),
    ('주택임대_분리과세', 'NULL', '0.1400', 'NULL', '2019-01-01', '소득세법 제64조의2', {
        'expense_rate': '0.50', 'registered_expense_rate': '0.60', 'deduction': 2000000,
        'registered_deduction': 4000000, 'other_income_limit': 20000000}),
    ('추계_배율', 'NULL', 'NULL', 'NULL', '2020-03-13', '소득세법 시행규칙 제67조', {
        'simple_books': '2.8', 'double_entry': '3.4'}),
    ('추계_복식부기_기준경비율_비율', 'NULL', '0.5000', 'NULL', '2011-01-01', '소득세법 시행령 제143조', {}),
    ('일용근로_근로소득공제', '150000', 'NULL', 'NULL', '2019-01-01', '소득세법 제47조', {}),
    ('일용근로_원천징수율', 'NULL', '0.0600', 'NULL', '2011-01-01', '소득세법 제129조', {}),
    ('일용근로_세액공제율', 'NULL', '0.5500', 'NULL', '2010-01-01', '소득세법 제59조', {}),
    ('소액부징수', '1000', 'NULL', 'NULL', '2003-07-30', '소득세법 제86조', {}),
]
# 연금소득공제 = rate x 총연금액 + 상수 (progressive_deduction holds the negated constant).
PENSION_BANDS = [(0, '1.0000', 0), (3500000, '0.4000', -2100000), (7000000, '0.2000', -3500000),
                 (14000000, '0.1000', -4900000)]


def upgrade():
    for name, amount, rate, maximum, effective, source, condition in DEDUCTIONS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '소득세', '{name}', {amount}, {rate}, {maximum}, '{json.dumps(condition)}'::jsonb,
                   DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions
                              WHERE tax_type = '소득세' AND deduction_name = '{name}'
                                AND effective_date = DATE '{effective}')""")
    for lower, rate, constant in PENSION_BANDS:
        op.execute(f"""
            INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction,
                                      effective_date, source_article)
            SELECT '소득세', '연금소득공제', {lower}, NULL, {rate}, {constant}, DATE '2011-01-01', '소득세법 제47조의2'
            WHERE NOT EXISTS (SELECT 1 FROM tax_brackets WHERE tax_type = '소득세' AND category = '연금소득공제'
                              AND bracket_from = {lower} AND effective_date = DATE '2011-01-01')""")


def downgrade():
    names = ", ".join(sorted({f"'{row[0]}'" for row in DEDUCTIONS}))
    op.execute(f"DELETE FROM tax_deductions WHERE tax_type = '소득세' AND deduction_name IN ({names})")
    op.execute("DELETE FROM tax_brackets WHERE tax_type = '소득세' AND category = '연금소득공제'")
