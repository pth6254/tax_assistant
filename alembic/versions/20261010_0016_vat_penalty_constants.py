"""Seed the statutory figures of the VAT and penalty tax calculators.

Values and effective dates were read from the archived official text (law_history) and the current
text on 2026-10-10:
부가가치세
- 법 제46조 제1항: 신용카드매출전표등 발행세액공제 1.3%, 연 1천만원 한도 (2026-12-31까지), 그 후 1%·500만원.
  The 1.3% rate for every eligible business (간이과세자 음식·숙박업의 2.6% ended 2021-12-31) is seeded from 2022-01-01.
- 시행령 제111조 제2항: 간이과세자 업종별 부가가치율 15·20·25·30·40%, 법 제63조 제3항: 매입 공급대가의 0.5%,
  both from 2021-07-01; 법 제69조 제1항: 납부의무 면제 공급대가 4,800만원 미만, from 2021-01-01.
- 법 제42조 제1항·시행령 제84조 제2항: 음식점업 개인사업자 의제매입세액 공제율 9/109(과세표준 2억원 이하, 2026년까지)
  또는 8/108, 한도 과세표준의 75%(1억원 이하)·70%(2억원 이하)·60%, from the 2022-07-01 decree version.
- 조세특례제한법 제104조의8: 전자신고세액공제 1만원.
가산세(국세기본법)
- 제47조의2: 무신고 수입금액 기준 1만분의 7(부정 1만분의 14) — the 20%·40% rates are already seeded.
- 제47조의4·시행령 제27조의4: 납부지연 1일 10만분의 25 (2019-02-12), 10만분의 22 (2022-02-15). The rate column holds four
  decimals, so the daily rate is kept in `condition`.
- 제48조 제2항: 수정신고 감면 90·75·50·30·20·10%, 기한 후 신고 감면 50·30·20%, from the 2020-01-01 version.
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
import json

from alembic import op

revision = '20261010_0016'
down_revision = '20261010_0015'
branch_labels = None
depends_on = None

ROWS = [
    # (tax_type, name, amount, rate, max_amount, effective, source, condition)
    ('부가가치세', '신용카드매출전표등발행세액공제', 'NULL', '0.0130', '10000000', '2022-01-01', '부가가치세법 제46조', {}),
    ('부가가치세', '신용카드매출전표등발행세액공제', 'NULL', '0.0100', '5000000', '2027-01-01', '부가가치세법 제46조', {}),
    ('부가가치세', '간이과세_매입세액공제율', 'NULL', '0.0050', 'NULL', '2021-07-01', '부가가치세법 제63조', {}),
    ('부가가치세', '간이과세_납부의무면제', '48000000', 'NULL', 'NULL', '2021-01-01', '부가가치세법 제69조', {}),
    ('부가가치세', '간이과세_부가가치율', 'NULL', 'NULL', 'NULL', '2021-07-01', '부가가치세법 시행령 제111조', {'rates': {
        '소매업': '0.15', '음식점업': '0.15', '제조업': '0.20', '농업·임업·어업': '0.20', '숙박업': '0.25',
        '건설업': '0.30', '운수·창고업': '0.30', '정보통신업': '0.30', '부동산임대업': '0.40', '서비스업': '0.40'}}),
    ('부가가치세', '의제매입세액_음식점_개인', 'NULL', 'NULL', 'NULL', '2022-07-01', '부가가치세법 시행령 제84조', {
        'rates': [[200000000, '9/109'], [None, '8/108']],
        'limits': [[100000000, '0.75'], [200000000, '0.70'], [None, '0.60']]}),
    ('부가가치세', '전자신고세액공제', '10000', 'NULL', 'NULL', '2013-01-01', '조세특례제한법 제104조의8', {}),
    ('가산세', '무신고가산세_수입금액_일반', 'NULL', '0.0007', 'NULL', '2013-01-01', '국세기본법 제47조의2', {}),
    ('가산세', '무신고가산세_수입금액_부정', 'NULL', '0.0014', 'NULL', '2013-01-01', '국세기본법 제47조의2', {}),
    ('가산세', '납부지연가산세_일률', 'NULL', 'NULL', 'NULL', '2019-02-12', '국세기본법 시행령 제27조의4', {'daily_rate': '0.00025'}),
    ('가산세', '납부지연가산세_일률', 'NULL', 'NULL', 'NULL', '2022-02-15', '국세기본법 시행령 제27조의4', {'daily_rate': '0.00022'}),
    ('가산세', '수정신고_감면', 'NULL', 'NULL', 'NULL', '2020-01-01', '국세기본법 제48조', {
        'bands': [[1, '0.90'], [3, '0.75'], [6, '0.50'], [12, '0.30'], [18, '0.20'], [24, '0.10']]}),
    ('가산세', '기한후신고_감면', 'NULL', 'NULL', 'NULL', '2020-01-01', '국세기본법 제48조', {
        'bands': [[1, '0.50'], [3, '0.30'], [6, '0.20']]}),
]


def upgrade():
    for tax_type, name, amount, rate, maximum, effective, source, condition in ROWS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '{tax_type}', '{name}', {amount}, {rate}, {maximum}, '{json.dumps(condition, ensure_ascii=False)}'::jsonb,
                   DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions
                              WHERE tax_type = '{tax_type}' AND deduction_name = '{name}'
                                AND effective_date = DATE '{effective}')""")


def downgrade():
    for tax_type in ('부가가치세', '가산세'):
        names = ", ".join(f"'{row[1]}'" for row in ROWS if row[0] == tax_type)
        op.execute(f"DELETE FROM tax_deductions WHERE tax_type = '{tax_type}' AND deduction_name IN ({names})")
