"""
services/citation_guard.py — 답변 인용·수치 검증 후처리

LLM이 생성한 최종 답변에서 법령 인용([법률]/[시행령]/[시행규칙] 법령명 제N조)과
계산기 핵심 수치를 추출하여, 실제로 검색된 근거(RAG 컨텍스트 + 계산기 결과)에
존재하는지 사후 검증한다.

근거 없는 인용을 임의로 지우거나 답변을 재작성하지 않는다 — 사용자가 직접
판단할 수 있도록 답변 하단에 경고 각주만 추가한다 (환각을 막는 최후 방어선이지,
답변을 대신 고쳐주는 장치가 아님).
"""
import re
from dataclasses import dataclass

# _COMBINED_PROMPT의 "근거 출처 목록" 형식과 동일한 패턴
_CITATION_RE = re.compile(r"\[(법률|시행령|시행규칙)\]\s*([^\n\[]+?)\s+(제\d+조(?:의\d+)?)")

# calc_context(format_calculation_context)가 만드는 "- 라벨: 1,234,567원" 형식
_MONEY_LINE_RE = re.compile(r"[\d][\d,]*원")


@dataclass
class CitationCheck:
    label: str        # 법률 / 시행령 / 시행규칙
    law_name: str
    article_no: str
    verified: bool


def _normalize(s: str) -> str:
    """공백 표기 차이(예: '상속세및증여세법' vs '상속세 및 증여세법')를 무시하기 위한 정규화."""
    return re.sub(r"\s+", "", s)


def extract_citations(answer: str) -> list[tuple[str, str, str]]:
    """답변 본문에서 (구분, 법령명, 조문번호) 튜플 목록을 추출한다."""
    return [(label, name.strip(), article) for label, name, article in _CITATION_RE.findall(answer)]


def verify_citations(answer: str, trusted_text: str) -> list[CitationCheck]:
    """추출한 인용이 신뢰 가능한 텍스트(RAG 컨텍스트 + 계산기 결과)에 실존하는지 확인한다."""
    norm_trusted = _normalize(trusted_text)
    checks = []
    for label, law_name, article_no in extract_citations(answer):
        exists = _normalize(law_name) in norm_trusted and article_no in norm_trusted
        checks.append(CitationCheck(label=label, law_name=law_name, article_no=article_no, verified=exists))
    return checks


def verify_calc_final_amount(answer: str, calc_context: str | None) -> bool:
    """계산기 결과의 마지막 금액(결정세액/합계)이 답변에 그대로 등장하는지 확인한다.

    calc_context가 없으면(계산기 미실행) 검증 대상이 없으므로 True.
    금액이 재서술(단위 변환 등)될 수 있어 100% 신뢰 지표는 아니지만,
    실효세율처럼 완전히 다른 숫자를 지어내는 경우를 잡아낸다.
    """
    if not calc_context:
        return True
    amounts = _MONEY_LINE_RE.findall(calc_context)
    if not amounts:
        return True
    final_amount = amounts[-1]  # format_calculation_context의 마지막 항목 = 결정세액/합계
    return final_amount in answer


def build_citation_footer(
    answer: str,
    context: str,
    calc_context: str | None = None,
) -> str:
    """검증 실패 항목이 있으면 경고 각주 문자열을 만든다. 문제 없으면 빈 문자열."""
    trusted_text = context if not calc_context else f"{context}\n{calc_context}"
    checks = verify_citations(answer, trusted_text)
    unverified = [c for c in checks if not c.verified]
    calc_ok = verify_calc_final_amount(answer, calc_context)

    if not unverified and calc_ok:
        return ""

    lines = ["\n\n---", "⚠️ **자동 검증 결과, 아래 항목을 확인해주세요 (AI가 생성 중 착오했을 수 있습니다):**"]
    for c in unverified:
        lines.append(f"- 검색 자료에서 확인되지 않은 인용: [{c.label}] {c.law_name} {c.article_no}")
    if not calc_ok:
        lines.append("- 계산기 결과 금액과 답변 속 서술이 일치하지 않을 수 있습니다. 계산 단계를 다시 확인하세요.")
    return "\n".join(lines)


def apply_citation_guard(answer: str, context: str, calc_context: str | None = None) -> str:
    """답변에 검증 각주를 덧붙인 최종 텍스트를 반환한다."""
    footer = build_citation_footer(answer, context, calc_context)
    return answer + footer if footer else answer
