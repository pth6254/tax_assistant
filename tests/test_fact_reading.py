"""Reading a calculation conversation: a fact the model lists is used only when the user's words prove it."""
from datetime import date

import pytest

from app.services.calculator import adjusted_areas as areas
from app.services.calculator import fact_reading as fr
from app.services.calculator.fact_reading import ReadFact, ReadFacts
from app.services.calculator.income_tax_inputs import stated_income_tax_inputs
from app.services.calculator.capital_gains_inputs import StatedInputs, stated_capital_gains_inputs

TODAY = date(2026, 11, 7)
BANPO = ["10년 보유한 아파트를 12억에 팔고 취득가는 7억이면 양도세 계산해줘", "1세대 1주택이야",
         "2014년 매입해서 2019년까지 거주하다가 지금까지 전세주고 있어"]


def read(tool, *rows):
    return ReadFacts(tool=tool, facts=[ReadFact(field=f, value=v, quote=q) for f, v, q in rows])


BANPO_READ = read("capital_gains",
                  ("transfer_price", "1200000000", "12억에 팔고"),
                  ("acquisition_price", "700000000", "취득가는 7억"),
                  ("holding_years", "10", "10년 보유한"),
                  ("residence_years", "5", "2014년 매입해서 2019년까지 거주"),   # the model counted: not in the words
                  ("expenses", "30000000", "중개수수료 3천만원"),                  # never said
                  ("acquisition_date", "2014", "2014년 매입해서"),
                  ("residence_end", "2019", "2019년까지 거주"),
                  ("lived", "false", "지금까지 전세주고 있어"),                   # rented out later: not "never lived"
                  ("is_one_home", "true", "1세대 1주택이야"))


def test_a_fact_is_kept_only_when_the_users_own_words_prove_it():
    proven = fr.prove(BANPO_READ, BANPO, today=TODAY)
    assert proven.facts == {"transfer_price": 1_200_000_000, "acquisition_price": 700_000_000, "holding_years": 10,
                            "acquisition_date": "2014", "residence_end": "2019", "is_one_home": True}
    assert {(f, reason) for f, _, _, reason in proven.rejected} == {
        ("residence_years", "not_in_quote"), ("expenses", "quote_not_in_conversation"), ("lived", "not_in_quote")}


def test_periods_given_as_dates_are_counted_by_code_and_the_2017_rule_settles_the_area():
    r = fr.reading(fr.prove(BANPO_READ, BANPO, today=TODAY), today=TODAY)
    assert r.lines["residence"] == "거주기간 4년"
    assert [a for a, _ in r.options["residence"]] == [{"residence_years": 4}, {"residence_years": 5}]
    assert r.lines["acquired_adjusted"] == "취득 당시 비조정"
    assert any("2017년 8월 2일 이전" in note for note in r.notes)
    # "10년 보유" and "2014년 매입" disagree (11~12 years by today): the stated years are used and the gap is said.
    assert r.lines["holding"] == "보유기간 10년" and any("다릅니다" in note for note in r.notes)
    stated = stated_capital_gains_inputs(r.text(), [{"role": "user", "content": "\n".join(BANPO)}])
    assert isinstance(stated, StatedInputs)
    assert stated.params["residence_years"] == 4 and stated.params["acquired_in_adjusted_area"] is False


def test_a_bare_yes_answers_only_the_fact_the_calculator_asked():
    texts = ["아파트 5억에 사서 8억에 팔았고 3년 보유했어. 1주택이야.", "거주는 안 했어", "네 맞아요"]
    reply = read("capital_gains", ("acquired_in_adjusted_area", "true", "네 맞아요"))
    asked = ["취득 당시 조정대상지역이었는지(예/아니오)"]
    assert fr.prove(reply, texts, asked, TODAY).facts == {"acquired_in_adjusted_area": True}
    assert fr.prove(reply, texts, [], TODAY).facts == {}
    assert fr.prove(reply, texts, ["보유기간 중 거주기간"], TODAY).facts == {}


