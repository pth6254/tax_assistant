"""Prepare a blind relation review form and validate human-completed labels.

This module never reads Judge predictions or writes Neo4j review status.
The reviewer identity in a form is self-reported, not authenticated.
"""
import argparse
from datetime import date
import json
from pathlib import Path

from evaluation.kg_relation_judge import validate_pool
from evaluation.schema import digest


REVIEW_FIELDS = ('label', 'reason', 'reviewer', 'reviewed_on', 'source_verified',
                 'temporal_status', 'temporal_note', 'hard_negative', 'confusion')
TEMPORAL_STATUSES = {'confirmed', 'unresolved', 'not_applicable'}


def prepare(pool):
    """Hide construction type and Judge output; retain exact source provenance."""
    validate_pool(pool)
    cards = []
    for card in pool['cards']:
        cards.append({
            'assertion_key': card['assertion_key'],
            'kind': card['kind'],
            'source': dict(card['source']),
            'claim': dict(card['claim']),
            'review': {field: None for field in REVIEW_FIELDS},
        })
    cards.sort(key=lambda card: digest('blind-relation-review-v1|' + card['assertion_key']))
    return {'schema_version': '1.0', 'purpose': 'blind_relation_review',
            'pool_hash': digest(pool), 'cards': cards}


def finalize(pool, form):
    """Create score-compatible gold only from a complete, independently filled form."""
    expected = prepare(pool)
    if (form.get('schema_version') != expected['schema_version']
            or form.get('purpose') != expected['purpose']
            or form.get('pool_hash') != expected['pool_hash']):
        raise ValueError('Blind form schema or source pool hash differs')
    rows = form.get('cards')
    if not isinstance(rows, list) or len(rows) != len(expected['cards']):
        raise ValueError('Blind form must contain every source card exactly once')
    gold = []
    for actual, original in zip(rows, expected['cards']):
        if not isinstance(actual, dict) or any(
                actual.get(field) != original[field]
                for field in ('assertion_key', 'kind', 'source', 'claim')):
            raise ValueError('Blind form source or card order was changed')
        review = actual.get('review')
        if not isinstance(review, dict) or set(review) != set(REVIEW_FIELDS):
            raise ValueError('Blind form review fields differ')
        if (review['label'] not in ('supported', 'unsupported', 'uncertain')
                or not isinstance(review['source_verified'], bool)
                or review['source_verified'] is not True
                or review['temporal_status'] not in TEMPORAL_STATUSES
                or not isinstance(review['reason'], str) or not review['reason'].strip()
                or not isinstance(review['reviewer'], str) or not review['reviewer'].strip()):
            raise ValueError('Human label, source check, temporal status, reason and reviewer required')
        if review['temporal_status'] == 'unresolved' and not str(review['temporal_note'] or '').strip():
            raise ValueError('Unresolved target version needs a temporal note')
        if original['kind'] == 'CITES' and review['temporal_status'] == 'not_applicable':
            raise ValueError('Cited law target version must be checked or marked unresolved')
        try:
            date.fromisoformat(review['reviewed_on'])
        except (TypeError, ValueError) as error:
            raise ValueError('Human review needs a valid ISO date') from error
        if not isinstance(review['hard_negative'], bool):
            raise ValueError('Hard-negative status must be true or false')
        if review['hard_negative'] and (review['label'] != 'unsupported'
                                        or not str(review['confusion'] or '').strip()):
            raise ValueError('Hard negative needs an unsupported label and confusion reason')
        gold.append({
            'assertion_key': original['assertion_key'],
            'label': review['label'],
            'reviewer_kind': 'human',
            'reviewer': review['reviewer'].strip(),
            'reviewed_on': review['reviewed_on'],
            'reason': review['reason'].strip(),
            'hard_negative': review['hard_negative'],
            'confusion': review['confusion'],
            'source_verified': True,
            'temporal_status': review['temporal_status'],
            'temporal_note': review['temporal_note'],
        })
    return {'schema_version': '1.0', 'purpose': 'human_relation_gold',
            'pool_hash': expected['pool_hash'], 'reviews': gold}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'finalize'))
    parser.add_argument('--pool', type=Path, required=True)
    parser.add_argument('--form', type=Path, help='Completed blind form for finalize')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    if args.command == 'finalize' and args.form is None:
        parser.error('--form is required for finalize')
    if args.command == 'prepare' and args.form is not None:
        parser.error('--form is only valid for finalize')
    pool = json.loads(args.pool.read_text(encoding='utf-8'))
    result = (prepare(pool) if args.command == 'prepare' else
              finalize(pool, json.loads(args.form.read_text(encoding='utf-8'))))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')
    print(json.dumps({'output': str(args.output), 'count': len(result.get('cards', result.get('reviews', [])))},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
