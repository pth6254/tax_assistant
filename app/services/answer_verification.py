"""Verification summaries for answers that skip the claim checks.

A tool failure, a question for missing inputs and an archive answer do not go through
claim_verification; these summaries say so instead of claiming checks that did not run.
"""


def unavailable_verification(events=None) -> dict:
    """Tool failure or archival lookup did not undergo final-answer checks."""
    terminal = next((event for event in reversed(events or [])
                     if event.get("scope") != "issue" and event.get("status") not in {"running", "selecting", "no_tool_needed"}), {})
    needs_input = terminal.get("status") in {"needs_input", "invalid_arguments"}
    return {"schema_version": "1.0", "status": "limited" if needs_input else "withheld",
            "checks": {"citation": "not_assessed", "calculation": "not_applicable",
                       "legal_application": "not_assessed"},
            "citations": [], "note": (terminal.get("context") or "계산·조회 조건을 추가로 확인해야 합니다.") if needs_input
            else "필요한 자료를 확보하지 못해 이번 세무 판단을 보류했습니다."}


def unassessed_verification() -> dict:
    """Answers produced by a separate archival path have no final-answer checks here."""
    return {"schema_version": "1.0", "status": "limited",
            "checks": {"citation": "not_assessed", "calculation": "not_applicable",
                       "legal_application": "not_assessed"},
            "citations": [], "note": "이 답변은 현재 채팅의 인용·계산 검사 대상이 아닙니다. 원문과 적용 시점을 확인해 주세요."}