@pytest.mark.parametrize("field, value, quote, kept", [
    ("acquired_in_adjusted_area", "false", "조정대상지역 아니야", True),
    ("acquired_in_adjusted_area", "true", "조정대상지역 아니야", False),   # the negation also holds the word
    ("is_one_home", "true", "집은 이거 하나야", True),
    ("is_one_home", "true", "두 채 중 하나를 팔았어", False),
    ("non_business_land", "true", "사업용으로 쓴 적 없고 그냥 놀리던 땅이야", True),
    ("has_spouse", "false", "부모님이 돌아가셔서", True),
    ("has_spouse", "false", "아버지가 돌아가셨어", False),                 # the person who died, not the spouse
    ("relation", "직계존비속", "엄마가 전세금 보태라고", True),
    ("relation", "배우자", "엄마가 전세금 보태라고", False),
])
def test_a_choice_needs_its_cue_words(field, value, quote, kept):
    tool = "gift" if field == "relation" else "inheritance" if field == "has_spouse" else "capital_gains"
    texts = [quote + " 팔았어 상속 증여"]
    assert (field in fr.prove(read(tool, (field, value, quote)), texts, today=TODAY).facts) is kept


@pytest.mark.parametrize("field, value, quote", [
    ("estate_value", "1800000000", "아파트 15억이랑 예금 3억"),     # a stated total
    ("children_count", "2", "어머니랑 나, 동생이"),
    ("children_count", "3", "자녀는 3명이고"),
    ("death_date", "2026-10", "지난달 돌아가셨어"),
])
def test_totals_counts_and_relative_dates_are_checked_against_the_words(field, value, quote):
    proven = fr.prove(read("inheritance", (field, value, quote)), [quote + " 상속"], today=TODAY)
    assert field in proven.facts


def test_numbers_that_the_words_do_not_hold_are_rejected():
    texts = ["엄마가 1억 보내줬어. 나 서른 살이야. 증여세 얼마야"]
    proven = fr.prove(read("gift", ("gift_amount", "100000000", "1억 보내줬어"), ("recipient_age", "30", "서른 살"),
                           ("prior_gifts_10y", "50000000", "1억 보내줬어")), texts, today=TODAY)
    assert proven.facts == {"gift_amount": 100_000_000, "recipient_age": 30}
    r = fr.reading(proven, today=TODAY)
    assert r.lines["minor"] == "성년"


def test_a_spoken_unit_proven_from_context_is_not_asked_again():
    texts = ["연봉 5천인 직장인인데 종합소득세 얼마 나오는지 계산해줘. 부양가족은 아내랑 애 하나야"]
    proven = fr.prove(read("income_tax", ("wage_income", "50000000", "연봉 5천"),
                           ("dependents", "2", "아내랑 애 하나")), texts, today=TODAY)
    r = fr.reading(proven, today=TODAY)
    stated = stated_income_tax_inputs(r.text(), [{"role": "user", "content": texts[0]}], basic_deduction=1_500_000)
    assert not hasattr(stated, "labels"), stated
    assert stated.params["wage_income"] == 50_000_000 and stated.params["personal_deduction_count"] == 3


def test_an_address_decides_the_adjusted_area_from_the_record():
    texts = ["서울 서초구에 아파트 한 채 있는데 2019년 3월에 9억에 사서 2026년 10월에 15억에 팔았어. 거주는 1년만 했어."]
    proven = fr.prove(read("capital_gains", ("house_location", "서울 서초구", "서울 서초구"),
                           ("acquisition_date", "2019-03", "2019년 3월에 9억에 사서"),
                           ("transfer_date", "2026-10", "2026년 10월에 15억에 팔았어"),
                           ("is_one_home", "true", "아파트 한 채")), texts, today=TODAY)
    r = fr.reading(proven, today=TODAY)
    assert r.lines["holding"] == "보유기간 7년" and r.lines["acquired_adjusted"] == "취득 당시 조정대상지역"
    multi = fr.prove(read("capital_gains", ("house_location", "마포구", "마포구"), ("is_one_home", "false", "두 채"),
                          ("transfer_date", "2026-10", "2026년 10월에")), ["집이 두 채인데 그중 마포구 아파트를 2026년 10월에 팔았어"],
                     today=TODAY)
    assert fr.reading(multi, today=TODAY).lines["transfer_adjusted"] == "양도일 현재 조정대상지역"


