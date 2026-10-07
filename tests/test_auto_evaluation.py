"""Source fidelity, label isolation, resumption and public-only upload contracts."""
from copy import deepcopy
import asyncio
from datetime import date
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.law.history_parser import sha
from app.services.law.parser_service import parse_articles
from evaluation.auto_cards import (build, check_draft, load_cards, save_json,
                                   source_data, source_groups, structured)
from evaluation.auto_langsmith import prepare, publish_automatic
from evaluation.auto_pipeline import (AnswerAssessment, SEMANTIC, assess, case_status,
    mechanical, run, summarize, validate_assessment, validate_experiment)
from evaluation.card_schema import (CardDataset, CardDraft, CardReview, FrozenCard,
    REVIEW_DIMENSIONS, RuleBook, Source, SourcePackage)
from evaluation.card_sources import validate_snapshot
from evaluation.schema import digest


XML = '''<법령><기본정보><법령ID>001</법령ID><법령명_한글>법인세법</법령명_한글>
<시행일자>20200101</시행일자><공포일자>20190101</공포일자></기본정보>
<조문><조문단위><조문번호>19</조문번호><조문여부>조문</조문여부>
<조문제목>손금의 범위</조문제목><조문내용>실제 사업과 관련된 비용을 확인한다.</조문내용>
<항><항번호>①</항번호><항내용>사업과 관련하여 발생한 비용의 요건을 확인한다.</항내용></항>
</조문단위></조문></법령>'''


@pytest.fixture
def card_files(tmp_path):
    root = tmp_path / 'cards'
    (root / 'snapshots').mkdir(parents=True)
    (root / 'snapshots/1.xml').write_bytes(XML.encode('utf-8'))
    text = parse_articles(XML)[0].article_text
    source = Source(id='S1:제19조', law='법인세법', reference='제19조', version='25:2020-01-01',
        effective_from=date(2020, 1, 1), source_url='https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=25&efYd=20200101',
        text=text, text_hash=sha(text), snapshot_id=1, snapshot_hash=sha(XML),
        snapshot_file='snapshots/1.xml', law_id='001', mst='25', promulgation_date=date(2019, 1, 1))
    package = SourcePackage(id='corporate-general', tax='corporate', case_type='general',
                            as_of=date(2026, 10, 4), sources=[source])
    citation = {'source_id': source.id, 'quote': text.splitlines()[-1]}
    rules = RuleBook.model_validate({'rules': [{'id': 'rule1', 'subject': '법인 A',
        'conditions': ['사업 관련 비용'], 'effect': '요건 확인', 'exceptions': [],
        'needed_facts': ['사업 관련성'], 'citations': [citation]}], 'unresolved': []})
    draft = CardDraft.model_validate({'question': '법인 A는 실제 사업과 관련된 비용을 지출했습니다. 손금 요건을 설명해 주세요.',
        'facts': [{'id': 'f1', 'text': '실제 사업과 관련된 비용을 지출했습니다.'}], 'event_dates': [],
        'issues': [{'id': 'i1', 'subject': '법인 A', 'tax': 'corporate', 'request_quote': '손금 요건을 설명해 주세요.',
            'rule_ids': ['rule1'], 'expected_behavior': 'answer', 'missing_inputs': [],
            'required': [{'id': 'e1', 'statement': '사업 관련성 확인', 'conditions': ['관련 비용'],
                'pass_if': '요건 설명', 'fail_if': '무조건 부인', 'citations': [citation]}], 'forbidden': []}]})
    review = CardReview.model_validate({'items': [{'dimension': key, 'verdict': 'pass',
        'reason': '합성 계약', 'citations': [citation]} for key in REVIEW_DIMENSIONS]})
    card = FrozenCard(id='auto-corporate-general', group='one', split='dev', package_id=package.id,
        package_hash=digest(package.model_dump(mode='json')), rules=rules, draft=draft,
        review=review, builder_version='test', model='synthetic', prompt_hash='test')
    dataset = CardDataset(packages=[package], cards=[card], failures=[], metadata={})
    save_json(root / 'cards.json', dataset.model_dump(mode='json'))
    return SimpleNamespace(root=root, source=source, package=package, rules=rules, draft=draft,
                           review=review, card=card, dataset=dataset)


def observation(files):
    source = files.source
    return {'answer': '사업 관련성과 비용의 요건을 확인해야 합니다.', 'error': None, 'elapsed_seconds': 1.5,
        'verification': {}, 'tool_events': [], 'retrieval': [], 'generation': [],
        'contexts': [{'records': [{'id': 'E1', 'origin': 'official_law', 'law_name': source.law,
            'reference': source.reference, 'effective_from': str(source.effective_from),
            'original_hash': source.text_hash, 'text': source.text}]}]}


