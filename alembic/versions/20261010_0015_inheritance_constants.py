"""Seed the statutory figures of the inheritance tax calculator.

Values and effective dates were read from the archived official text of 상속세 및 증여세법 and its
enforcement decree (law_history and the current text) on 2026-10-10:
- 제19조 제1항 제2호: 배우자 상속공제 한도 30억원 (unchanged in every archived version from 2013).
- 제20조 제1항: 자녀 1명 5천만원, 미성년자 1천만원 x 19세까지 연수, 65세 이상 5천만원, 장애인 1천만원 x 기대여명
  연수, from the 2016-01-01 version.
- 제22조 제1항: 금융재산 상속공제 순금융재산의 20% 또는 2천만원 중 큰 금액(2천만원 이하는 전액), 2억원 한도,
  from the 2016-01-01 version.
- 제24조 단서: 가산한 증여재산은 과세가액이 5억원을 넘을 때만 공제 한도에서 뺀다, from the 2016-01-01 version.
- 제25조 제2항: 과세최저한 50만원; 제27조: 세대생략 할증 30%(미성년 20억원 초과 40%), from the 2016-01-01 version;
  제69조 제1항: 신고세액공제 3%, 2019-01-01 (2018 deaths kept 5% under the supplementary provision).
- 시행령 제9조 제2항: 장례비용 최소 500만원·한도 1천만원, 봉안시설 등 한도 500만원, from the 2011-01-01 version.
The existing 기초공제·일괄공제·배우자상속공제_최소 rows (2024-01-01) and brackets are left as they are.
Rows are inserted only when absent, so re-running against a seeded database is harmless.
"""
from alembic import op

revision = '20261010_0015'
down_revision = '20261010_0014'
branch_labels = None
depends_on = None

ROWS = [
    ('배우자상속공제_한도', '3000000000', 'NULL', 'NULL', '2013-01-01', '상속세 및 증여세법 제19조'),
    ('자녀공제', '50000000', 'NULL', 'NULL', '2016-01-01', '상속세 및 증여세법 제20조'),
    ('미성년자공제_연', '10000000', 'NULL', 'NULL', '2016-01-01', '상속세 및 증여세법 제20조'),
    ('연로자공제', '50000000', 'NULL', 'NULL', '2016-01-01', '상속세 및 증여세법 제20조'),
    ('장애인공제_연', '10000000', 'NULL', 'NULL', '2016-01-01', '상속세 및 증여세법 제20조'),
    ('금융재산상속공제', '20000000', '0.2000', '200000000', '2016-01-01', '상속세 및 증여세법 제22조'),
    ('공제한도_증여가산_기준', '500000000', 'NULL', 'NULL', '2016-01-01', '상속세 및 증여세법 제24조'),
    ('장례비용_최소', '5000000', 'NULL', 'NULL', '2011-01-01', '상속세 및 증여세법 시행령 제9조'),
    ('장례비용_한도', '10000000', 'NULL', 'NULL', '2011-01-01', '상속세 및 증여세법 시행령 제9조'),
    ('봉안비용_한도', '5000000', 'NULL', 'NULL', '2011-01-01', '상속세 및 증여세법 시행령 제9조'),
    ('세대생략할증률', 'NULL', '0.3000', 'NULL', '2016-01-01', '상속세 및 증여세법 제27조'),
    ('세대생략할증률_미성년_고액', '2000000000', '0.4000', 'NULL', '2016-01-01', '상속세 및 증여세법 제27조'),
    ('신고세액공제율', 'NULL', '0.0300', 'NULL', '2019-01-01', '상속세 및 증여세법 제69조'),
    ('과세최저한', '500000', 'NULL', 'NULL', '2013-01-01', '상속세 및 증여세법 제25조'),
]


def upgrade():
    for name, amount, rate, maximum, effective, source in ROWS:
        op.execute(f"""
            INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition,
                                        effective_date, source_article)
            SELECT '상속세', '{name}', {amount}, {rate}, {maximum}, '{{}}', DATE '{effective}', '{source}'
            WHERE NOT EXISTS (SELECT 1 FROM tax_deductions
                              WHERE tax_type = '상속세' AND deduction_name = '{name}'
                                AND effective_date = DATE '{effective}')""")


def downgrade():
    names = ", ".join(f"'{row[0]}'" for row in ROWS)
    op.execute(f"DELETE FROM tax_deductions WHERE tax_type = '상속세' AND deduction_name IN ({names})")
