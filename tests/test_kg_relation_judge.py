from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import date

import pytest
import config

from evaluation.kg_relation_judge import (RelationVerdict, assess, count_attempts, evaluate,
                                          validate_pool, verify_card)
from evaluation.kg_relation_review import challenge_cards, collect_auto, make_cards
from evaluation.kg_relation_score import score
from evaluation.schema import digest
from tests.test_tax_knowledge import sample


def fixture_card():
    version, article = sample()
    card = make_cards(version, [article], max_per_kind=1)[0]
    return version, article, card


def test_exact_source_reconstruction_and_tampering():
    version, article, card = fixture_card()
    assert verify_card(card, version, [article])
    card['source']['quote'] = 'forged'
    with pytest.raises(ValueError, match='drift'):
        verify_card(card, version, [article])


def test_challenge_is_reproducible_but_unlabelled():
    version, article = sample()
    extracted = make_cards(version, [article], max_per_kind=5)
    challenges = challenge_cards(extracted, max_per_kind=2)
    assert challenges and challenges == challenge_cards(extracted, max_per_kind=2)
    assert all(card['review']['status'] == 'unreviewed' for card in challenges)
    assert all(verify_card(card, version, [article]) for card in challenges)
    challenges[0]['claim']['target'] = '위조된 대상'
    with pytest.raises(ValueError, match='challenge'):
        verify_card(challenges[0], version, [article])


def test_unreviewed_pool_only():
    _, _, card = fixture_card()
    pool = {'schema_version': '1.0', 'purpose': 'human_relation_review_pool',
            'gold_labels': False, 'cards': [card]}
    validate_pool(pool)
    card['review']['status'] = 'approved'
    with pytest.raises(ValueError, match='unreviewed'):
        validate_pool(pool)


def test_provider_strict_schema_requires_every_output_field():
    assert set(RelationVerdict.model_json_schema()['required']) == {
        'verdict', 'reason', 'evidence_quote'}


@pytest.mark.asyncio
async def test_judge_requires_exact_evidence_and_never_grants_gold():
    _, _, card = fixture_card()
    quote = card['source']['quote'][:10]
    provider = SimpleNamespace(structured=AsyncMock(side_effect=[
        {'verdict': 'supported', 'reason': '본문에서 확인됨', 'evidence_quote': quote},
        {'verdict': 'supported', 'reason': '동일한 표현', 'evidence_quote': quote},
    ]))
    result = await assess(provider, card)
    assert result['consensus'] == 'supported'
    assert result['status'] == 'advisory_only'
    assert result['temporal_applicability'] == 'not_assessed'
    assert card['review']['status'] == 'unreviewed'


@pytest.mark.asyncio
async def test_judge_invented_quote_and_disagreement_not_consensus():
    _, _, card = fixture_card()
    provider = SimpleNamespace(structured=AsyncMock(side_effect=[
        {'verdict': 'supported', 'reason': '추정', 'evidence_quote': '원문에 없는 문구'},
        {'verdict': 'uncertain', 'reason': '불명확', 'evidence_quote': ''},
    ]))
    result = await assess(provider, card)
    assert result['consensus'] is None
    assert result['status'] == 'partial_model_error'
    assert result['runs'][0] == {'verdict': 'error', 'error_type': 'ValueError'}


@pytest.mark.asyncio
async def test_source_drift_blocks_model_call(monkeypatch):
    from evaluation import kg_relation_judge

    version, article, card = fixture_card()
    card['source']['article_hash'] = 'changed'
    pool = {'schema_version': '1.0', 'purpose': 'human_relation_review_pool',
            'gold_labels': False, 'cards': [card]}
    monkeypatch.setattr(kg_relation_judge, 'source_version',
                        AsyncMock(return_value=(version, [article])))
    monkeypatch.setattr(kg_relation_judge, 'close_pool', AsyncMock())
    provider = SimpleNamespace(structured=AsyncMock())
    result = await evaluate(pool, provider)
    assert result['results'][0]['status'] == 'source_blocked'
    assert result['neo4j_review_unchanged'] is True
    provider.structured.assert_not_called()