def verdicts(keys, files, answer, verdict='pass'):
    return {'items': [{'criterion_id': key, 'verdict': verdict, 'reason': '대조',
        'reference_ids': [files.source.id], 'answer_quotes': ['A:P1'] if verdict == 'pass' else [],
        'missing_expectation_ids': []} for key in keys]}


def experiment(files, output):
    obs = observation(files)
    criteria = mechanical(files.card, files.package, obs) + [
        {'criterion_id': key, 'verdict': 'pass', 'reason': '합성 계약'} for key in SEMANTIC]
    criteria.append({'criterion_id': 'G2', 'verdict': 'not_applicable', 'reason': '없음'})
    row = {'case_id': files.card.id, 'card_hash': digest(files.card.model_dump(mode='json')),
        'observation': obs, 'observation_hash': digest(obs), 'criteria': criteria, 'status': case_status(criteria)}
    result = {'schema_version': 'auto-eval-1', 'options': {'dataset_hash': files.dataset.fingerprint(),
        'selected_ids': [files.card.id], 'split': 'all', 'provider': 'mock', 'model': 'mock', 'prompt_hash': 'test',
        'code_hash': 'original_generation', 'runtime': {'marker': 'original_runtime'}},
        'records': [row], 'build_failures': [], 'summary': summarize([row])}
    output.mkdir()
    save_json(output / 'experiment.json', result)
    return result


def fake_client():
    client = MagicMock()
    client.has_project.return_value = False
    client.has_dataset.return_value = False
    client.create_dataset.return_value = SimpleNamespace(id=uuid4())
    client.create_project.return_value = SimpleNamespace(id=uuid4())
    return client


def test_source_archive_and_frozen_card_are_rechecked(card_files):
    data = load_cards(card_files.root)
    assert data.fingerprint() == card_files.dataset.fingerprint()
    assert data.cards[0].human_approved is False
    (card_files.root / 'snapshots/1.xml').write_bytes((XML + 'changed').encode('utf-8'))
    with pytest.raises(ValueError, match='source_hash_mismatch'):
        load_cards(card_files.root)


@pytest.mark.parametrize('updates,reason', [
    ({'source_url': 'https://example.org/LSW/lsInfoP.do?lsiSeq=25&efYd=20200101'}, 'untrusted_source_url'),
    ({'source_url': 'https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=26&efYd=20200101'}, 'untrusted_source_url'),
    ({'snapshot_file': '../outside.xml'}, 'snapshot_path_escape'),
    ({'version': '26:2020-01-01'}, 'source_version_identity'),
    ({'law_id': '002'}, '법령 ID'),
    ({'text': '실제 사업과 관련된 비용의 잘못된 원문', 'text_hash': sha('실제 사업과 관련된 비용의 잘못된 원문')}, 'source_not_in_snapshot'),
])
def test_forged_source_is_rejected(card_files, updates, reason):
    with pytest.raises(ValueError):
        validate_snapshot(card_files.source.model_copy(update=updates), card_files.root)


@pytest.mark.parametrize('edit', ['quote', 'fact', 'rule', 'missing', 'compound', 'date'])
def test_card_contracts_block_false_facts_sources_and_scope(card_files, edit):
    draft = deepcopy(card_files.draft)
    package = card_files.package
    if edit == 'quote':
        draft.issues[0].required[0].citations[0].quote = '원문에 없는 주장입니다.'
    elif edit == 'fact':
        draft.facts[0].text = '질문에 없는 사실'
    elif edit == 'rule':
        draft.issues[0].rule_ids = ['unknown']
    elif edit == 'missing':
        package = package.model_copy(update={'case_type': 'missing_information'})
    elif edit == 'compound':
        package = package.model_copy(update={'case_type': 'compound'})
    else:
        draft.event_dates = [date(2025, 1, 1)]
    with pytest.raises(ValueError):
        check_draft(draft, card_files.rules, package)


def test_shared_sources_never_cross_splits(card_files):
    other = card_files.package.model_copy(update={'id': 'vat-compound', 'tax': 'vat', 'case_type': 'compound'})
    groups = source_groups([card_files.package, other])
    assert groups[other.id] == groups[card_files.package.id]
    card = card_files.card.model_copy(update={'id': 'two', 'group': 'different', 'split': 'test',
        'package_id': other.id, 'package_hash': digest(other.model_dump(mode='json')),
        'draft': card_files.draft.model_copy(update={'question': '다른 법인의 손금 요건을 설명해 주세요.'})})
    with pytest.raises(ValidationError, match='card_source_leakage'):
        CardDataset(packages=[card_files.package, other], cards=[card_files.card, card], failures=[], metadata={})


