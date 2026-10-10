"""Real-estate capital gains tax against the National Tax Service's published cases.

Each case is computed with the brackets printed for its year (2021~2022 or 2023~), so the
formula is checked independently of the current database rows.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.calculator import capital_gains as cg
from app.services.calculator.errors import CalculationError
from tests.test_calculator import _patch_repository

DATA = json.loads((Path(__file__).parent / "data" / "nts_capital_gains.json").read_text(encoding="utf-8"))


def params(brackets="brackets_2023"):
    p = DATA["parameters"]["statutory"]
    lower, bands = 0, []
    for band in DATA["parameters"][brackets]["bands"]:
        bands.append({"bracket_from": lower, "rate": Decimal(band["rate"]),
                      "progressive_deduction": band["progressive_deduction"]})
        lower = band["upper"]
    short = {(key.split("/")[0], int(key.split("/")[1])): Decimal(rate) for key, rate in p["short_rates"].items()}
    d = lambda key: Decimal(p[key])
    return cg.Parameters(
        brackets=bands, short_rates=short, basic_deduction=p["basic_deduction"],
        high_price_threshold=p["high_price_threshold"], general_rate=d("general_rate"), general_cap=d("general_cap"),
        home_holding_rate=d("home_holding_rate"), home_holding_cap=d("home_holding_cap"),
        home_residence_rate=d("home_residence_rate"), home_residence_cap=d("home_residence_cap"),
        surcharges={k: Decimal(v) for k, v in p["surcharges"].items()}, local_tax_ratio=d("local_tax_ratio"))


def step(result, prefix):
    found = [amount for label, amount in result.steps if label.startswith(prefix)]
    assert len(found) == 1, (prefix, result.steps)
    return found[0]


STEP = {"gain": "양도차익", "taxable_gain": "고가주택 과세대상 양도차익", "long_term_deduction": "장기보유특별공제",
        "income": "양도소득금액", "taxable": "과세표준"}


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["id"] for c in DATA["cases"]])
def test_matches_every_published_figure(case):
    result = cg.compute(params=params(case["brackets"]), **case["inputs"])
    for key, expected in case["expected"].items():
        actual = result.calculated_tax if key == "calculated_tax" else step(result, STEP[key])
        assert actual == expected, (case["id"], key, actual, expected)


def run(**inputs):
    inputs.setdefault("acquisition_price", 0)
    return cg.compute(params=params(), **inputs)


def test_one_home_at_or_below_the_threshold_is_exempt():
    result = run(transfer_price=1_200_000_000, acquisition_price=500_000_000, holding_years=2, is_one_home=True)
    assert result.method == "exempt" and result.calculated_tax == 0


def test_adjusted_area_home_needs_two_years_of_residence():
    common = dict(transfer_price=900_000_000, acquisition_price=600_000_000, holding_years=4, is_one_home=True,
                  acquired_in_adjusted_area=True)
    lived = run(residence_years=2, **common)
    not_lived = run(residence_years=1, **common)
    assert lived.method == "exempt"
    # Not exempt: the whole gain is taxed, with table 1 (residence under 2 years): 4 years 8%.
    assert not_lived.method == "taxed" and step(not_lived, "장기보유특별공제") == 24_000_000
    assert any("비과세 요건" in note for note in not_lived.notes)


def test_one_home_held_under_two_years_pays_the_short_term_house_rate():
    result = run(transfer_price=600_000_000, acquisition_price=500_000_000, holding_years=1, is_one_home=True)
    assert result.calculated_tax == 58_500_000   # (1억 - 250만) x 60%


def test_table_two_combines_holding_and_residence_with_caps():
    p = params()
    assert cg.long_term_rate(p, holding_years=5, residence_years=2, is_one_home=True, surcharged=False)[0] == Decimal("0.28")
    assert cg.long_term_rate(p, holding_years=12, residence_years=12, is_one_home=True, surcharged=False)[0] == Decimal("0.80")
    # Lived less than two years: table 1 even for a one-home household.
    assert cg.long_term_rate(p, holding_years=12, residence_years=1, is_one_home=True, surcharged=False)[0] == Decimal("0.24")
    assert cg.long_term_rate(p, holding_years=20, residence_years=0, is_one_home=False, surcharged=False)[0] == Decimal("0.30")
    assert cg.long_term_rate(p, holding_years=20, residence_years=0, is_one_home=False, surcharged=True)[0] == 0


def test_two_home_surcharge_adds_twenty_points_and_drops_the_deduction():
    result = run(transfer_price=500_000_000, acquisition_price=200_000_000, expenses=5_000_000, holding_years=5,
                 multi_home_surcharge="2주택")
    assert step(result, "장기보유특별공제") == 0
    # 292,500,000 x 38% - 19,940,000 + 292,500,000 x 20% = 91,210,000 + 58,500,000
    assert result.calculated_tax == 149_710_000
    assert any("중과" in note for note in result.notes)


def test_local_income_tax_is_shown_apart_from_the_national_tax():
    result = run(transfer_price=300_000_000, acquisition_price=150_000_000, expenses=26_500_000, holding_years=7,
                 asset_type="토지·건물")
    assert result.calculated_tax == 20_858_500
    assert step(result, "지방소득세") == 2_085_850
    assert step(result, "양도소득세와 지방소득세 합계") == 22_944_350


def test_a_loss_has_no_tax():
    result = run(transfer_price=300_000_000, acquisition_price=400_000_000)
    assert result.method == "no_gain" and result.calculated_tax == 0


@pytest.mark.parametrize("inputs,code", [
    (dict(holding_years=3, residence_years=4), "invalid_input"),
    (dict(holding_years=3, asset_type="토지·건물", is_one_home=True), "invalid_input"),
    (dict(holding_years=3, is_one_home=True, multi_home_surcharge="2주택"), "invalid_input"),
    (dict(holding_years=3, asset_type="토지·건물", multi_home_surcharge="2주택"), "invalid_input"),
    (dict(holding_years=3, asset_type="분양권"), "unsupported_condition"),
])
def test_inconsistent_inputs_are_rejected(inputs, code):
    with pytest.raises(CalculationError) as error:
        run(transfer_price=500_000_000, **inputs)
    assert error.value.code == code


@pytest.mark.asyncio
async def test_calculate_reads_every_statutory_figure_from_the_database():
    with _patch_repository(cg):
        result = await cg.calculate(transfer_price=1_500_000_000, acquisition_price=431_800_000, expenses=17_200_000,
                                    holding_years=7, is_one_home=True, residence_years=5)
    assert result.calculated_tax == result.final_tax == 21_941_400
    assert any("지방소득세" in note for note in result.notes)


def test_consultation_case_asks_only_the_facts_that_apply():
    from app.services.consultation_case_service import _active_question_specs, _questions
    keys = lambda facts: [q[0] for q in _active_question_specs('capital_gains', facts)]
    assert 'residence_years' not in keys({'asset_type': '토지·건물'})
    assert 'multi_home_surcharge' not in keys({'asset_type': '주택', 'is_one_home': True})
    assert 'residence_years' not in keys({'asset_type': '주택', 'is_one_home': False})
    # A choice stored before the asset types were split is asked again, not reused.
    legacy = {q['key']: q['answered'] for q in _questions({'asset_type': '부동산'}, 'capital_gains')}
    assert legacy['asset_type'] is False
