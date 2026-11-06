"""Official-answer gold set, figure check, delegated provisions and calibrated abstention (no database, no model)."""
import json
from dataclasses import replace

import pytest

from app.services import answer_risk, claim_verification as claims
from app.services.evidence import context_from_records, digest, record_from_result
from app.services.legal_figures import amounts, percents, periods, unsupported_figures
from app.services.search import hybrid_search_service as search
from evaluation import abstention_calibration as calibration
from evaluation import build_interpretation_gold as gold
from evaluation import gold_eval
from tests.test_reliability_workflow import context, draft, source


# ── figures ────────────────────────────────────────────────────────────────────

def test_statute_and_plain_ways_of_writing_a_figure_are_the_same_figure():
    assert percents("100분의 20을 곱한 금액, 1천분의 5") == {20.0, 0.5}
    assert amounts("4천800만원 미만, 1억 2천만원, 8,000만 원, 48,000,000원") == {48_000_000, 120_000_000, 80_000_000}
    assert periods("3월 이내, 2년 이상 보유, 매년 6월 1일") == {(3, "개월"), (2, "년")}


def test_a_figure_missing_from_the_cited_text_and_the_question_is_reported():
    cited = "말일부터 3개월 이내에 신고하여야 한다. 산출세액의 100분의 3을 공제한다. 4천800만원 미만이면 면제한다."
    assert unsupported_figures("3개월 이내 신고, 3% 공제, 4,800만 원 미만 면제", cited) == []
    assert unsupported_figures("6개월 이내 신고하면 5% 공제", cited) == ["5%", "6개월"]
    assert unsupported_figures("2억원 이하", cited, query="재산이 2억원인데") == []
    # A rate table stored as an image cannot be read, so rates are not checked against it.
    assert unsupported_figures("최고 50%", '<img src="rate-table.jpg"> 세율') == []


def test_a_rate_the_cited_article_does_not_contain_is_a_signal_for_the_judge():
    ctx = context()
    result = claims.check_claims(draft(ctx, "조건 충족 시 세율 30%를 적용합니다."), ctx, "질문")
    assert "figure_not_in_source" in result["C1"]
    assert claims.CHECKS["figure_not_in_source"].gate == "signal"
    assert "figure_not_in_source" not in claims.blocking_codes(result["C1"])
    assert claims.check_claims(draft(ctx, "조건 충족 시 적용합니다."), ctx, "질문")["C1"] == []


# ── delegated provisions and hidden interpretations ────────────────────────────

def test_an_article_leaving_a_requirement_to_the_decree_points_at_decree_articles_citing_it():
    statute = source(content="제89조\n① … 대통령령으로 정하는 요건을 충족하는 주택", law_name="소득세법", article_no="제89조")
    decree = source(content="제154조\n① … 기획재정부령으로 정하는 서류", law_name="소득세법 시행령", article_no="제154조")
    plain = source(content="제12조\n① 비과세한다.", law_name="소득세법", article_no="제12조")
    targets = search.delegation_targets([statute, decree, plain])
    assert targets == {"소득세법 시행령": {"(?<![가-힣])법 제89조(?![의0-9])"},
                       "소득세법 시행규칙": {"(?<![가-힣])영 제154조(?![의0-9])"}}


def test_an_evaluation_run_hides_the_interpretation_its_question_came_from():
    kept = source(source_type="interpretation", article_no="21-0001")
    hidden = source(source_type="interpretation", article_no="21-0469")
    statute = source(article_no="제19조")
    assert search._visible([kept, hidden, statute]) == [kept, hidden, statute]
    token = search.EXCLUDED_INTERPRETATIONS.set(frozenset({"21-0469"}))
    try:
        assert search._visible([kept, hidden, statute]) == [kept, statute]
    finally:
        search.EXCLUDED_INTERPRETATIONS.reset(token)


# ── gold set construction ──────────────────────────────────────────────────────

INTERPRETATION = """[질의요지]
직장어린이집을 위탁하여 운영하는 경우1)1) 단서에 해당하지 않는 경우로 전제함
, 「지방세특례제한법」 제19조제1항에 따라 취득세 면제 결정을 할 수 있는지?

< 질의 배경 >
  민원인은 이견이 있어 법령해석을 요청함.

[회답]
이 사안의 경우 지방자치단체의 장은 취득세 면제 결정을 할 수 없습니다.

[이유]
「지방세특례제한법」 제19조제1항에서는 …"""


def test_the_official_reply_and_its_verdict_come_from_the_stored_interpretation():
    parts = gold.sections(INTERPRETATION)
    question = gold.clean_question(parts["질의요지"])
    assert "전제함" not in question and "질의 배경" not in question and question.endswith("있는지?")
    assert gold.verdict(question, parts["회답"]) == "no"
    assert gold.verdict(question, "이 경우 감면받을 수 있습니다.") == "yes"
    assert gold.verdict(question, "가. 질의 가에 대해 할 수 있습니다. 나. …") is None
    assert gold.verdict("과세표준의 범위", "과세표준은 취득가액입니다.") is None


def test_a_reply_holds_today_when_the_paragraph_it_turns_on_reads_the_same():
    old = "제19조(어린이집) ① 유치원등에 대해서는 면제한다. <개정 2019.12.31>\n② 종전 규정"
    new = "제19조(어린이집)\n① 유치원등에 대해서는 면제한다. <개정 2023.3.14>\n② 바뀐 규정"
    assert gold.provision_text(gold.paragraph_text(old, {1})) == gold.provision_text(gold.paragraph_text(new, {1}))
    assert gold.provision_text(gold.paragraph_text(old, {2})) != gold.provision_text(gold.paragraph_text(new, {2}))
    assert gold.paragraph_text(old, set()) == old            # no paragraph cited: the whole article
    assert gold.paragraph_text(old, {5}) == old              # a paragraph that does not exist: the whole article
    assert gold.split_of("21-0469") == gold.split_of("21-0469") in {"dev", "test"}


