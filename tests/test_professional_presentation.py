"""Presentation must retain released text, qualifiers, dependencies and provenance."""
from app.schemas.reliability import AnswerClaim, AnswerDraft, ClaimCitation
from app.services import claim_verification as service
from tests.test_reliability_workflow import context


def claim(key, text, *, role="explanation", kind="legal", **kwargs):
    return AnswerClaim(id=key, issue_id="I1", text=text, kind=kind,
                       presentation_role=role, **kwargs)


def test_conclusion_is_shown_once_with_its_conditions_and_original_provenance():
    ctx = context()
    rows = [claim("C1", "업무 목적이 확인되는 범위에서 인정 여부를 검토합니다.", role="conclusion",
                  conditions=["실제 귀속자가 회사인지 확인해야 합니다."],
                  citations=[ClaimCitation(evidence_id=ctx.records[0].id, quote="조건을 충족한 경우에만 적용한다.")]),
            claim("C2", "업무 관련성: 지출 목적을 증빙과 대조합니다."),
            claim("C3", "귀속 판단: 개인 사용분은 구분해야 합니다.")]
    before = [row.model_dump() for row in rows]
    answer = service.render_structured_answer(rows, ctx)
    assert answer.startswith("## 핵심 판단")
    assert answer.count(rows[0].text) == 1
    assert answer.index(rows[0].conditions[0]) < answer.index("## 판단 근거")
    assert "[법률] 시험법 제1조" in answer
    assert [row.model_dump() for row in rows] == before


def test_display_role_cannot_release_a_rejected_claim_or_its_source():
    ctx = context()
    value = AnswerDraft(claims=[
        claim("C1", "차단된 확정 판단입니다.", role="conclusion"),
        claim("C2", "질문의 사실입니다.", kind="fact")])
    released, rejected = service.release_claims(
        value, {"C1": ["missing_evidence"], "C2": []}, None, ctx.plan, mode="shadow")
    assert "C1" in rejected
    answer = service.render_structured_answer(released, ctx)
    assert "차단된 확정 판단" not in answer
    assert "핵심 판단" not in answer


def test_fact_and_guidance_do_not_become_core_tax_conclusions():
    rows = [claim("C1", "사용자 진술입니다.", role="conclusion", kind="fact"),
            claim("C2", "증빙을 대조하세요.", role="conclusion", kind="guidance")]
    answer = service.render_structured_answer(rows, context())
    assert "핵심 판단" not in answer
    assert all(row.text in answer for row in rows)


def test_dependent_conclusion_stays_after_its_premise():
    rows = [claim("C1", "선행 요건을 확인합니다."),
            claim("C2", "따라서 해당 범위만 판단합니다.", role="conclusion", depends_on=["C1"])]
    answer = service.render_structured_answer(rows, context())
    assert answer.index(rows[0].text) < answer.index(rows[1].text)
    assert "핵심 판단" not in answer


def test_specific_conditions_containing_source_or_date_words_are_never_hidden():
    ctx = context()
    ctx.plan.dates = ["2025년"]
    specific = ["계약서 원문에 납품 조건이 기재되어 있어야 합니다.",
                "거래 시점의 사업자등록 상태를 확인해야 합니다.",
                "확보한 소득세법 원문만으로 원천징수 기한을 확정할 수 없습니다."]
    row = claim("C1", "제공된 기준의 설명입니다.", kind="source_summary",
                conditions=["2025년 적용 여부는 미확정입니다.", *specific])
    answer = service.render_structured_answer([row], ctx)
    assert all(condition in answer for condition in specific)
    assert answer.count("**적용 시점:**") == 1
    assert "2025년 적용 여부는 미확정입니다." not in answer


def test_live_generic_scope_variant_folds_once_but_rule_exclusions_stay_local():
    repeated = "확보한 원문 기준이며, 거래·사건의 적용 시점이 제시되지 않아 해당 연도 적용 여부는 미확정입니다."
    specific = "자동차 관련 업종 예외의 구체적 범위는 이 설명에 포함하지 않았습니다."
    rows = [claim("C1", "제공된 원문에 따른 첫 기준입니다.", kind="source_summary", role="conclusion",
                  conditions=[repeated]),
            claim("C2", "별개 기준입니다.", kind="source_summary", conditions=[repeated, specific])]
    answer = service.render_structured_answer(rows, context())
    assert repeated not in answer
    assert answer.count("**법령 적용:**") == 1
    assert specific in answer
    assert rows[0].conditions == [repeated]


def test_live_gift_scope_variants_and_role_transitions_keep_each_topic_clear():
    scope1 = "확보한 원문 기준이며, 거래 시점에 적용되는 법령 버전은 미확정입니다."
    scope2 = "확보한 원문 기준이며, 거래·사건 연도에 이 기준이 적용되는지는 미확정입니다."
    rows = [claim("C1", "제공된 기준입니다.", kind="source_summary", conditions=[scope1]),
            claim("C2", "자료 목록입니다.", kind="source_summary", role="checklist", conditions=[scope2]),
            claim("C3", "추가 공제 기준입니다.", kind="source_summary", conditions=[scope1])]
    answer = service.render_structured_answer(rows, context())
    assert scope1 not in answer and scope2 not in answer
    assert answer.count("**법령 적용:**") == 1
    assert answer.index("### 준비 자료") < answer.index(rows[1].text)
    assert answer.index(rows[1].text) < answer.index("### 판단 기준과 예외") < answer.index(rows[2].text)


