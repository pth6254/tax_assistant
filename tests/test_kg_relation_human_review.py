from copy import deepcopy

import pytest

from evaluation.kg_relation_human_review import finalize, prepare
from evaluation.kg_relation_review import make_cards
from evaluation.kg_relation_score import score
from evaluation.schema import digest
from tests.test_tax_knowledge import sample


def fixture_pool():
    version, article = sample()
    cards = make_cards(version, [article], max_per_kind=1)
    return {'schema_version': '1.0', 'purpose': 'human_relation_review_pool',
            'gold_labels': False, 'cards': cards}


def completed_form(pool):
    form = prepare(pool)
    for row in form['cards']:
        row['review'].update({
            'label': 'supported', 'reason': '원문이 대상을 명시합니다.',
            'reviewer': 'reviewer-a', 'reviewed_on': '2026-09-26',
            'source_verified': True, 'temporal_status': 'unresolved',
            'temporal_note': '인용 대상 버전은 별도 확인 필요',
            'hard_negative': False, 'confusion': None,
        })
    return form


def test_blind_form_hides_construction_and_judge_output():
    pool = fixture_pool()
    form = prepare(pool)
    assert form == prepare(pool)
    assert form['pool_hash'] == digest(pool)
    assert len(form['cards']) == len(pool['cards'])
    assert all('candidate_type' not in card and 'source_assertion_key' not in card
               and 'consensus' not in card for card in form['cards'])
    assert all(set(card['review'].values()) == {None} for card in form['cards'])


def test_completed_form_exports_score_compatible_gold_without_temporal_conflation():
    pool = fixture_pool()
    gold = finalize(pool, completed_form(pool))
    assert gold['purpose'] == 'human_relation_gold'
    assert gold['pool_hash'] == digest(pool)
    assert len(gold['reviews']) == len(pool['cards'])
    assert all(row['reviewer_kind'] == 'human' and row['temporal_status'] == 'unresolved'
               and row['label'] == 'supported' for row in gold['reviews'])
    report = {'pool_hash': digest(pool), 'advisory_only': True, 'gold_labels': False,
              'results': [{'assertion_key': row['assertion_key'], 'consensus': 'supported'}
                          for row in gold['reviews']]}
    assert score(pool, report, gold)['gold_labels'] == len(pool['cards'])


@pytest.mark.parametrize('change, error', [
    (lambda form: form['cards'][0]['review'].update(label=None), 'Human label'),
    (lambda form: form['cards'][0]['review'].update(source_verified=False), 'Human label'),
    (lambda form: form['cards'][0]['review'].update(temporal_note=None), 'temporal note'),
    (lambda form: next(card for card in form['cards'] if card['kind'] == 'CITES')
     ['review'].update(temporal_status='not_applicable'), 'target version'),
    (lambda form: form['cards'][0]['review'].update(hard_negative=True), 'Hard negative'),
    (lambda form: form['cards'][0]['source'].update(quote='tampered'), 'source or card'),
    (lambda form: form['cards'].pop(), 'every source card'),
])
def test_incomplete_or_tampered_form_cannot_become_gold(change, error):
    pool = fixture_pool()
    form = deepcopy(completed_form(pool))
    change(form)
    with pytest.raises(ValueError, match=error):
        finalize(pool, form)