@pytest.mark.asyncio
async def test_schema_repairs_once_but_semantic_failure_does_not_retry(card_files):
    valid = card_files.review.model_dump(mode='json')
    valid['items'][0]['verdict'] = 'fail'
    call = AsyncMock(side_effect=[{}, valid])
    result = await structured(CardReview, 'audit', {}, purpose='answer_judge', validate=lambda v: None, call=call)
    assert result.items[0].verdict == 'fail'
    assert call.call_count == 2
    call = AsyncMock(return_value=valid)
    await structured(CardReview, 'audit', {}, purpose='answer_judge', validate=lambda v: None, call=call)
    assert call.call_count == 1


@pytest.mark.asyncio
async def test_builder_resumes_candidate_after_network_error_without_regeneration(card_files, tmp_path, monkeypatch):
    from evaluation import card_sources
    root = tmp_path / 'build'

    async def collect(output, **kwargs):
        (output / 'snapshots').mkdir()
        (output / 'snapshots/1.xml').write_bytes(XML.encode('utf-8'))
        return [card_files.package], []

    monkeypatch.setattr(card_sources, 'collect_packages', collect)
    def wire(value):
        serialized = json.dumps(value.model_dump(mode='json'), ensure_ascii=False)
        span = next(u['span_id'] for u in source_data(card_files.package)['sources'][0]['units']
                    if u['text'] == card_files.rules.rules[0].citations[0].quote)
        return json.loads(serialized.replace(json.dumps(card_files.rules.rules[0].citations[0].quote, ensure_ascii=False),
                                              json.dumps(span, ensure_ascii=False)))

    call = AsyncMock(side_effect=[wire(card_files.rules), wire(card_files.draft), RuntimeError('secret remote key')])
    result = await build(root, as_of=date(2026, 10, 4), taxes=('corporate',), case_types=('general',), call=call)
    assert result['auto_validated'] == 0
    assert 'secret remote key' not in (root / 'cards.json').read_text(encoding='utf-8')
    call = AsyncMock(return_value=wire(card_files.review))
    result = await build(root, as_of=date(2026, 10, 4), taxes=('corporate',), case_types=('general',), resume=True, call=call)
    assert result['auto_validated'] == 1
    assert result['failures'] == {}
    assert call.call_count == 1  # Only the interrupted blind audit is repeated.
    call.reset_mock()
    await build(root, as_of=date(2026, 10, 4), taxes=('corporate',), case_types=('general',), resume=True, call=call)
    call.assert_not_called()
    (root / 'snapshots/1.xml').write_bytes((XML + 'tampered').encode('utf-8'))
    with pytest.raises(ValueError):
        await build(root, as_of=date(2026, 10, 4), taxes=('corporate',), case_types=('general',), resume=True, call=call)
    call.assert_not_called()


@pytest.mark.asyncio
async def test_span_handles_restore_original_text_and_block_cross_source_pairing(card_files):
    from evaluation.auto_cards import citation_schema, expand_spans
    data = source_data(card_files.package)
    schema, spans = citation_schema(RuleBook, data)
    handle = next(key for key, value in spans.items() if value[1] == card_files.rules.rules[0].citations[0].quote)
    assert handle in schema['$defs']['Citation']['properties']['quote']['enum']
    expanded = expand_spans({'source_id': card_files.source.id, 'quote': handle}, spans)
    assert expanded['quote'] == card_files.rules.rules[0].citations[0].quote
    with pytest.raises(ValueError, match='invalid_source_span'):
        expand_spans({'source_id': 'other', 'quote': handle}, spans)
    with pytest.raises(ValueError, match='invalid_source_span'):
        expand_spans({'source_id': card_files.source.id, 'quote': 'invented'}, spans)


def test_mechanical_checks_final_input_version_hash_and_exact_required_spans(card_files):
    obs = observation(card_files)
    assert mechanical(card_files.card, card_files.package, obs)[0]['verdict'] == 'pass'
    obs['generation'] = [{'records': []}]
    assert mechanical(card_files.card, card_files.package, obs)[0]['verdict'] == 'fail'
    obs['generation'] = []
    record = obs['contexts'][0]['records'][0]
    record['text'] = '다른 항만 전달함'
    assert mechanical(card_files.card, card_files.package, obs)[0]['verdict'] == 'fail'
    record['effective_from'] = '2019-01-01'
    assert mechanical(card_files.card, card_files.package, obs)[1]['verdict'] == 'fail'


