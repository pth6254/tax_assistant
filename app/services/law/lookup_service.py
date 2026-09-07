"""API와 검색·도구가 공유하는 법령 원문 조회."""
from app.database import get_pool
from app.schemas.law import LawArticleDetail, LawReferenceTarget, ParsedLawReference
from app.services.law.reference_parser import InvalidLawReference, LawReference, normalize_article_no, parse_law_reference
from app.services.law.structure_parser import resolve_reference_target

# ── 조문 원문 조회 ───────────────────────────────────────────────

_ARTICLE_LOOKUP_SQL = """
SELECT law_name, law_type, tax_type, article_no, article_title, article_text,
       effective_date, amendment_date, source_url
FROM law_articles
WHERE is_current = TRUE
  AND regexp_replace(law_name, '\\s+', '', 'g') = regexp_replace($1, '\\s+', '', 'g')
  AND article_no = $2
-- 국가법령정보 API는 절/관 구조 표제(예: "제4절 세액의 계산")를 다음 조문과
-- 같은 조문번호를 가진 별도 행으로 내려주는 경우가 있어(파서 한계),
-- 실제 조문 본문("제55조(세율)..."로 시작)을 우선 채택한다.
ORDER BY (article_text LIKE $2 || '%') DESC, length(article_text) DESC, updated_at DESC
LIMIT 1
"""


async def get_law_article(law_name: str, article_no: str) -> LawArticleDetail | None:
    """법령명 + 조문번호로 조문 원문을 조회한다 (공백 표기 차이 무시).

    조문 원문 뷰어(채팅 답변의 인용을 클릭했을 때) 및 인용 검증에 사용.
    """
    law_name = law_name.strip()
    try:
        parsed_reference = parse_law_reference(article_no)
    except InvalidLawReference:
        normalized_article_no = normalize_article_no(article_no)
        try:
            parsed_reference = parse_law_reference(normalized_article_no)
        except InvalidLawReference:
            parsed_reference = None
    article_no = normalize_article_no(article_no)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_ARTICLE_LOOKUP_SQL, law_name, article_no)
    if not row:
        return None
    reference = None
    target = None
    if parsed_reference and parsed_reference.article is not None:
        canonical_reference = LawReference(
            law_name=row["law_name"],
            article=parsed_reference.article,
            article_branch=parsed_reference.article_branch,
            paragraph=parsed_reference.paragraph,
            item=parsed_reference.item,
            item_branch=parsed_reference.item_branch,
            subitem=parsed_reference.subitem,
        )
        reference = ParsedLawReference(
            law_name=row["law_name"],
            article=canonical_reference.article,
            article_branch=canonical_reference.article_branch,
            paragraph=canonical_reference.paragraph,
            item=canonical_reference.item,
            item_branch=canonical_reference.item_branch,
            subitem=canonical_reference.subitem,
            canonical=canonical_reference.canonical,
        )
        resolved = resolve_reference_target(row["article_text"], canonical_reference)
        if resolved is not None:
            target = LawReferenceTarget(
                exists=resolved.exists,
                level=resolved.level,
                paragraph=resolved.paragraph,
                item=resolved.item,
                item_branch=resolved.item_branch,
                subitem=resolved.subitem,
                text=resolved.text,
                detail=resolved.detail,
            )

    return LawArticleDetail(
        law_name=row["law_name"],
        law_type=row["law_type"],
        tax_type=row["tax_type"],
        article_no=row["article_no"],
        article_title=row["article_title"],
        article_text=row["article_text"],
        effective_date=row["effective_date"],
        amendment_date=row["amendment_date"],
        source_url=row["source_url"] or "",
        reference=reference,
        target=target,
    )
