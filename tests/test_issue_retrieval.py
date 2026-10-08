"""Regression cases for scoped retrieval and evidence admission."""
from unittest.mock import AsyncMock
import json

import pytest

from app.schemas.reliability import Issue, QuestionPlan, AnswerDraft, AnswerClaim, ClaimCitation, JudgeReport, ClaimJudgment
from app.services import question_planning, issue_coverage, claim_verification
from app.services.evidence import context_from_records, record_from_result
from app.services.search.hybrid_search_service import (
    _embedding_queries, _fuse_issue_rankings, _rescue_title_hits, issue_keyword_terms,
)
from app.services.search import hybrid_search_service
from tests.test_reliability_workflow import source


@pytest.mark.asyncio
async def test_insufficient_issue_gets_targeted_retry_only(monkeypatch):
    monkeypatch.setattr(question_planning.config, "TAVILY_API_KEY", "")
    plan = QuestionPlan(issues=[
        Issue(id="I1", request_quote="질문", subject="H", law="법인세법", question="H 손금"),
        Issue(id="I2", request_quote="질문", subject="I", law="부가가치세법", question="I 매출세액"),
    ])
    search = AsyncMock(side_effect=lambda queries, law, **kwargs: [source(law_name=law)])
    rounds = 0

    async def assess(issues, records, scope_issues=None):
        nonlocal rounds
        rounds += 1
        return {issue.id: {
            "status": "missing" if issue.id == "I1" and rounds == 1 else "sufficient",
            "missing_requirements": ["손금 산입 요건"] if issue.id == "I1" and rounds == 1 else [],
            "relevant_ids": [row.id for row in records[issue.id]],
        } for issue in issues}

    monkeypatch.setattr(question_planning, "assess_issues", assess)
    result = await question_planning.retrieve_issues(plan, "질문", "user", search)
    assert search.call_count == 3
    assert search.call_args_list[-1].args[1] == "법인세법"
    assert "손금 산입 요건" in search.call_args_list[-1].args[0][0]
    assert {state["status"] for state in result.coverage.values()} == {"sufficient"}
    assert result.coverage["I1"]["attempts"] == 2


@pytest.mark.asyncio
async def test_retry_assessor_failure_preserves_prior_missing_result(monkeypatch):
    monkeypatch.setattr(question_planning.config, "TAVILY_API_KEY", "")
    plan = QuestionPlan(issues=[Issue(id="I1", request_quote="질문", law="법인세법", question="손금")])
    search = AsyncMock(return_value=[source(law_name="법인세법")])
    assess = AsyncMock(side_effect=[
        {"I1": {"status": "missing", "missing_requirements": ["손금 요건"], "relevant_ids": []}},
        {"I1": {"status": "unverified", "missing_requirements": [], "relevant_ids": [], "error": "ValueError"}},
    ])
    monkeypatch.setattr(question_planning, "assess_issues", assess)
    result = await question_planning.retrieve_issues(plan, "질문", "user", search)
    assert result.coverage["I1"]["status"] == "missing"
    assert result.coverage["I1"]["retry_assessment_error"] == "ValueError"


@pytest.mark.asyncio
async def test_coverage_rejects_invented_evidence_id(monkeypatch):
    issue = Issue(id="I1", request_quote="질문", law="법인세법", question="손금")
    record = record_from_result(source(law_name="법인세법"))
    monkeypatch.setattr(issue_coverage, "call_llm_structured", AsyncMock(return_value={"issues": [{
        "issue_id": "I1", "status": "sufficient", "relevant_evidence_ids": ["forged"],
        "missing_requirements": []}]}))
    report = await issue_coverage.assess_issues([issue], {issue.id: [record]})
    assert report["I1"]["status"] == "unverified"


@pytest.mark.asyncio
async def test_one_malformed_coverage_result_does_not_invalidate_another_issue(monkeypatch):
    first = Issue(id="I1", request_quote="질문", law="법인세법", question="손금")
    second = Issue(id="I2", request_quote="질문", law="부가가치세법", question="매입세액")
    records = {"I1": [record_from_result(source(law_name="법인세법"))],
               "I2": [record_from_result(source(law_name="부가가치세법", source_id="18"))]}

    async def judge(messages, schema, **kwargs):
        item = json.loads(messages[1]["content"])[0]
        if item["issue_id"] == "I2":
            return {"issues": []}
        return {"issues": [{"issue_id": "I1", "status": "sufficient",
                            "relevant_evidence_ids": [records["I1"][0].id],
                            "missing_requirements": []}]}

    monkeypatch.setattr(issue_coverage, "call_llm_structured", judge)
    result = await issue_coverage.assess_issues([first, second], records)
    assert result["I1"]["status"] == "sufficient"
    assert result["I2"]["status"] == "unverified"


def test_context_budget_does_not_silently_drop_an_issue():
    first = record_from_result(source(law_name="법인세법"))
    second = record_from_result(source(law_name="부가가치세법", source_id="18"))
    plan = QuestionPlan(issues=[Issue(id="I1", request_quote="질문", question="첫째"),
                                Issue(id="I2", request_quote="질문", question="둘째")])
    coverage = {"I1": {"status": "sufficient", "relevant_ids": [first.id], "evidence_ids": [first.id]},
                "I2": {"status": "sufficient", "relevant_ids": [second.id], "evidence_ids": [second.id]}}
    context = context_from_records([first, second], plan=plan, coverage=coverage)
    bounded = claim_verification.bounded_context(context, limit=len(first.text))
    assert len(bounded.records) == 1
    assert {state["status"] for state in bounded.coverage.values()} == {"sufficient", "missing"}
    assert "context_budget" in {state.get("error") for state in bounded.coverage.values()}


