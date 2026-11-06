"""Choose the answer-risk score and threshold from official-answer results (evaluation/gold_eval.py).

An answer is delivered as is when its risk score is at or below the threshold; above it the service adds a
notice or withholds (ANSWER_RISK_ACTION). The loss of a case is 1 when the answer is delivered and its
conclusion contradicts the official reply. Conformal risk control (Angelopoulos et al., 2022) picks the
largest threshold whose adjusted development loss stays within alpha:

    (n / (n + 1)) * mean_loss(t) + 1 / (n + 1) <= alpha

which bounds the expected rate of delivered wrong conclusions on new questions from the same distribution
by alpha. The score is chosen first, on development cases only, as the one that best separates wrong
answers from the rest (AUC); the test split is only reported, never used to choose.

This bounds wrong conclusions *among questions like these* (legal interpretations, asked as official
queries); it is not a guarantee for every question users ask. Partly matching answers count as not wrong
unless --partial-as-wrong.

    python evaluation/abstention_calibration.py evaluation/runs/gold/<name>/results.jsonl --alpha 0.1
"""
import argparse
import json
from pathlib import Path

ANSWERED = {"agree", "partial", "contradict"}


def is_wrong(row, partial_as_wrong=False) -> bool:
    return row["outcome"] == "contradict" or (partial_as_wrong and row["outcome"] == "partial")


def usable(rows):
    return [r for r in rows if r.get("risk_scores") and r["outcome"] in ANSWERED | {"no_conclusion"}]


def auc(rows, score, partial_as_wrong=False):
    """Chance that a wrong answer scores higher than a right one (ties count half); None without both."""
    answered = [r for r in rows if r["outcome"] in ANSWERED]
    wrong = [r["risk_scores"][score] for r in answered if is_wrong(r, partial_as_wrong)]
    right = [r["risk_scores"][score] for r in answered if not is_wrong(r, partial_as_wrong)]
    if not wrong or not right:
        return None
    wins = sum(1.0 if w > r else 0.5 if w == r else 0.0 for w in wrong for r in right)
    return round(wins / (len(wrong) * len(right)), 4)


def delivered_loss(rows, score, threshold, partial_as_wrong=False):
    return sum(1 for r in rows if r["outcome"] in ANSWERED and r["risk_scores"][score] <= threshold
               and is_wrong(r, partial_as_wrong)) / len(rows)


def conformal_threshold(rows, score, alpha, partial_as_wrong=False):
    """Largest threshold meeting the conformal bound, or None when even delivering nothing fails it."""
    n = len(rows)
    if n == 0 or 1 / (n + 1) > alpha:
        return None
    candidates = sorted({r["risk_scores"][score] for r in rows} | {-1.0})
    best = None
    for threshold in candidates:  # the loss only grows with the threshold
        if n / (n + 1) * delivered_loss(rows, score, threshold, partial_as_wrong) + 1 / (n + 1) <= alpha:
            best = threshold
        else:
            break
    return best


def report(rows, score, threshold, partial_as_wrong=False):
    n = len(rows)
    answered = [r for r in rows if r["outcome"] in ANSWERED]
    delivered = [r for r in answered if threshold is not None and r["risk_scores"][score] <= threshold]
    return {
        "cases": n,
        "answered_by_system": len(answered),
        "delivered_without_notice": len(delivered),
        "delivered_rate": round(len(delivered) / n, 3) if n else None,
        "wrong_delivered": sum(is_wrong(r, partial_as_wrong) for r in delivered),
        "wrong_delivered_rate": round(sum(is_wrong(r, partial_as_wrong) for r in delivered) / n, 3) if n else None,
        "wrong_before": sum(is_wrong(r, partial_as_wrong) for r in answered),
        "wrong_rate_before": round(sum(is_wrong(r, partial_as_wrong) for r in answered) / n, 3) if n else None,
        "agree_flagged": sum(r["outcome"] == "agree" for r in answered if r not in delivered),
    }


def calibrate(rows, alpha, partial_as_wrong=False):
    rows = usable(rows)
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]
    scores = sorted(rows[0]["risk_scores"]) if rows else []
    aucs = {name: auc(dev, name, partial_as_wrong) for name in scores}
    ranked = sorted((value, name) for name, value in aucs.items() if value is not None)
    score = ranked[-1][1] if ranked else "combined"
    threshold = conformal_threshold(dev, score, alpha, partial_as_wrong)
    return {
        "alpha": alpha, "partial_as_wrong": partial_as_wrong, "score": score, "auc_dev": aucs,
        "threshold": threshold,
        "note": ("no threshold meets alpha on the development cases; withhold or add cases" if threshold is None
                 else "set ANSWER_RISK_SCORE and ANSWER_RISK_THRESHOLD to these values"),
        "minimum_alpha_for_dev_size": round(1 / (len(dev) + 1), 3) if dev else None,
        "dev": report(dev, score, threshold, partial_as_wrong),
        "test": report(test, score, threshold, partial_as_wrong),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+")
    parser.add_argument("--alpha", type=float, default=0.1)
    parser.add_argument("--partial-as-wrong", action="store_true")
    args = parser.parse_args()
    rows = [json.loads(line) for path in args.results for line in Path(path).open(encoding="utf-8")]
    print(json.dumps(calibrate(rows, args.alpha, args.partial_as_wrong), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
