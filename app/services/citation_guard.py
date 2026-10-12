"""
services/citation_guard.py — 주장에 적힌 법령 인용의 실재 확인

주장 문장의 법령 인용([법률]/[시행령]/[시행규칙] 법령명 제N조 …)이 그 주장이 연결한 공식 근거
레코드(EvidenceContext)의 같은 법령·조문과, 항·호·목까지 실제로 일치하는지 확인한다.
claim_verification의 reference_mismatch 검사가 이 결과를 쓴다.
"""
import re
from dataclasses import dataclass

from app.services.evidence import EvidenceContext, is_official
from app.services.law.reference_parser import (
    InvalidLawReference, extract_law_reference, normalize_article_no, parse_law_reference,
)
from app.services.law.structure_parser import resolve_reference_target

# 조문번호는 공백 변형을 허용한다 — 모델이 "제 50 조", "제 59 조의 4"처럼 숫자 주변에 공백을
# 섞어 쓰는 경우가 많아, 엄격한 "제\d+조" 패턴은 인용 대부분을 놓쳐 검증이 조용히 무력화된다.
_CITATION_RE = re.compile(
    r"\[(법률|시행령|시행규칙)\]\s*([^\n\[]+?)\s*"
    r"(제\s*\d+\s*조(?:\s*의\s*\d+)?"
    r"(?:\s*(?:제\s*\d+\s*항|[①-⑳㉑-㉟]))?"
    r"(?:\s*제\s*\d+\s*호(?:\s*의\s*\d+)?)?"
    r"(?:\s*[가-하]\s*목)?)"
)
_SOURCE_LABELS = {
    "법률": "법률", "대통령령": "시행령", "총리령": "시행규칙", "부령": "시행규칙",
}


def _source_label(category: str) -> str | None:
    if category.endswith("부령"):
        return "시행규칙"
    return _SOURCE_LABELS.get(category)


@dataclass
class CitationCheck:
    label: str        # 법률 / 시행령 / 시행규칙
    law_name: str
    article_no: str
    verified: bool


def _normalize(s: str) -> str:
    """공백 표기 차이(예: '상속세및증여세법' vs '상속세 및 증여세법')를 무시하기 위한 정규화."""
    return re.sub(r"\s+", "", s)


def verify_citations(answer: str, evidence: EvidenceContext) -> list[CitationCheck]:
    """Match each citation to one official source article and its actual subunit."""
    sources = []
    for record in evidence.records:
        if is_official(record) and _source_label(record.category):
            reference = extract_law_reference(record.reference)
            if reference and reference.article_no:
                sources.append((_source_label(record.category), _normalize(record.law_name),
                                reference.article_no, record.text))
    checks = []
    for match in _CITATION_RE.finditer(answer):
        label, law_name, citation = match.groups()
        law_name = law_name.strip(" *_")
        article_no = normalize_article_no(citation)
        try:
            reference = parse_law_reference(citation)
        except InvalidLawReference:
            checks.append(CitationCheck(label, law_name, article_no, False))
            continue
        exists = False
        for source_label, source_law, source_article, body in sources:
            if (label, _normalize(law_name), reference.article_no) != (source_label, source_law, source_article):
                continue
            target = resolve_reference_target(body, reference)
            if target is None or target.exists:
                exists = True
                break
        checks.append(CitationCheck(label, law_name, article_no, exists))
    return checks
