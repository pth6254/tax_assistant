"""
test_api_service.py — law/api_service.py XML 파싱 단위 테스트

외부 API 호출 없이 실제 국가법령정보 API 응답 형식과 동일한 고정 XML로 파싱만 검증한다.
"""
from app.services.law.api_service import _parse_expc_detail_xml, _parse_expc_search_xml, _parse_search_result

# 실제 lawSearch.do?target=law 응답 형식 (법령구분명 태그 — 과거 "법령종류명"으로
# 잘못 가정되어 law_type이 항상 빈 문자열로 파싱되던 버그의 회귀 방지용).
_LAW_SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LawSearch><totalCnt>1</totalCnt>
<law id="1"><법령일련번호>280405</법령일련번호><법령명한글><![CDATA[소득세법]]></법령명한글>
<공포일자>20251223</공포일자><소관부처명>재정경제부</소관부처명>
<법령구분명>법률</법령구분명></law>
</LawSearch>"""


def test_parse_search_result_extracts_law_type():
    laws, total = _parse_search_result(_LAW_SEARCH_XML)
    assert total == 1
    assert laws[0].law_type == "법률"


def test_parse_search_result_extracts_basic_fields():
    laws, _ = _parse_search_result(_LAW_SEARCH_XML)
    assert laws[0].mst == "280405"
    assert laws[0].law_name == "소득세법"
    assert laws[0].ministry == "재정경제부"


# ── 법령해석례(expc) XML 파싱 ──────────────────────────────────────

_EXPC_SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Expc><totalCnt>1</totalCnt>
<expc id="1"><법령해석례일련번호>312859</법령해석례일련번호>
<안건명><![CDATA[「소득세법」 제20조 관련 해석]]></안건명>
<안건번호>10-0075</안건번호><질의기관명></질의기관명>
<회신기관명>법제처</회신기관명><회신일자>2010.04.23</회신일자></expc>
</Expc>"""


def test_parse_expc_search_xml():
    results = _parse_expc_search_xml(_EXPC_SEARCH_XML)
    assert len(results) == 1
    assert results[0]["case_id"] == "312859"
    assert results[0]["case_no"] == "10-0075"
    assert results[0]["response_agency"] == "법제처"


_EXPC_DETAIL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ExpcService><법령해석례일련번호>312859</법령해석례일련번호>
<안건명><![CDATA[「소득세법」 제20조 관련 해석]]></안건명>
<안건번호>10-0075</안건번호><해석일자>20100423</해석일자>
<해석기관명>법제처</해석기관명>
<질의요지><![CDATA[질의 내용]]></질의요지>
<회답><![CDATA[회답 내용]]></회답>
<이유><![CDATA[이유 내용]]></이유>
</ExpcService>"""


def test_parse_expc_detail_xml():
    detail = _parse_expc_detail_xml(_EXPC_DETAIL_XML)
    assert detail["case_id"] == "312859"
    assert detail["question"] == "질의 내용"
    assert detail["answer"] == "회답 내용"
    assert detail["reasoning"] == "이유 내용"