@pytest.mark.asyncio
async def test_blind_judges_never_receive_first_verdict_and_disagreement_is_unknown(card_files):
    obs = observation(card_files)
    first = verdicts(SEMANTIC, card_files, obs['answer'])
    second = verdicts(('A1', 'A5', 'A6'), card_files, obs['answer'])
    second['items'][0].update(verdict='fail', answer_quotes=[])
    call = AsyncMock(side_effect=[first, second])
    rows = await assess(card_files.card, card_files.package, obs, call=call)
    assert next(r for r in rows if r['criterion_id'] == 'A1')['verdict'] == 'unknown'
    second_input = json.loads(call.call_args_list[1].args[0][1]['content'])
    assert 'verification' not in second_input
    assert 'first_verdict' not in second_input
    assert second_input['criteria'] == ['A1', 'A5', 'A6']


@pytest.mark.parametrize('updates', [{'answer_quotes': ['invented']}, {'reference_ids': ['unknown']},
    {'missing_expectation_ids': ['i1:e1']}, {'answer_quotes': []}])
def test_judge_cannot_pass_with_invented_spans_or_missing_claims(card_files, updates):
    raw = verdicts(['A1'], card_files, 'answer')
    raw['items'][0]['answer_quotes'] = ['answer']
    raw['items'][0].update(updates)
    with pytest.raises(ValueError):
        validate_assessment(AnswerAssessment.model_validate(raw), ['A1'], card_files.card, card_files.package, 'answer')


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [None, 'TimeoutError'])
async def test_empty_answer_and_errors_keep_all_eleven_criteria(card_files, error):
    obs = observation(card_files) | {'answer': '', 'error': error}
    call = AsyncMock()
    rows = mechanical(card_files.card, card_files.package, obs) + await assess(card_files.card, card_files.package, obs, call=call)
    assert len(rows) == 11
    assert len({r['criterion_id'] for r in rows}) == 11
    call.assert_not_called()
    summary = summarize([{'criteria': rows, 'status': case_status(rows)}])
    assert summary['human_approved'] is False
    if error:
        assert summary['counts']['error'] == 10
        assert summary['judge_pass_rate_on_decided'] is None


@pytest.mark.asyncio
async def test_production_observer_only_passes_question_and_disables_history_writes(monkeypatch):
    from app.services import chat_service as chat
    from evaluation.auto_pipeline import observe_chat

    async def process(question, conversation_id, user_id, *, tool_events, verification_out):
        assert question == '질문만 전달'
        assert await chat._fetch_history(conversation_id) == []
        await chat._save_history('placeholder')
        verification_out.append({'status': 'test'})
        return 'answer', None

    save = AsyncMock()
    monkeypatch.setattr(chat, 'process_chat', process)
    monkeypatch.setattr(chat, '_save_history', save)
    result = await observe_chat('질문만 전달')
    assert result['answer'] == 'answer'
    assert result['error'] is None
    save.assert_not_called()


