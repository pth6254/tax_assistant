from copy import deepcopy

import pytest

from evaluation.history_audit import passed


def good_result():
    return dict(errors={}, complete_without_snapshot=0, blank_article_bodies=0,
                coverage=[dict(discovery_status='complete', expected_count=2,
                               listed=2, collected=2, pending=0, failed=0)],
                official_samples=[dict(raw_hash_match=True, parsed_match=True) for _ in range(3)])


def test_complete_integrity_gate():
    assert passed(good_result())


@pytest.mark.parametrize('field,value', [('pending', 1), ('failed', 1),
    ('collected', 1), ('expected_count', 3), ('discovery_status', 'pending')])
def test_incomplete_collection_never_passes(field, value):
    result = good_result()
    result['coverage'][0][field] = value
    assert not passed(result)


@pytest.mark.parametrize('field,value', [('errors', {'xml_hash': 1}),
    ('complete_without_snapshot', 1), ('blank_article_bodies', 1),
    ('coverage', []), ('official_samples', [])])
def test_missing_or_corrupt_data_never_passes(field, value):
    result = deepcopy(good_result())
    result[field] = value
    assert not passed(result)


def test_official_mismatch_never_passes():
    result = good_result()
    result['official_samples'][0]['raw_hash_match'] = False
    assert not passed(result)