@pytest.mark.asyncio
async def test_batch_resume_reuses_completed_card(monkeypatch):
    from evaluation import kg_relation_judge

    version, article = sample()
    cards = make_cards(version, [article], max_per_kind=2)
    pool = {'schema_version': '1.0', 'purpose': 'human_relation_review_pool',
            'gold_labels': False, 'cards': cards[:2]}
    monkeypatch.setattr(kg_relation_judge, 'source_version',
                        AsyncMock(return_value=(version, [article])))
    monkeypatch.setattr(kg_relation_judge, 'close_pool', AsyncMock())
    provider = SimpleNamespace(structured=AsyncMock(return_value={
        'verdict': 'uncertain', 'reason': '판정 유보', 'evidence_quote': ''}))
    prior = [{'assertion_key': cards[0]['assertion_key'], 'status': 'advisory_only',
              'runs': [{'verdict': 'supported'}], 'consensus': 'supported'}]
    checkpoints = []
    result = await evaluate(pool, provider, repeats=1, existing_results=prior,
                            progress=lambda rows, total: checkpoints.append((len(rows), total)))
    assert provider.structured.await_count == 1
    assert checkpoints == [(2, 2)]
    assert result['results'][0] == prior[0]
    assert result['results'][1]['consensus'] == 'uncertain'


@pytest.mark.asyncio
async def test_interruption_resumes_without_recalling_completed_card(monkeypatch):
    from evaluation import kg_relation_judge

    version, article = sample()
    cards = make_cards(version, [article], max_per_kind=2)[:2]
    pool = {'schema_version': '1.0', 'purpose': 'human_relation_review_pool',
            'gold_labels': False, 'cards': cards}
    monkeypatch.setattr(kg_relation_judge, 'source_version',
                        AsyncMock(return_value=(version, [article])))
    monkeypatch.setattr(kg_relation_judge, 'close_pool', AsyncMock())
    provider = SimpleNamespace(structured=AsyncMock(return_value={
        'verdict': 'uncertain', 'reason': '검수 필요', 'evidence_quote': ''}))
    saved = []
    def interrupt_after_checkpoint(rows, total):
        saved[:] = [dict(row) for row in rows]
        raise RuntimeError('interrupted after durable checkpoint')
    with pytest.raises(RuntimeError, match='interrupted'):
        await evaluate(pool, provider, repeats=1, progress=interrupt_after_checkpoint)
    assert len(saved) == 1
    resumed = await evaluate(pool, provider, repeats=1, existing_results=saved)
    assert len(resumed['results']) == 2
    assert provider.structured.await_count == 2


def test_relation_judge_provider_settings_are_independent(monkeypatch):
    monkeypatch.setenv('KG_JUDGE_PROVIDER', 'ollama')
    monkeypatch.setenv('KG_JUDGE_MODEL', 'local-reviewer')
    monkeypatch.setenv('KG_JUDGE_BASE_URL', 'http://localhost:11434')
    monkeypatch.setenv('KG_JUDGE_MAX_TOKENS', '700')
    settings = config._kg_judge_settings()
    assert (settings.provider, settings.model, settings.max_tokens) == ('ollama', 'local-reviewer', 700)
    assert settings.api_key == config.LLM_API_KEY


def test_provider_usage_snapshot_preserves_missing_cost():
    from app.services.inference.llm.openai_compatible import OpenAICompatibleLLMProvider

    provider = OpenAICompatibleLLMProvider.__new__(OpenAICompatibleLLMProvider)
    provider.provider, provider.model, provider._usage_totals = 'openrouter', 'example', {}
    provider._record_usage({'usage': {'prompt_tokens': 10, 'completion_tokens': 4}})
    provider._record_usage({'usage': {'prompt_tokens': 2, 'cost': 0.001}})
    assert provider.usage_snapshot() == {
        'prompt_tokens': 12, 'completion_tokens': 4, 'cost': 0.001}
    provider._usage_totals.pop('cost')
    assert 'cost' not in provider.usage_snapshot()


def test_retry_attempt_total_includes_previous_failed_call():
    rows = [{'assertion_key': 'ok', 'runs': [{'verdict': 'supported'}]},
            {'assertion_key': 'failed', 'runs': [{'verdict': 'supported'}]}]
    assert count_attempts(2, {'ok'}, rows) == 3


