"""How likely a released answer is to be wrong, from what the verification already recorded.

No model call: the score is read from the verification report (issues without sufficient evidence,
withheld claims, unanswered issues, signal flags on released claims). Which score to use and the
threshold above which an answer is flagged are chosen on the official-answer set
(evaluation/abstention_calibration.py) and set through ANSWER_RISK_SCORE / ANSWER_RISK_THRESHOLD.
"""
import config

UNCOVERED = {"missing", "unverified", "failed"}


def risk_features(report: dict) -> dict:
    metrics = report.get("metrics") or {}
    claims = report.get("claims") or []
    released = [c for c in claims if c.get("released")]
    coverage = report.get("coverage") or {}
    issues = max(metrics.get("issues_total") or len(coverage) or 1, 1)
    judge = report.get("judge") or {}
    return {
        "uncovered": round(sum(1 for state in coverage.values() if (state or {}).get("status") in UNCOVERED) / issues, 4),
        "withheld": round((metrics.get("claims_withheld") or 0) / max(metrics.get("claims_total") or 0, 1), 4),
        "unanswered": round(1 - (metrics.get("issues_answered") or 0) / issues, 4),
        "flagged": round(sum(1 for c in released if c.get("signals")) / max(len(released), 1), 4),
        "judge_missing": round(len(judge.get("missing_issue_ids") or []) / issues, 4),
        "no_legal_claim": 0.0 if any(c.get("released") for c in claims) else 1.0,
    }


# Candidate scores. "combined" weighs the evidence gap most; calibration picks the one that
# separates wrong from right answers best on the development split.
SCORES = {
    "combined": lambda f: 0.35 * f["uncovered"] + 0.25 * f["withheld"] + 0.2 * f["unanswered"]
                          + 0.1 * f["flagged"] + 0.1 * f["judge_missing"],
    "uncovered": lambda f: f["uncovered"],
    "withheld": lambda f: f["withheld"],
    "unanswered": lambda f: f["unanswered"],
    "flagged": lambda f: f["flagged"],
}


def answer_risk(report: dict, score: str | None = None) -> float:
    return round(SCORES[score or config.ANSWER_RISK_SCORE](risk_features(report)), 4)


RISK_NOTICE = ("> **확인 필요:** 이 답변은 근거가 일부 부족하거나 검사에서 걸러진 내용이 있어, 비슷한 경우의 공식 회답과 "
               "결론이 다를 가능성이 평소보다 높습니다. 결론을 그대로 쓰기 전에 인용 원문을 직접 확인하거나 전문가와 상의하세요.")
RISK_HOLD = ("근거가 충분하지 않아 이번 질문에는 결론을 드리지 않습니다. 질문을 더 구체적으로(대상·날짜·금액 등) 적어 주시거나, "
             "국세상담센터(126) 또는 세무 전문가에게 확인해 주세요.")


def apply_risk_policy(text: str, report: dict) -> str:
    """Record the risk; above a calibrated threshold add a notice or withhold the answer."""
    score = answer_risk(report)
    threshold = config.ANSWER_RISK_THRESHOLD
    flagged = threshold is not None and score > threshold and report.get("status") != "withheld"
    report["risk"] = {"score": score, "score_name": config.ANSWER_RISK_SCORE, "features": risk_features(report),
                      "threshold": threshold, "flagged": flagged}
    if not flagged:
        return text
    if config.ANSWER_RISK_ACTION == "hold":
        report["risk"]["action"] = "hold"
        return RISK_HOLD
    report["risk"]["action"] = "notice"
    return RISK_NOTICE + "\n\n" + text
