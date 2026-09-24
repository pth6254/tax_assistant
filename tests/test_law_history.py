from datetime import date

import pytest

from app.services.law.history_parser import listing, parse, redact

DETAIL = '''<법령><기본정보><법령ID>001</법령ID><법령명_한글>시험법</법령명_한글>
<시행일자>20200101</시행일자><공포일자>20190101</공포일자></기본정보>
<조문><조문단위 조문키="590040"><조문번호>59</조문번호><조문가지번호>4</조문가지번호>
<조문여부>조문</조문여부><조문내용>본문</조문내용><항><항번호>①</항번호>
<항내용>첫 항</항내용><호><호번호>1.</호번호><호내용>첫 호</호내용>
<목><목번호>가.</목번호><목내용>첫 목</목내용></목></호></항></조문단위>
<조문단위><조문번호>60</조문번호><조문여부>삭제</조문여부><조문내용>삭제</조문내용></조문단위>
<조문단위><조문번호>60</조문번호><조문여부>전문</조문여부><조문내용>제2장</조문내용></조문단위></조문>
<부칙><부칙단위 부칙키="x"><부칙내용>종전 규정에 따른다.</부칙내용></부칙단위></부칙></법령>'''


def test_history_keeps_deleted_headings_branch_and_structure():
    data = parse(DETAIL,law_id='1',effective_date=date(2020,1,1))
    assert len(data['articles']) == 3
    a = data['articles'][0]
    assert (a['article_number'],a['article_branch']) == ('59','4')
    assert '첫 목' in a['body']
    assert data['articles'][1]['unit_kind'] == '삭제'
    assert data['articles'][2]['unit_kind'] == '전문'
    assert '종전 규정' in data['supplements'][0]['body']


@pytest.mark.parametrize('kwargs', [dict(law_id='2'),dict(effective_date=date(2021,1,1)),
                                   dict(promulgation_date=date(2018,1,1))])
def test_history_rejects_wrong_identity_or_date(kwargs):
    with pytest.raises(ValueError):
        parse(DETAIL,**kwargs)


@pytest.mark.parametrize('xml',['<html>error</html>','<법령><기본정보><법령ID>1</법령ID></기본정보></법령>'])
def test_history_rejects_empty_or_html(xml):
    with pytest.raises(ValueError):
        parse(xml)


def test_listing_preserves_same_mst_distinct_effective_dates():
    unit='<law><법령ID>001</법령ID><법령일련번호>25</법령일련번호><시행일자>{}</시행일자></law>'
    xml='<LawSearch><totalCnt>2</totalCnt>'+unit.format('20200101')+unit.format('20210101')+'</LawSearch>'
    rows,total=listing(xml,'001')
    assert total==2 and rows[0]['mst']==rows[1]['mst']
    assert rows[0]['effective_date']!=rows[1]['effective_date']
    with pytest.raises(ValueError):
        listing(xml,'002')


def test_redact_oc_and_literal_secret():
    assert 'private' not in redact('<x>url?OC=private&amp;MST=3 private</x>','private')
    assert 'other' not in redact('url?OC=other&type=XML')


@pytest.mark.parametrize('stored,held,age,expected', [
    ('running', False, 1, 'interrupted'),
    ('running', True, 10, 'running'),
    ('running', True, 181, 'unresponsive'),
    ('complete', False, 200, 'complete'),
    ('partial', False, 200, 'partial'),
])
def test_observed_worker_status(stored, held, age, expected):
    from app.services.law.history_service import observed_run_status
    assert observed_run_status({'status': stored}, held, age) == expected