@pytest.mark.asyncio
async def test_automatic_sampling_excludes_future_versions(monkeypatch):
    from evaluation import kg_relation_review

    names = ['국세기본법', '국세기본법 시행령', '국세기본법 시행규칙']
    laws = [dict(law_id=str(index), law_name=name, first_date=date(2015, 1, 1))
            for index, name in enumerate(names, 1)]
    version_rows = [[dict(id=index * 100 + offset, effective_date=day)
                     for offset, day in enumerate((date(2015, 1, 1),
                                                   date(2026, 1, 1), date(2028, 1, 1)), 1)]
                    for index in range(1, 4)]
    pool = AsyncMock()
    pool.fetch.side_effect = [laws, *version_rows]
    monkeypatch.setattr(kg_relation_review, 'get_pool', AsyncMock(return_value=pool))
    monkeypatch.setattr(kg_relation_review, 'close_pool', AsyncMock())
    _, article = sample()
    async def source(version_id, *, allow_empty=False):
        index = version_id // 100
        return (dict(id=version_id, law_id=str(index), law_name=names[index - 1],
                     law_type='test', snapshot_id=version_id + 1000,
                     source_url='https://www.law.go.kr/', effective_date=date(2015, 1, 1)
                     if version_id % 100 == 1 else date(2026, 1, 1)), [article])
    monkeypatch.setattr(kg_relation_review, 'source_version', source)
    result = await collect_auto(laws_per_level=1, per_kind=1, challenge_per_kind=0,
                                as_of=date(2026, 9, 26))
    assert {row['version_id'] for row in result['scopes']} == {
        101, 102, 201, 202, 301, 302}
    assert result['coverage']['eras']['old'] > 0
    assert result['coverage']['eras']['recent'] > 0
    assert all(row['source']['effective_date'] <= '2026-09-26' for row in result['cards'])


@pytest.mark.asyncio
async def test_input_budget_and_provider_error_do_not_leak_text():
    _, _, card = fixture_card()
    provider = SimpleNamespace(structured=AsyncMock(side_effect=RuntimeError('secret')))
    assert (await assess(provider, card, input_budget_bytes=1))['status'] == 'input_over_budget'
    provider.structured.assert_not_called()
    result = await assess(provider, card, repeats=1)
    assert result['status'] == 'model_error'
    assert result['runs'][0]['error_type'] == 'RuntimeError'
    assert 'secret' not in str(result)


def test_human_gold_scoring_keeps_abstentions_and_hard_negatives_separate():
    _, _, card = fixture_card()
    pool = {'cards': [card]}
    report = {'pool_hash': digest(pool), 'advisory_only': True, 'gold_labels': False, 'results': [
        {'assertion_key': card['assertion_key'], 'consensus': 'supported'}]}
    gold = {'schema_version': '1.0', 'purpose': 'human_relation_gold',
            'pool_hash': digest(pool), 'reviews': [{
                'assertion_key': card['assertion_key'], 'label': 'unsupported',
                'reviewer_kind': 'human', 'reviewer': 'domain-reviewer',
                'reviewed_on': '2026-09-26', 'reason': '관계가 원문에 없음',
                'hard_negative': True, 'confusion': 'same_terms'}]}
    result = score(pool, report, gold)
    assert result['accuracy_on_decided'] == 0
    assert result['hard_negative_false_support_rate'] == 1
    report['results'][0]['consensus'] = None
    assert score(pool, report, gold)['decision_coverage'] == 0
    gold['reviews'][0]['reviewer_kind'] = 'model'
    with pytest.raises(ValueError, match='human'):
        score(pool, report, gold)


def test_no_human_gold_never_produces_accuracy():
    pool = {'cards': []}
    report = {'pool_hash': digest(pool), 'advisory_only': True, 'gold_labels': False, 'results': []}
    gold = {'schema_version': '1.0', 'purpose': 'human_relation_gold',
            'pool_hash': digest(pool), 'reviews': []}
    result = score(pool, report, gold)
    assert result['status'] == 'insufficient_human_gold'
    assert result['accuracy_on_decided'] is None
