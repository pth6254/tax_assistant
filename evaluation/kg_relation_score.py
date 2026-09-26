"""Score advisory relation-Judge results against independently human-reviewed gold."""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from evaluation.schema import digest


def score(pool, report, gold):
    if report.get('pool_hash') != digest(pool) or gold.get('pool_hash') != digest(pool):
        raise ValueError('Pool hash mismatch; source cards changed')
    if report.get('advisory_only') is not True or report.get('gold_labels') is not False:
        raise ValueError('Expected an advisory relation-Judge report')
    if gold.get('schema_version') != '1.0' or gold.get('purpose') != 'human_relation_gold':
        raise ValueError('Expected human relation gold')
    cards = {card['assertion_key']: card for card in pool['cards']}
    predictions = {row['assertion_key']: row for row in report['results']}
    if len(predictions) != len(report['results']) or not predictions.keys() <= cards.keys():
        raise ValueError('Duplicate or unknown Judge assertions')
    seen = set()
    rows = []
    for review in gold.get('reviews', []):
        key = review['assertion_key']
        if key in seen or key not in cards:
            raise ValueError('Duplicate or unknown gold assertion')
        seen.add(key)
        if (review.get('label') not in ('supported', 'unsupported', 'uncertain')
                or review.get('reviewer_kind') != 'human'
                or not str(review.get('reviewer', '')).strip()
                or not str(review.get('reason', '')).strip()):
            raise ValueError('Gold requires a named human reviewer, label and reason')
        try:
            date.fromisoformat(review['reviewed_on'])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('Gold requires a valid review date') from error
        if review.get('hard_negative') is True and review['label'] != 'unsupported':
            raise ValueError('Hard negative must be unsupported')
        if review.get('hard_negative') is True and not review.get('confusion'):
            raise ValueError('Hard negative requires a confusion type')
        prediction = predictions.get(key, {})
        rows.append({'assertion_key': key, 'gold': review['label'],
                     'prediction': prediction.get('consensus'),
                     'hard_negative': review.get('hard_negative') is True})
    binary = [row for row in rows if row['gold'] != 'uncertain']
    decided = [row for row in binary if row['prediction'] in ('supported', 'unsupported')]
    true_positive = sum(row['gold'] == row['prediction'] == 'supported' for row in decided)
    false_positive = sum(row['gold'] == 'unsupported' and row['prediction'] == 'supported'
                         for row in decided)
    false_negative = sum(row['gold'] == 'supported' and row['prediction'] == 'unsupported'
                         for row in decided)
    hard = [row for row in binary if row['hard_negative']]
    def rate(numerator, denominator):
        return numerator / denominator if denominator else None
    return {'schema_version': '1.0', 'gold_labels': len(rows),
            'status': 'scored' if binary else 'insufficient_human_gold',
            'binary_gold': len(binary), 'decided': len(decided),
            'decision_coverage': rate(len(decided), len(binary)),
            'accuracy_on_decided': rate(sum(row['gold'] == row['prediction'] for row in decided),
                                        len(decided)),
            'supported_precision': rate(true_positive, true_positive + false_positive),
            'supported_recall_on_all_gold': rate(true_positive,
                sum(row['gold'] == 'supported' for row in binary)),
            'hard_negative_false_support_rate': rate(sum(row['prediction'] == 'supported'
                for row in hard), len(hard)),
            'prediction_counts': dict(Counter(row['prediction'] or 'undecided' for row in rows)),
            'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pool', 'judge', 'gold', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    files = [json.loads(path.read_text(encoding='utf-8'))
             for path in (args.pool, args.judge, args.gold)]
    result = score(*files)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')
    print(json.dumps({'output': str(args.output), 'status': result['status'],
                      'gold_labels': result['gold_labels']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