@pytest.mark.asyncio
async def test_run_resume_uses_saved_observation_and_refuses_changed_payload(card_files, tmp_path, monkeypatch):
    from evaluation import auto_pipeline
    output = tmp_path / 'run'
    observe = AsyncMock(return_value=observation(card_files))
    # Simulate an interruption after durable chat collection, before judging.
    monkeypatch.setattr(auto_pipeline, 'assess', AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await run(card_files.root, output, observe=observe)
    observe.assert_awaited_once_with(card_files.draft.question, timeout=420)
    judge = AsyncMock(side_effect=[verdicts(SEMANTIC, card_files, observation(card_files)['answer']),
                                  verdicts(('A1', 'A5', 'A6'), card_files, observation(card_files)['answer'])])
    monkeypatch.undo()
    result = await run(card_files.root, output, resume=True, observe=AsyncMock(side_effect=AssertionError('reran chat')), call=judge)
    validate_experiment(result)
    assert result['records'][0]['status'] == 'incomplete'  # Unlabeled R2 stays unknown.
    result['records'][0]['observation']['answer'] += 'changed'
    save_json(output / 'experiment.json', result)
    with pytest.raises(ValueError, match='automatic_observation_changed'):
        await run(card_files.root, output, resume=True, call=judge)


@pytest.mark.asyncio
async def test_recorded_run_preserves_original_observations_and_never_calls_chat(card_files, tmp_path):
    original_dir, output = tmp_path / 'original', tmp_path / 'rejudge'
    original = experiment(card_files, original_dir)
    observe = AsyncMock(side_effect=AssertionError('chat rerun'))
    judge = AsyncMock(side_effect=[verdicts(SEMANTIC, card_files, observation(card_files)['answer']),
                                  verdicts(('A1', 'A5', 'A6'), card_files, observation(card_files)['answer'])])
    result = await run(card_files.root, output, from_run=original_dir, observe=observe, call=judge)
    observe.assert_not_called()
    assert result['records'][0]['observation'] == original['records'][0]['observation']
    assert result['options']['collection_mode'] == 'recorded'
    assert result['options']['runtime'] == {'marker': 'original_runtime'}
    assert result['options']['generation_code_hash'] == 'original_generation'
    assert not result['summary']['counts'].get('error')
    validate_experiment(result)


@pytest.mark.asyncio
async def test_answer_judge_schema_limits_ids_and_restores_exact_answer_lines(card_files):
    obs = observation(card_files)
    call = AsyncMock(side_effect=[verdicts(SEMANTIC, card_files, obs['answer']),
                                  verdicts(('A1', 'A5', 'A6'), card_files, obs['answer'])])
    result = await assess(card_files.card, card_files.package, obs, call=call)
    first = next(r for r in result if r['criterion_id'] == 'A1')
    assert first['answer_quotes'] == [obs['answer']]
    properties = call.call_args_list[1].args[1]['$defs']['AnswerItem']['properties']
    assert properties['criterion_id']['enum'] == ['A1', 'A5', 'A6']
    assert properties['reference_ids']['items']['enum'] == [card_files.source.id]
    assert properties['missing_expectation_ids']['items']['enum'] == ['i1:e1']
    assert properties['answer_quotes']['items']['enum'] == ['A:P1']


@pytest.mark.parametrize('where', ['contexts', 'generation', 'retrieval'])
def test_auto_publication_rejects_private_evidence_in_every_capture(card_files, tmp_path, where):
    output = tmp_path / 'run'
    value = experiment(card_files, output)
    obs = value['records'][0]['observation']
    obs[where] = [{'results' if where == 'retrieval' else 'records': [
        {'origin_kind' if where == 'retrieval' else 'origin': 'user_document'}]}]
    value['records'][0]['observation_hash'] = digest(obs)
    save_json(output / 'experiment.json', value)
    with pytest.raises(ValueError, match='private_evidence'):
        prepare(card_files.root, output)


def test_publication_preserves_unknowns_and_draft_and_is_idempotent(card_files, tmp_path):
    output = tmp_path / 'run'
    experiment(card_files, output)
    plan = prepare(card_files.root, output)
    assert plan['gate'] == 'incomplete'
    assert plan['examples'][0]['inputs'] == {'case_id': card_files.card.id, 'question': card_files.draft.question}
    assert plan['examples'][0]['outputs']['human_approved'] is False
    feedback = plan['records'][0]['feedback']
    assert {'key': 'diagnostic.auto.R2', 'value': 'unknown'} in feedback
    assert {'key': 'diagnostic.auto.R1', 'score': 1} in feedback
    client = fake_client()
    result = publish_automatic(card_files.root, output, client_factory=lambda: client)
    assert result['status'] == 'complete'
    assert client.create_run.call_count == 1
    assert client.create_example.call_count == 1
    again = publish_automatic(card_files.root, output, client_factory=lambda: pytest.fail('duplicate upload'))
    assert again == result
    assert load_cards(card_files.root).fingerprint() == card_files.dataset.fingerprint()


def test_partial_publication_receipt_blocks_retries_and_masks_remote_error(card_files, tmp_path):
    output = tmp_path / 'run'
    experiment(card_files, output)
    client = fake_client()
    client.create_feedback.side_effect = RuntimeError('private key')
    with pytest.raises(RuntimeError):
        publish_automatic(card_files.root, output, client_factory=lambda: client)
    assert 'private key' not in (output / 'langsmith-receipt.json').read_text(encoding='utf-8')
    with pytest.raises(ValueError, match='inspect_partial'):
        publish_automatic(card_files.root, output, client_factory=lambda: pytest.fail('duplicate remote mutation'))


def test_modified_summary_or_criteria_cannot_be_published(card_files, tmp_path):
    output = tmp_path / 'run'
    value = experiment(card_files, output)
    value['records'][0]['criteria'][0]['verdict'] = 'unknown'
    save_json(output / 'experiment.json', value)
    with pytest.raises(ValueError, match='summary_mismatch'):
        prepare(card_files.root, output)


def test_provider_error_text_never_becomes_an_error_code():
    from evaluation.auto_cards import safe_error
    assert safe_error(ValueError('private_token')) == {'error_type': 'ValueError'}
    assert safe_error(ValueError('invalid_answer_span')) == {
        'error_type': 'ValueError', 'error_code': 'invalid_answer_span'}
