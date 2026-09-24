import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evaluation.precedent_pilot import QUESTIONS, prepare


def source_fixture(tmp_path):
    cases = []
    for pid in QUESTIONS:
        case = SimpleNamespace(id='precedent-' + pid,
            input={'review_card': {'case_number': pid}},
            rubric=[SimpleNamespace(instruction=''), SimpleNamespace(instruction='')])
        cases.append(case)
        (tmp_path / (pid + '.json')).write_text(json.dumps({'PrecService': {
            '사건번호': pid, '판결요지': 'reference<br/>complete ending'}}), encoding='utf-8')
    (tmp_path / 'draft-cards.json').write_text('{}', encoding='utf-8')
    return SimpleNamespace(cases=cases)


def test_pilot_keeps_complete_reference_separate_from_question(tmp_path):
    dataset = source_fixture(tmp_path)
    with patch('evaluation.precedent_pilot.Dataset.model_validate_json', return_value=dataset):
        actual, hashes = prepare(tmp_path)
    assert len(hashes) == 5
    for case in actual.cases:
        assert case.input['context'] == 'reference\ncomplete ending'
        assert 'complete ending' not in case.input['query']
        assert len(hashes[case.id.removeprefix('precedent-')]) == 64


def test_pilot_rejects_mismatched_source(tmp_path):
    dataset = source_fixture(tmp_path)
    dataset.cases[0].input['review_card']['case_number'] = 'wrong'
    with patch('evaluation.precedent_pilot.Dataset.model_validate_json', return_value=dataset):
        with pytest.raises(ValueError, match='case number mismatch'):
            prepare(tmp_path)
