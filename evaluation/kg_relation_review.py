"""Build reproducible, unlabelled review cards from retained law-history XML.

These are candidate cards, not legal gold labels. A human must verify the
source, relation meaning, temporal applicability and any hard negative.
"""
import argparse
import asyncio
from datetime import date
import hashlib
import json
from pathlib import Path

from app.database import close_pool, get_pool
from app.services.graph.knowledge_service import build, source_version


def make_cards(version, articles, *, max_per_kind=10):
    provisions, concepts, references, assertions = build(version, articles)
    sources = {row['key']: row for row in provisions}
    targets = {row['key']: ('concept', row['name']) for row in concepts}
    targets.update({row['key']: ('reference', row['law_name'] + ' ' + row['reference'])
                    for row in references})
    cards = []
    for kind in ('DEFINES', 'CITES'):
        claims = sorted((row for row in assertions if row['kind'] == kind),
                        key=lambda row: hashlib.sha256(row['key'].encode()).hexdigest())
        for claim in claims[:max_per_kind]:
            source = sources[claim['source']]
            target_type, target_text = targets[claim['target']]
            cards.append({
                'assertion_key': claim['key'], 'kind': kind, 'candidate_type': 'extracted',
                'source': {'version_id': version['id'], 'snapshot_id': version['snapshot_id'],
                           'law_id': version['law_id'], 'law_name': version['law_name'],
                           'law_type': version.get('law_type', ''),
                           'effective_date': str(version.get('effective_date') or ''),
                           'source_url': version['source_url'],
                           'article_id': source['source_article_id'],
                           'article_hash': source['article_hash'],
                           'reference': source['reference'], 'quote': source['quote'],
                           'source_hash': source['source_hash'],
                           'occurrence': source['occurrence']},
                'claim': {'target_type': target_type, 'target': target_text,
                          'evidence': claim['quote']},
                'review': {'status': 'unreviewed', 'label': None, 'confusion': None,
                           'reason': None, 'reviewer': None, 'reviewed_on': None},
            })
    return cards


def law_level(name):
    if name.endswith('시행규칙'):
        return '시행규칙'
    if name.endswith('시행령'):
        return '시행령'
    return '법률'


def challenge_cards(cards, *, seed='kg-relation-v1', max_per_kind=6):
    """Make blind, unlabelled target swaps for hard-negative review."""
    result = []
    for kind in ('DEFINES', 'CITES'):
        group = [card for card in cards if card['kind'] == kind]
        group.sort(key=lambda card: hashlib.sha256(
            (seed + card['assertion_key']).encode()).hexdigest())
        for card in group:
            alternatives = [other for other in group
                if other['claim']['target_type'] == card['claim']['target_type']
                and other['claim']['target'] != card['claim']['target']
                and other['source']['law_id'] == card['source']['law_id']
                and other['claim']['target'] not in card['source']['quote']]
            if not alternatives:
                continue
            alternatives.sort(key=lambda other: hashlib.sha256(
                (seed + card['assertion_key'] + other['assertion_key']).encode()).hexdigest())
            other = alternatives[0]
            target = other['claim']['target']
            key = hashlib.sha256(('kg-challenge|' + card['assertion_key'] + '|'
                                  + target).encode()).hexdigest()
            challenge = json.loads(json.dumps(card, ensure_ascii=False))
            challenge.update(assertion_key=key, source_assertion_key=card['assertion_key'],
                             candidate_type='challenge', challenge_type='same_law_other_target')
            challenge['claim']['target'] = target
            result.append(challenge)
            if len([row for row in result if row['kind'] == kind]) >= max_per_kind:
                break
    return result


def pool_payload(cards, scopes, *, seed, requested, challenges):
    keys = [card['assertion_key'] for card in cards]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate assertion in review scope')
    era_by_version = {scope['version_id']: scope['era'] for scope in scopes
                      if scope.get('version_id') is not None and 'era' in scope}
    return {'schema_version': '1.0', 'purpose': 'human_relation_review_pool',
            'gold_labels': False, 'selection': {'seed': seed, **requested},
            'scopes': scopes, 'cards': cards,
            'coverage': {'laws': sorted({card['source']['law_name'] for card in cards}),
                         'levels': {level: sum(law_level(card['source']['law_name']) == level
                                          for card in cards)
                                    for level in ('법률', '시행령', '시행규칙')},
                         'kinds': {kind: sum(card['kind'] == kind for card in cards)
                                   for kind in ('DEFINES', 'CITES')},
                         'eras': {era: sum(era_by_version.get(card['source']['version_id']) == era
                                            for card in cards)
                                  for era in ('old', 'recent')},
                         'empty_scopes': [scope for scope in scopes
                                          if scope.get('candidate_count') == 0],
                         'challenge_candidates': challenges}}