# ── evaluation run (fake pipeline and judge) ───────────────────────────────────

CASE = {"id": "gold-21-0469", "interpretation": "21-0469", "split": "dev", "question": "면제할 수 있는지?",
        "official_answer": "할 수 없습니다.", "verdict": "no",
        "key_articles": [{"law": "지방세특례제한법", "article": "제19조"}], "validity": "unchanged"}


def verification(status="limited", uncovered=1):
    return {"status": status, "metrics": {"claims_total": 4, "claims_withheld": 1, "issues_total": 2, "issues_answered": 2},
            "claims": [{"id": "C1", "released": True, "signals": ["figure_not_in_source"]},
                       {"id": "C2", "released": True}],
            "coverage": {"I1": {"status": "missing" if uncovered else "sufficient",
                                "missing_requirements": ["지방세특례제한법 시행령 제8조"]},
                         "I2": {"status": "sufficient"}},
            "judge": {"claims": [{"claim_id": "C1", "verdict": "supported"}], "missing_issue_ids": []}}


@pytest.mark.asyncio
async def test_each_case_is_run_with_its_interpretation_hidden_and_judged_against_the_reply(tmp_path):
    seen = []

    async def observe(question):
        seen.append(search.EXCLUDED_INTERPRETATIONS.get())
        return {"answer": "면제 결정을 할 수 있습니다.", "verification": verification(),
                "contexts": [{"records": [{"law_name": "지방세특례제한법", "reference": "제19조"}]}], "elapsed_seconds": 3}

    async def call(messages):
        return {"outcome": "contradict", "answer_quote": "면제 결정을 할 수 있습니다.", "reason": "반대"}

    summary = await gold_eval.run([CASE], tmp_path, observe=observe, call=call)
    assert seen == [frozenset({"21-0469"})] and search.EXCLUDED_INTERPRETATIONS.get() == frozenset()
    row = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert row["outcome"] == "contradict" and row["key_article_found"] and row["coverage"]["I1"] == "missing"
    assert row["missing_requirements"] == ["지방세특례제한법 시행령 제8조"]
    assert row["figure_flags"] == [{"claim_id": "C1", "released": True, "judge": "supported"}]
    assert summary["summary"]["dev"]["wrong_conclusion_rate"] == 1.0
    assert summary["summary"]["dev"]["figure_flags_on_supported_claims"] == 1
    # Already recorded cases are not run (or paid for) again.
    await gold_eval.run([CASE], tmp_path, observe=None, call=None)


@pytest.mark.asyncio
async def test_a_judge_quote_that_is_not_in_the_answer_is_not_accepted():
    async def invented(messages):
        return {"outcome": "agree", "answer_quote": "답변에 없는 문장", "reason": "-"}
    result = await gold_eval.judge(CASE, "면제 결정을 할 수 없습니다.", call=invented)
    assert result["outcome"] == "error"
    assert (await gold_eval.judge(CASE, "", call=invented))["outcome"] == "no_conclusion"


# ── risk score and calibration ─────────────────────────────────────────────────

def test_the_risk_score_reads_only_the_verification_report(monkeypatch):
    features = answer_risk.risk_features(verification())
    assert features["uncovered"] == 0.5 and features["withheld"] == 0.25 and features["flagged"] == 0.5
    monkeypatch.setattr(answer_risk.config, "ANSWER_RISK_THRESHOLD", None)
    report = verification()
    assert answer_risk.apply_risk_policy("본문", report) == "본문" and report["risk"]["flagged"] is False
    monkeypatch.setattr(answer_risk.config, "ANSWER_RISK_THRESHOLD", 0.1)
    monkeypatch.setattr(answer_risk.config, "ANSWER_RISK_ACTION", "notice")
    assert answer_risk.apply_risk_policy("본문", report).startswith(answer_risk.RISK_NOTICE)
    monkeypatch.setattr(answer_risk.config, "ANSWER_RISK_ACTION", "hold")
    assert answer_risk.apply_risk_policy("본문", verification()) == answer_risk.RISK_HOLD
    low = verification(status="checked", uncovered=0)
    low["metrics"]["claims_withheld"], low["claims"][0]["signals"] = 0, []
    assert answer_risk.apply_risk_policy("본문", low) == "본문"


def rows(split, outcomes_scores):
    return [{"split": split, "outcome": o, "risk_scores": {"combined": s, "uncovered": 0.5}} for o, s in outcomes_scores]


def test_the_threshold_bounds_delivered_wrong_conclusions_on_the_development_split():
    dev = rows("dev", [("agree", 0.0)] * 30 + [("agree", 0.2)] * 10 + [("contradict", 0.6)] * 8 + [("agree", 0.6)] * 2)
    test = rows("test", [("agree", 0.0)] * 10 + [("contradict", 0.7)] * 3)
    result = calibration.calibrate(dev + test, alpha=0.1)
    assert result["score"] == "combined" and result["auc_dev"]["uncovered"] == 0.5
    assert result["threshold"] == 0.2
    assert result["dev"]["wrong_delivered"] == 0 and result["dev"]["wrong_before"] == 8
    assert result["test"]["wrong_delivered"] == 0 and result["test"]["delivered_without_notice"] == 10
    # Too few development cases for the requested alpha: no threshold is claimed.
    assert calibration.calibrate(rows("dev", [("agree", 0.0)] * 5), alpha=0.1)["threshold"] is None
