"""Seed the rate tables in force from 2021-01-01, so a chat or calculator date in 2021~2023 is computed on its own law.

Most base rows were first seeded with a placeholder effective date of 2024-01-01. Each row below was checked against the
archived official text (law_history) on 2026-10-12, and its effective date is the earliest archived version that states
the value without a break up to 2021 (an earlier start in force before the archive's first version is not claimed):
- 소득세법 제55조 기본세율: 2021-01-01 version 1,200만/4,600만/8,800만/1.5억/3억/5억/10억, 6~45%; 2023-01-01 version
  1,400만/5,000만/… (same as the 2024 rows). 양도소득 기본세율(제104조 제1항 제1호)은 같은 표를 쓴다.
- 소득세법 제59조 근로소득세액공제 55%/71만5천원+30% (2015-05-13 version); 한도 74만원, 3,300만~7,000만원 74만원-초과액x8/1000
  (최소 66만원), 7,000만원 초과 66만원-초과액x1/2 (최소 50만원) (2015-05-13 version, 2022 version까지).
- 소득세법 제50조 기본공제 150만원 (2010-01-01), 제103조 양도소득 기본공제 250만원 (2001-01-01).
- 소득세법 시행령 제156조 고가주택 9억원 (2008-10-07 version, 2021-12-08 법 제89조 12억원 전까지).
- 소득세법 제104조: 주택·조합원입주권 1년 미만 40% (2014-01-01 version, 2021-06-01 70% 전까지), 1년 이상 2년 미만은
  단기세율 없이 기본세율(0으로 저장, 계산기는 기본세율과 비교); 조정대상지역 다주택 기본세율+10%p/20%p (2018-04-01 version);
  대주주 1년 미만 비중소 30% (2017-01-01), 소액주주 중소 10%·그 밖 20% (2018-01-01), 국외주식(제94조 제1항 제3호 다목)
  중소 10%·그 밖 20% (2020-01-01). 2021-06-01 전 분양권은 조정대상지역 여부로 세율이 갈려 넣지 않았다(계산기가 멈춘다).
- 소득세법 시행규칙 제23조 정기예금이자율: 1천분의 18 (2020-03-13), 12 (2021-03-16), 29 (2023-03-20), 35 (2024-03-22).
  시행령 제53조 제3항: (보증금 - 3억원) x 60%. 2주택 규정은 2026년 과세기간부터라 없다.
- 국세기본법 제47조의2 무신고 20% (2017-01-01 version)·부정 40% (2020-01-01 version), 제47조의3 과소신고 10%
  (2007-01-01)·부정 40% (2015-01-01).
- 상속세 및 증여세법 제18조 기초공제 2억원·제19조 배우자 최소 5억원 (2005-07-13), 제21조 일괄공제 5억원 (2010-01-01),
  제26조 세율 10~50% (2005-07-13, 제56조 증여세 준용), 제53조 배우자 6억원 (2010-01-01)·직계존속 5천만원·미성년 2천만원
  (2014-01-01)·기타친족 1천만원 (2016-01-01). 혼인·출산공제는 2024-01-01 신설이라 그 전 행이 없다.
- 부가가치세법 제30조 10% (2013-07-01), 제46조 신용카드 등 발행세액공제 1.3%·연 1천만원 (2019-01-01 version, 2021년까지
  특례), 시행령 제84조 음식점 개인 의제매입 한도 65%/60%/50% (2018-09-28 version)와 제42조 공제율 9/109(2억원 이하)·8/108
  (2019-01-01 version) → 2019-01-01 행.
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
import json

from alembic import op

revision = '20261012_0022'
down_revision = '20261011_0021'
branch_labels = None
depends_on = None

OLD_BASIC = [(0, 12000000, '0.06', 0), (12000000, 46000000, '0.15', 1080000), (46000000, 88000000, '0.24', 5220000),
             (88000000, 150000000, '0.35', 14900000), (150000000, 300000000, '0.38', 19400000),
             (300000000, 500000000, '0.40', 25400000), (500000000, 1000000000, '0.42', 35400000),
             (1000000000, None, '0.45', 65400000)]
NEW_BASIC = [(0, 14000000, '0.06', 0), (14000000, 50000000, '0.15', 1260000), (50000000, 88000000, '0.24', 5760000),
             (88000000, 150000000, '0.35', 15440000), (150000000, 300000000, '0.38', 19940000),
             (300000000, 500000000, '0.40', 25940000), (500000000, 1000000000, '0.42', 35940000),
             (1000000000, None, '0.45', 65940000)]
INHERITANCE = [(0, 100000000, '0.10', 0), (100000000, 500000000, '0.20', 10000000),
               (500000000, 1000000000, '0.30', 60000000), (1000000000, 3000000000, '0.40', 160000000),
               (3000000000, None, '0.50', 460000000)]
WAGE_CREDIT = [(0, None, '0.55', 0), (1300000, None, '0.30', -325000)]

# (tax_type, category, effective, bands, source)
BRACKETS = [
    ('소득세', 'default', '2021-01-01', OLD_BASIC, '소득세법 제55조'),
    ('소득세', 'default', '2023-01-01', NEW_BASIC, '소득세법 제55조'),
    ('양도소득세', '기본', '2021-01-01', OLD_BASIC, '소득세법 제104조'),
    ('양도소득세', '기본', '2023-01-01', NEW_BASIC, '소득세법 제104조'),
    ('소득세', '근로소득세액공제', '2015-05-13', WAGE_CREDIT, '소득세법 제59조'),
    ('양도소득세', '주택_1년미만', '2014-01-01', [(0, None, '0.40', 0)], '소득세법 제104조'),
    # 1년 이상 2년 미만 주택·입주권은 단기세율 없이 기본세율: 0은 "기본세율과 비교할 단기세율 없음".
    ('양도소득세', '주택_2년미만', '2014-01-01', [(0, None, '0', 0)], '소득세법 제104조'),
    ('상속세', 'default', '2005-07-13', INHERITANCE, '상속세 및 증여세법 제26조'),
    ('증여세', 'default', '2005-07-13', INHERITANCE, '상속세 및 증여세법 제26조'),
    ('부가가치세', 'default', '2013-07-01', [(0, None, '0.10', 0)], '부가가치세법 제30조'),
]

DEEMED_RENT = {"ratio": "0.6", "house_count": 3}
# (tax_type, name, amount, rate, max_amount, condition, effective, source)
ROWS = [
    ('소득세', '기본공제', 1500000, None, None, {}, '2010-01-01', '소득세법 제50조'),
    ('소득세', '양도소득기본공제', 2500000, None, None, {}, '2001-01-01', '소득세법 제103조'),
    ('소득세', '근로소득세액공제_한도', None, None, None,
     {"tiers": [[0, 740000, "0", 740000], [33000000, 740000, "0.008", 660000], [70000000, 660000, "0.5", 500000]]},
     '2015-05-13', '소득세법 제59조'),
    ('소득세', '간주임대료_주택', 300000000, '0.0180', None, DEEMED_RENT, '2020-03-13', '소득세법 제25조'),
    ('소득세', '간주임대료_주택', 300000000, '0.0120', None, DEEMED_RENT, '2021-03-16', '소득세법 제25조'),
    ('소득세', '간주임대료_주택', 300000000, '0.0290', None, DEEMED_RENT, '2023-03-20', '소득세법 제25조'),
    ('소득세', '간주임대료_주택', 300000000, '0.0350', None, DEEMED_RENT, '2024-03-22', '소득세법 제25조'),
    ('양도소득세', '고가주택기준금액', 900000000, None, None, {}, '2008-10-07', '소득세법 시행령 제156조'),
    ('양도소득세', '다주택중과_2주택', None, '0.1000', None, {}, '2018-04-01', '소득세법 제104조'),
    ('양도소득세', '다주택중과_3주택이상', None, '0.2000', None, {}, '2018-04-01', '소득세법 제104조'),
    ('양도소득세', '주식_대주주_단기_비중소', None, '0.3000', None, {}, '2017-01-01', '소득세법 제104조'),
    ('양도소득세', '주식_소액_중소', None, '0.1000', None, {}, '2018-01-01', '소득세법 제104조'),
    ('양도소득세', '주식_소액_비중소', None, '0.2000', None, {}, '2018-01-01', '소득세법 제104조'),
    ('양도소득세', '주식_국외_중소', None, '0.1000', None, {}, '2020-01-01', '소득세법 제104조'),
    ('양도소득세', '주식_국외', None, '0.2000', None, {}, '2020-01-01', '소득세법 제104조'),
    ('가산세', '무신고가산세_일반', None, '0.2000', None, {}, '2017-01-01', '국세기본법 제47조의2'),
    ('가산세', '무신고가산세_부정', None, '0.4000', None, {}, '2020-01-01', '국세기본법 제47조의2'),
    ('가산세', '과소신고가산세_일반', None, '0.1000', None, {}, '2007-01-01', '국세기본법 제47조의3'),
    ('가산세', '과소신고가산세_부정', None, '0.4000', None, {}, '2015-01-01', '국세기본법 제47조의3'),
    ('상속세', '기초공제', 200000000, None, None, {}, '2005-07-13', '상속세 및 증여세법 제18조'),
    ('상속세', '배우자상속공제_최소', 500000000, None, None, {}, '2005-07-13', '상속세 및 증여세법 제19조'),
    ('상속세', '일괄공제', 500000000, None, None, {}, '2010-01-01', '상속세 및 증여세법 제21조'),
    ('증여세', '증여재산공제_배우자', 600000000, None, None, {"relation": "배우자"}, '2010-01-01', '상속세 및 증여세법 제53조'),
    ('증여세', '증여재산공제_직계존비속', 50000000, None, None, {"relation": "직계존비속"}, '2014-01-01',
     '상속세 및 증여세법 제53조'),
    ('증여세', '증여재산공제_직계존비속_미성년', 20000000, None, None, {"is_minor": True, "relation": "직계존비속"},
     '2014-01-01', '상속세 및 증여세법 제53조'),
    ('증여세', '증여재산공제_기타친족', 10000000, None, None, {"relation": "기타친족"}, '2016-01-01', '상속세 및 증여세법 제53조'),
    ('부가가치세', '신용카드매출전표등발행세액공제', None, '0.0130', 10000000, {}, '2019-01-01', '부가가치세법 제46조'),
    ('부가가치세', '의제매입세액_음식점_개인', None, None, None,
     {"rates": [[200000000, "9/109"], [None, "8/108"]], "limits": [[100000000, "0.65"], [200000000, "0.60"], [None, "0.50"]]},
     '2019-01-01', '부가가치세법 시행령 제84조'),
]


def _sql(value):
    return "NULL" if value is None else str(value)


def upgrade():
    for tax_type, category, effective, bands, source in BRACKETS:
        for low, high, rate, deduction in bands:
            op.execute(f"""
                INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction,
                                          effective_date, source_article)
                SELECT '{tax_type}', '{category}', {low}, {_sql(high)}, {rate}, {deduction}, DATE '{effective}', '{source}'
                WHERE NOT EXISTS (SELECT 1 FROM tax_brackets WHERE tax_type = '{tax_type}' AND category = '{category}'
                                  AND effective_date = DATE '{effective}' AND bracket_from = {low})""")
    for tax_type, name, amount, rate, max_amount, condition, effective, source in ROWS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date,
                                        source_article)
            SELECT '{tax_type}', '{name}', {_sql(amount)}, {_sql(rate)}, {_sql(max_amount)},
                   '{json.dumps(condition, ensure_ascii=False)}'::jsonb, DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions WHERE tax_type = '{tax_type}' AND deduction_name = '{name}'
                              AND effective_date = DATE '{effective}')""")


def downgrade():
    for tax_type, category, effective, _bands, _source in BRACKETS:
        op.execute(f"""DELETE FROM tax_brackets WHERE tax_type = '{tax_type}' AND category = '{category}'
                       AND effective_date = DATE '{effective}'""")
    for tax_type, name, *_rest, effective, _source in ROWS:
        op.execute(f"""DELETE FROM tax_deductions WHERE tax_type = '{tax_type}' AND deduction_name = '{name}'
                       AND effective_date = DATE '{effective}'""")
