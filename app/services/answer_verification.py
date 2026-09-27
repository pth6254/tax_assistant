"""Structured, source-bound checks shown with each chat answer.

These checks verify references and calculator output; they do not decide the
legal meaning or temporal applicability of a provision.
"""

from app.services.citation_guard import (
    _official_source_markers,
    guarded_answer,
    verify_calc_final_amount,
    verify_citations,
)


def verify_answer(answer: str, context: str, calc_context: str | None = None,
                  *, require_law: bool = False) -> tuple[str, dict]:
    """Return the released text and a versioned, public verification summary."""
    released = guarded_answer(answer, context, calc_context, require_law=require_law)
    return released, summarize_verification(answer, context, calc_context, released,
                                            require_law=require_law)


def summarize_verification(answer: str, context: str, calc_context: str | None,
                           released: str, *, require_law: bool = False) -> dict:
    """Describe checks already used by the release guard without changing its result."""
    citations = verify_citations(answer, context)
    citation_required = (bool(_official_source_markers(context)) or require_law) and not calc_context
    citation_status = (
        "failed" if any(not citation.verified for citation in citations) or
        (citation_required and not citations) else
        "checked" if citations else "not_assessed"
    )
    calculation_status = (
        "not_applicable" if not calc_context else
        "checked" if verify_calc_final_amount(answer, calc_context) else "failed"
    )
    status = "withheld" if released != answer else (
        "checked" if citation_status == "checked" or calculation_status == "checked" else "limited"
    )
    return {
        "schema_version": "1.0",
        "status": status,
        "checks": {
            "citation": citation_status,
            "calculation": calculation_status,
            "legal_application": "not_assessed",
        },
        "citations": [
            {"label": citation.label, "law_name": citation.law_name,
             "reference": citation.article_no}
            for citation in citations if citation.verified and status != "withheld"
        ],
        "note": "인용 위치와 계산 결과의 형식 검사를 수행했습니다. 법적 해석과 적용 시점은 별도 확인이 필요합니다."
                if status == "checked" else
                "생성된 설명을 제공하기 위한 근거를 확인하지 못했습니다."
                if status == "withheld" else
                "자동으로 확인할 공식 법령 인용이나 계산 결과가 없습니다.",
    }


def unavailable_verification() -> dict:
    """Tool failure or archival lookup did not undergo final-answer checks."""
    return {"schema_version": "1.0", "status": "withheld",
            "checks": {"citation": "not_assessed", "calculation": "not_applicable",
                       "legal_application": "not_assessed"},
            "citations": [], "note": "필요한 자료를 확보하지 못해 이번 세무 판단을 보류했습니다."}


def unassessed_verification() -> dict:
    """Answers produced by a separate archival path have no final-answer checks here."""
    return {"schema_version": "1.0", "status": "limited",
            "checks": {"citation": "not_assessed", "calculation": "not_applicable",
                       "legal_application": "not_assessed"},
            "citations": [], "note": "이 답변은 현재 채팅의 인용·계산 검사 대상이 아닙니다. 원문과 적용 시점을 확인해 주세요."}