def test_keyword_and_vector_rankings_fuse_by_article_identity():
    legal = source(law_name="법인세법", article_no="제1조", similarity_score=0.8)
    lexical = source(law_name="법인세법", article_no="제1조", similarity_score=0.0)
    other = source(law_name="법인세법", article_no="제2조", similarity_score=0.7)
    result = _fuse_issue_rankings([[legal, other], [lexical]], 3)
    assert [row.article_no for row in result] == ["제1조", "제2조"]
    assert result[0].similarity_score == 0.8
    assert "가공거래" in issue_keyword_terms("H회사 가공거래 매입세액 확인", "부가가치세법")


def test_title_rescue_adds_official_statutes_without_displacing_fused_results():
    baseline = source(law_name="지방세법", article_no="제101조", source_id="101")
    corporation = source(law_name="법인세법", article_no="제72조", source_id="72",
                         content="제72조 [중소기업의 결손금 소급공제에 따른 환급]\n본문")
    income = source(law_name="소득세법", article_no="제85조의2", source_id="85",
                    content="제85조의2 [결손금 소급공제에 따른 환급]\n본문")
    forged = source(law_name="사용자 문서", article_no="제1조", source_id="upload",
                    content="제1조 [결손금 소급공제에 따른 환급]\n본문",
                    origin_kind="user_document")
    decree = source(law_name="법인세법 시행령", article_no="제110조", source_id="110",
                    content="제110조 [결손금 소급공제에 따른 환급]\n본문", priority=1)
    results, added = _rescue_title_hits(
        [baseline], [baseline, corporation, income, forged, decree],
        "상황 설명 " * 80 + "결손금 소급공제 신청 방법")
    assert results[0] is baseline
    assert len(added) == 2
    assert {row.source_id for row in added} == {"72", "85"}
    assert all(row.origin_kind == "official_law" and row.priority == 0 for row in added)


def test_qwen_query_instruction_is_opt_in(monkeypatch):
    monkeypatch.setattr(hybrid_search_service.config, "EMBEDDING_MODEL", "qwen3-embedding:4b")
    monkeypatch.setattr(hybrid_search_service.config, "SEARCH_QUERY_INSTRUCTION_ENABLED", False)
    assert _embedding_queries(["법인세법 결손금"]) == ["법인세법 결손금"]
    monkeypatch.setattr(hybrid_search_service.config, "SEARCH_QUERY_INSTRUCTION_ENABLED", True)
    assert _embedding_queries(["법인세법 결손금"])[0].endswith("Query: 법인세법 결손금")


def test_invoice_case_searches_receiver_and_supplier_separately():
    question = ("H건설회사는 I컨설팅회사로부터 경영컨설팅을 제공받고 세금계산서를 수취하였다. "
                "대금 5억 원을 지급했으나 실제 용역을 제공했는지 의심되며 가공거래로 판단될 경우 "
                "H와 I에 발생하는 법인세 및 부가가치세 문제를 설명하시오. " + "거래 실질 확인 자료. " * 8)
    plan = question_planning.fallback_plan(question, ["법인세법", "부가가치세법"])
    queries = {(issue.subject, issue.law): question_planning.issue_queries(issue, question)
               for issue in plan.issues if issue.subject}
    assert "손금" in queries[("H", "법인세법")][0]
    assert "익금" in queries[("I", "법인세법")][0]
    assert "매입세액" in queries[("H", "부가가치세법")][0]
    assert "매출세액" in queries[("I", "부가가치세법")][0]
    assert len({item for pair in queries.values() for item in pair}) == 8


def test_incomplete_issue_allows_only_semantically_supported_partial_claim():
    record = record_from_result(source(law_name="법인세법"))
    plan = QuestionPlan(issues=[Issue(id="I1", request_quote="질문", law="법인세법", question="손금 요건")])
    context = context_from_records([record], plan=plan, coverage={"I1": {
        "status": "missing", "evidence_ids": [record.id], "relevant_ids": [record.id]}})
    draft = AnswerDraft(claims=[AnswerClaim(id="C1", issue_id="I1", text="조건을 충족하면 적용합니다.",
                                            kind="legal", citations=[ClaimCitation(
                                                evidence_id=record.id, quote="조건을 충족한 경우에만 적용한다.")])])
    checks = claim_verification.check_claims(draft, context, "질문")
    assert checks == {"C1": []}
    supported = JudgeReport(claims=[ClaimJudgment(claim_id="C1", support="supported",
                                                  applicability="supported", evidence_ids=[record.id], reason="요건 부합")])
    released, _ = claim_verification.release_claims(draft, checks, supported, plan,
                                                     mode="shadow", coverage=context.coverage)
    assert [claim.id for claim in released] == ["C1"]
    withheld, reasons = claim_verification.release_claims(draft, checks, None, plan,
                                                           mode="shadow", coverage=context.coverage)
    assert not withheld and "semantic_check_not_passed" in reasons["C1"]
