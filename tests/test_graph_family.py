import pytest
from app.services.graph.family_service import verify_family
from app.services.graph.family_service import group_stored_families


def test_grouping_reports_unmatched_and_never_confuses_similar_names():
    complete, unmatched = group_stored_families(['시험법', '시험법 시행령', '시험법 시행규칙', '다른시험법 시행규칙'])
    assert complete == ['시험법']
    assert unmatched == ['다른시험법 시행규칙']


@pytest.mark.parametrize('reference', ['같은 법', '동법'])
def test_purpose_resolves_local_decree_reference(reference):
    rows = members()
    rows[2]['purpose'] = f'목적 「시험법」 및 {reference} 시행령에서 위임된 사항'
    assert len(verify_family(rows)) == 3


def test_explicit_alias_definitions_without_purpose_clause():
    rows = members()
    rows[2]['purpose'] = '제1조 다른 제목'
    rows[2]['alias_evidence'] = ['「시험법」(이하 "법"이라 한다) 제1조', '「시험법 시행령」(이하 "영"이라 한다) 제2조']
    links = verify_family(rows)
    assert [r['status'] for r in links] == ['purpose_verified', 'alias_verified', 'alias_verified']


def members():
    return [dict(law_id=str(i), law_name=name, purpose=purpose,
                 source_url='https://example.test', mst=str(i), published_on='20260101', effective_on='20260101')
            for i, (name, purpose) in enumerate([
                ('시험법', '목적'),
                ('시험법 시행령', '목적 「시험법」에서 위임된 사항'),
                ('시험법 시행규칙', '목적 「시험법」 및 「시험법 시행령」에서 위임된 사항')])]


def test_verified_family_has_three_distinct_links():
    links = verify_family(members())
    assert len(links) == 3
    assert {x['relation'] for x in links} == {'HAS_ENFORCEMENT_DECREE', 'HAS_ENFORCEMENT_RULE', 'HAS_IMPLEMENTING_RULE'}


def test_matching_names_alone_are_not_evidence():
    rows = members()
    rows[1]['purpose'] = '목적만 있고 근거 없음'
    with pytest.raises(ValueError):
        verify_family(rows)


def test_wrong_family_rejected():
    rows = members()
    rows[2]['law_name'] = '다른법 시행규칙'
    with pytest.raises(ValueError):
        verify_family(rows)