async def collect(scopes, *, max_per_kind=10):
    cards = []
    try:
        for version_id, article in scopes:
            version, rows = await source_version(version_id, article)
            cards.extend(make_cards(version, rows, max_per_kind=max_per_kind))
    finally:
        await close_pool()
    return pool_payload(cards, [{'version_id': v, 'article': a} for v, a in scopes],
                        seed='manual', requested={'mode': 'manual'}, challenges=0)


async def collect_auto(*, laws_per_level=3, per_kind=3, challenge_per_kind=6,
                       seed='kg-relation-v1', max_scan_per_era=20,
                       old_before=date(2016, 1, 1), as_of=None):
    as_of = as_of or date.today()
    if min(laws_per_level, per_kind, max_scan_per_era) < 1 or challenge_per_kind < 0:
        raise ValueError('Invalid automatic sampling limits')
    pool = await get_pool()
    laws = await pool.fetch('''SELECT DISTINCT ON (law_id) law_id,law_name,
            min(effective_date) OVER(PARTITION BY law_id) AS first_date
        FROM law_history.versions WHERE fetch_status='complete' AND effective_date <= $1
        ORDER BY law_id,effective_date DESC,id DESC''', as_of)
    selected = []
    for level in ('법률', '시행령', '시행규칙'):
        group = [dict(row) for row in laws if law_level(row['law_name']) == level]
        group.sort(key=lambda row: (row['first_date'] >= old_before,
            hashlib.sha256((seed + row['law_id']).encode()).hexdigest()))
        selected.extend(group[:laws_per_level])
    cards, scopes = [], []
    try:
        for law in selected:
            versions = await pool.fetch('''SELECT id,effective_date FROM law_history.versions
                WHERE law_id=$1 AND fetch_status='complete' AND effective_date <= $2
                ORDER BY effective_date,id''', law['law_id'], as_of)
            chosen = set()
            old_versions = [row for row in versions if row['effective_date'] < old_before]
            for era, ordered in (('old', list(reversed(old_versions))),
                                 ('recent', list(reversed(versions)))):
                scanned = 0
                for row in ordered[:max_scan_per_era]:
                    if row['id'] in chosen:
                        continue
                    scanned += 1
                    version, articles = await source_version(row['id'], allow_empty=True)
                    selected_cards = make_cards(version, articles, max_per_kind=per_kind)
                    if not selected_cards:
                        continue
                    chosen.add(row['id'])
                    cards.extend(selected_cards)
                    scopes.append({'version_id': row['id'], 'law_id': law['law_id'],
                                   'law_level': law_level(law['law_name']),
                                   'era': era, 'versions_scanned': scanned,
                                   'candidate_count': len(selected_cards)})
                    break
                else:
                    scopes.append({'version_id': None, 'law_id': law['law_id'],
                                   'law_level': law_level(law['law_name']),
                                   'era': era, 'versions_scanned': scanned,
                                   'candidate_count': 0})
    finally:
        await close_pool()
    challenges = challenge_cards(cards, seed=seed, max_per_kind=challenge_per_kind)
    cards.extend(challenges)
    return pool_payload(cards, scopes, seed=seed,
                        requested={'mode': 'automatic', 'laws_per_level': laws_per_level,
                                   'per_kind': per_kind,
                                   'challenge_per_kind': challenge_per_kind,
                                   'max_scan_per_era': max_scan_per_era,
                                   'old_before': old_before.isoformat(),
                                   'as_of': as_of.isoformat()},
                        challenges=len(challenges))


def parse_scope(value):
    version, separator, article = value.partition(':')
    if not separator or not article.strip() or not version.isdigit():
        raise argparse.ArgumentTypeError('Scope must be VERSION_ID:ARTICLE')
    return int(version), article.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--scope', action='append', type=parse_scope)
    source.add_argument('--auto', action='store_true')
    parser.add_argument('--max-per-kind', type=int, default=10)
    parser.add_argument('--laws-per-level', type=int, default=3)
    parser.add_argument('--per-kind', type=int, default=3)
    parser.add_argument('--challenge-per-kind', type=int, default=6)
    parser.add_argument('--max-scan-per-era', type=int, default=20)
    parser.add_argument('--old-before', type=date.fromisoformat, default=date(2016, 1, 1))
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    parser.add_argument('--seed', default='kg-relation-v1')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (min(args.max_per_kind, args.laws_per_level, args.per_kind,
            args.max_scan_per_era) < 1
            or args.challenge_per_kind < 0):
        parser.error('Sampling limits must be positive (challenge limit may be zero)')
    if args.output.exists():
        parser.error('Output already exists')
    result = asyncio.run(collect_auto(laws_per_level=args.laws_per_level,
        per_kind=args.per_kind, challenge_per_kind=args.challenge_per_kind,
        seed=args.seed, max_scan_per_era=args.max_scan_per_era,
        old_before=args.old_before, as_of=args.as_of)
        if args.auto else collect(args.scope, max_per_kind=args.max_per_kind))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')
    print(json.dumps({'output': str(args.output), 'cards': len(result['cards']),
                      'coverage': result['coverage'], 'gold_labels': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
