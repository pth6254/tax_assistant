"""The displayed verification is bound to the released answer and its source."""

from app.services.answer_verification import verify_answer


CONTEXT = '[출처: 소득세법 | 소득세법 | 📌 법률 (law)]\n제1조 [목적]\n① 본문'


def test_verified_article_is_exposed_without_claiming_legal_application():
    answer = '[법률] 소득세법 제1조에 관한 설명입니다.'
    released, verification = verify_answer(answer, CONTEXT, require_law=True)
    assert released == answer
    assert verification['status'] == 'checked'
    assert verification['checks']['citation'] == 'checked'
    assert verification['checks']['legal_application'] == 'not_assessed'
    assert verification['citations'] == [
        {'label': '법률', 'law_name': '소득세법', 'reference': '제1조'}]


def test_rejected_article_never_appears_as_verified_evidence():
    generated = '[법률] 소득세법 제2조가 적용됩니다.'
    released, verification = verify_answer(generated, CONTEXT, require_law=True)
    assert generated not in released
    assert verification['status'] == 'withheld'
    assert verification['checks']['citation'] == 'failed'
    assert verification['citations'] == []


def test_calc_mismatch_is_withheld_and_not_marked_checked():
    released, verification = verify_answer('결정세액은 2,000원입니다.', '', '- 결정세액: 1,000원')
    assert '2,000원' not in released
    assert verification['status'] == 'withheld'
    assert verification['checks']['calculation'] == 'failed'