def test_the_tool_must_be_named_by_the_users_words():
    proven = fr.prove(read("inheritance", ("estate_value", "5000000000", "50억을")), ["50억을 받았어"], today=TODAY)
    assert proven.tool == "none"
    proven = fr.prove(read("inheritance", ("estate_value", "5000000000", "50억을")), ["부모님이 돌아가셔서 50억을 받았어"],
                      today=TODAY)
    assert proven.facts == {"estate_value": 5_000_000_000}


def test_the_designation_record_answers_a_month_and_a_later_day_with_its_limit():
    seoul = areas.find_area("마포구")
    value, note = areas.adjusted_on_transfer(seoul, (date(2026, 10, 1), date(2026, 10, 31)))
    assert value is True and "2026-10-01~2026-10-31" in note
    value, note = areas.adjusted_on_transfer(seoul, date(2026, 12, 15))
    assert value is True and "반영하지 못했습니다" in note
    # A month in which the status changed is not guessed.
    assert areas.adjusted_on_transfer(seoul, (date(2025, 10, 1), date(2025, 10, 31)))[0] is None
    assert areas.acquired_in_adjusted_area(None, (date(2015, 1, 1), date(2015, 12, 31)))[0] is False
    assert areas.find_area("부산 해운대") is not None
    assert areas.acquired_in_adjusted_area(areas.find_area("부산 해운대"), (date(2018, 1, 1), date(2018, 12, 31)))[0] is None


@pytest.mark.parametrize("tool, rows, reader, expected", [
    ("gift", [("gift_amount", "20000000", "2천만원을 줬어"), ("prior_gifts_10y", "10000000", "1천만원 받았어"),
              ("relation", "기타", "친구가")], "gift",
     {"gift_amount": 20_000_000, "prior_gifts_10y": 10_000_000, "relation": "기타"}),
    ("inheritance", [("estate_value", "1800000000", "아파트 15억이랑 예금 3억"), ("financial_assets", "300000000", "예금 3억"),
                     ("has_spouse", "true", "어머니랑"), ("children_count", "2", "나, 동생이")], "inheritance",
     {"estate_value": 1_800_000_000, "financial_assets": 300_000_000, "has_spouse": True, "children_count": 2}),
    ("vat", [("sales", "60000000", "매출이 6천만원"), ("purchases", "20000000", "세금계산서 받은 게 2천만원"),
             ("is_simplified", "false", "일반과세자야")], "vat",
     {"sales": 60_000_000, "purchases": 20_000_000, "is_simplified": False}),
    ("retirement", [("retirement_pay", "120000000", "퇴직금 1억 2천"), ("service_start", "2010-03", "2010년 3월에 입사"),
                    ("service_end", "2026-10", "2026년 10월에 퇴사")], "retirement",
     {"retirement_pay": 120_000_000, "service_years": 17}),
])
def test_every_standard_sentence_reads_back_as_the_same_input(tool, rows, reader, expected):
    """The rendered facts go through the tool's own reader; a label clash there would drop the whole case."""
    from app.services.calculator.gift_inputs import stated_gift_inputs
    from app.services.calculator.inheritance_inputs import stated_inheritance_inputs
    from app.services.calculator.retirement_inputs import stated_retirement_inputs
    from app.services.calculator.vat_inputs import stated_vat_inputs
    readers = {"gift": stated_gift_inputs, "inheritance": stated_inheritance_inputs, "vat": stated_vat_inputs,
               "retirement": stated_retirement_inputs}
    text = " ".join(q for _, _, q in rows) + {"gift": " 증여세", "inheritance": " 상속세", "vat": " 카페 부가세",
                                             "retirement": " 퇴직소득세"}[tool]
    r = fr.reading(fr.prove(read(tool, *rows), [text], today=TODAY), today=TODAY)
    stated = readers[reader](r.text(), [{"role": "user", "content": text}])
    assert stated is not None and not hasattr(stated, "labels"), (r.text(), stated)
    assert {k: stated.params[k] for k in expected} == expected


def test_both_parents_dead_leaves_no_spouse_in_the_reader():
    from app.services.calculator.inheritance_inputs import stated_inheritance_inputs
    stated = stated_inheritance_inputs("부모님이 돌아가셔서 상속재산 50억을 받았어. 자녀는 1명이야. 상속세 얼마야?")
    assert stated.params["has_spouse"] is False
