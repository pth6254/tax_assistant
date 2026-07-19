"""
services/law/clause_splitter.py — 조문 본문의 항(項) 단위 분할

한국 법령 조문은 항을 원문자(①②③…)로 구분한다. 긴 조문을 항 단위로
분할해 보조 임베딩을 만들면, 조문 전체 벡터에서 희석되는 특정 항의
내용도 검색에 걸리게 할 수 있다 (예: 소득세법 제59조의4 ⑨항 표준세액공제).

순수 함수만 포함 — DB/LLM 의존 없음.
"""
import re

# 항 번호 원문자: ①(U+2460)~⑳(U+2473), ㉑(U+3251)~㉟(U+325F)
_CLAUSE_MARKERS = frozenset(
    chr(c) for c in list(range(0x2460, 0x2474)) + list(range(0x3251, 0x3260))
)
_CLAUSE_MARKER_RE = re.compile(r"(?=[①-⑳㉑-㉟])")

# 이 길이(문자 수) 이상이고 항이 2개 이상인 조문만 분할 대상.
# 300~1000자 조문 10개로 실험한 결과 hit_rate는 동일(10/10)했지만 MRR이 개선되었고
# (예: 법인세법 제19조의2 HIT@2→HIT@1, 관세법 제118조의4 HIT@3→HIT@1) 회귀는 없었다.
# 짧은 조문도 항끼리 서로 다른 세부사항을 다루면 항 벡터가 더 정밀하게 매칭된다.
CLAUSE_SPLIT_MIN_CHARS = 300
# 분할된 항이 이 길이 미만이면 임베딩 가치가 낮아 제외 (예: "③ 삭제 <2010.12.30>")
_MIN_CLAUSE_CHARS = 50


def split_into_clauses(article_text: str) -> list[tuple[str, str]]:
    """조문 본문을 (항 라벨, 항 텍스트) 목록으로 분할한다.

    첫 원문자 이전 부분(조문 제목 줄 등)은 각 항의 맥락으로만 쓰이고
    별도 항목으로 반환하지 않는다. 항이 2개 미만이면 빈 목록을 반환한다.
    """
    parts = [p for p in _CLAUSE_MARKER_RE.split(article_text) if p.strip()]
    clauses = [p for p in parts if p and p[0] in _CLAUSE_MARKERS]
    if len(clauses) < 2:
        return []

    result = []
    for clause in clauses:
        text = clause.strip()
        if len(text) < _MIN_CLAUSE_CHARS:
            continue
        result.append((text[0], text))
    return result


def should_split(article_text: str) -> bool:
    """항 단위 보조 임베딩 대상인지 판단한다."""
    if len(article_text) < CLAUSE_SPLIT_MIN_CHARS:
        return False
    return len(split_into_clauses(article_text)) >= 2


def build_clause_embed_text(
    law_name: str,
    article_no: str,
    article_title: str,
    article_text: str,
    clause_text: str,
) -> str:
    """항 임베딩용 텍스트 — 조문 메타데이터와 첫 줄(조문 헤더)을 맥락으로 포함한다."""
    header_line = article_text.split("\n", 1)[0][:100]
    return (
        f"법령명: {law_name}\n"
        f"조문: {article_no}"
        + (f" [{article_title}]" if article_title else "")
        + f"\n{header_line}\n"
        f"항 내용:\n{clause_text}"
    )
