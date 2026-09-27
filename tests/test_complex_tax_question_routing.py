"""A fact pattern asking for tax analysis is not an exact article lookup."""

from app.services.tools.planner import has_calculation_intent, has_tool_intent
from app.services.law.reference_parser import extract_law_reference
import re


def test_consulting_invoice_fact_pattern_does_not_force_a_tool():
    query = (
        "H건설회사는 I컨설팅회사로부터 총 5억 원의 경영컨설팅을 제공받았다고 주장하면서 "
        "세금계산서를 수취하였다. 그러나 세무조사 결과 I회사는 직원이 1명뿐이고 별도의 "
        "사무실도 존재하지 않았다. 컨설팅 보고서는 약 20페이지이며 내용 대부분이 인터넷에서 "
        "확인할 수 있는 일반적인 시장자료였다. H사는 컨설팅 대금 5억 원을 지급한 직후 "
        "I회사의 대표가 해당 금액 중 4억 원을 현금으로 인출했다. "
        "해당 거래의 실질을 판단하기 위해 어떤 자료를 확인해야 하는가? "
        "거래가 가공거래로 판단되는 경우 H회사와 I회사에 각각 발생할 수 있는 법인세 및 "
        "부가가치세 문제를 설명하시오."
    )
    assert not has_calculation_intent(query)
    assert extract_law_reference(query) is None
    assert re.search(r"원문|조문|문서|서류|계약서|업로드|첨부|PDF|pdf", query) is None
    assert not has_tool_intent(query)