def test_official_decree_category_maps_to_an_actionable_citation_label():
    ctx = context()
    ctx.records = tuple(record.model_copy(update={"category": "대통령령", "law_name": "시험법 시행령"})
                        for record in ctx.records)
    row = claim("C1", "원문 설명입니다.", citations=[ClaimCitation(evidence_id=ctx.records[0].id, quote="조건")])
    answer = service.render_structured_answer([row], ctx)
    assert "[시행령] 시험법 시행령 제1조" in answer
    assert "[대통령령]" not in answer


def test_procedure_keeps_question_order_and_steps_without_double_bullets():
    query = "공제 요건과 신고 절차를 설명해 주세요."
    rows = [claim("C1", "1. 신고자료를 확인하세요.\n2. 제출 절차를 확인하세요.",
                  role="procedure", question_part="신고 절차"),
            claim("C2", "공제 설명입니다.", question_part="공제 요건")]
    answer = service.render_structured_answer(rows, context(), query)
    assert answer.index(rows[1].text) < answer.index("### 신고·처리 절차") < answer.index(rows[0].text)
    assert "- 1." not in answer


def test_specific_procedure_heading_is_not_stacked_under_a_duplicate_generic_heading():
    row = claim("C1", "증여세 신고 방법: 정해진 서식으로 제출하세요.", role="procedure",
                conditions=["해당 연도 서식은 별도 확인이 필요합니다."])
    answer = service.render_structured_answer([row], context())
    assert answer.count("### ") == 1
    assert "### 증여세 신고 방법" in answer
    assert "### 신고·처리 절차" not in answer
    assert row.conditions[0] in answer


def test_short_question_keeps_a_direct_answer_without_forced_report_sections():
    row = claim("C1", "조건을 충족해야 합니다.", role="conclusion")
    answer = service.render_structured_answer([row], context())
    assert answer == row.text


def test_partial_answer_separates_actions_from_unresolved_tax_scope():
    ctx = context()
    ctx.plan.issues.append(ctx.plan.issues[0].model_copy(update={"id": "I2", "law": "부가가치세법"}))
    rows = [claim("C1", "확인된 조건 범위만 설명합니다.", role="conclusion"),
            claim("C2", "결제내역과 업무 자료를 대조하세요.", kind="guidance", role="checklist")]
    answer = service.render_structured_answer(rows, ctx)
    assert answer.index("## 실무 확인 사항") < answer.index(rows[1].text)
    assert answer.index(rows[1].text) < answer.index("## 추가 확인이 필요한 부분")
    assert "부가가치세에 필요한 근거" in answer
    assert answer.count(rows[0].text) == 1


def _two_subject_answer(query):
    from app.schemas.reliability import Issue, QuestionPlan
    from app.services.evidence import context_from_records
    base = context()
    plan = QuestionPlan(issues=[
        Issue(id="I1", request_quote="질문", subject="A", law="소득세법", question="질문"),
        Issue(id="I2", request_quote="질문", subject="B", law="부가가치세법", question="질문")])
    ctx = context_from_records(base.records, plan=plan)
    rows = [AnswerClaim(id="C1", issue_id="I1", text="A의 판단입니다.", kind="fact", presentation_role="explanation"),
            AnswerClaim(id="C2", issue_id="I2", text="B의 판단입니다.", kind="fact", presentation_role="explanation")]
    return service.render_structured_answer(rows, ctx, query)


def test_individual_subject_letter_is_not_labelled_as_a_company():
    answer = _two_subject_answer("A는 거주자이고 B는 사업자입니다. 각각 설명해 주세요.")
    assert "A회사" not in answer and "B회사" not in answer
    assert "A · 소득세" in answer


def test_company_suffix_is_kept_when_the_question_names_a_company():
    answer = _two_subject_answer("A회사는 B사로부터 세금계산서를 받았습니다.")
    assert "A회사 · 소득세" in answer and "B회사 · 부가가치세" in answer


def test_law_label_keeps_procedural_law_names_whole():
    assert [service.law_label(law) for law in
            ('소득세법', '법인세법', '부가가치세법', '상속세 및 증여세법', '국세기본법', '국세징수법',
             '조세범처벌법', '조세특례제한법', 'ALL')] == [
        '소득세', '법인세', '부가가치세', '상속세 및 증여세', '국세기본법', '국세징수법',
        '조세범처벌법', '조세특례제한법', '사실관계']


def test_withheld_answer_does_not_ask_for_a_date_it_never_needed():
    from app.schemas.reliability import Issue, QuestionPlan
    from app.services.evidence import context_from_records
    plan = QuestionPlan(issues=[Issue(id='I1', request_quote='질문', law='국세기본법', question='질문')],
                        missing_inputs=[service.DATE_INPUT, '과거 증여 내역'])
    ctx = context_from_records([], plan=plan)
    withheld = service.render_claims([], ctx)
    assert service.DATE_INPUT not in withheld and '과거 증여 내역' in withheld
    assert '국세기본법에 필요한 근거' in withheld and '국세기본에' not in withheld
    assert service.requested_inputs(ctx, []) == ['과거 증여 내역']
    answered = service.requested_inputs(ctx, [claim('C1', '설명입니다.')])
    assert answered == [service.DATE_INPUT, '과거 증여 내역']  # kept beside an actual answer
