"""
test_law_api.py — Phase 1~5 수동 테스트

실행:
    python test_law_api.py                          # 검색 + XML 파싱만
    python test_law_api.py 부가가치세법              # 다른 법령
    python test_law_api.py --xml                    # raw XML 출력
    python test_law_api.py --ingest                 # 단일 법령 저장 (임베딩 없음)
    python test_law_api.py --ingest --embed         # 단일 법령 저장 + 임베딩
    python test_law_api.py 법인세법 --ingest --embed
    python test_law_api.py --ingest-all             # 전체 법령 저장 (임베딩 없음)
    python test_law_api.py --ingest-all --embed     # 전체 법령 저장 + 임베딩
"""
import asyncio
import sys

from app.services.law.api_service import get_law_detail, search_law
from app.services.law.parser_service import parse_articles, summarize_articles


async def search_and_parse_law(query: str, show_xml: bool = False) -> None:
    """법령명으로 API 검색 후 XML 조문 파싱 결과를 출력한다."""

    print(f"\n{'='*50}")
    print(f" 법령 검색: '{query}'")
    print(f"{'='*50}")

    try:
        laws = await search_law(query, display=5)
    except ValueError as e:
        print(f"[설정 오류] {e}")
        return
    except Exception as e:
        print(f"[API 오류] {type(e).__name__}: {e}")
        return

    if not laws:
        print("  검색 결과 없음")
        return

    for i, law in enumerate(laws, 1):
        print(f"  [{i}] {law.law_name}")
        print(f"       종류: {law.law_type} | 소관: {law.ministry}")
        print(f"       공포일: {law.promulgation_date} | MST: {law.mst}")

    first = laws[0]
    print(f"\n{'='*50}")
    print(f" 상세 조회 + 조문 파싱: '{first.law_name}' (MST={first.mst})")
    print(f"{'='*50}")

    try:
        detail = await get_law_detail(first.mst)
    except Exception as e:
        print(f"[상세 조회 오류] {type(e).__name__}: {e}")
        return

    raw_xml = detail["raw_xml"]
    print(f"  XML 크기: {len(raw_xml):,} bytes")

    if show_xml:
        print("\n--- raw XML (앞 2000자) ---")
        print(raw_xml[:2000])
        print("---\n")

    articles = parse_articles(
        raw_xml,
        law_name_hint=first.law_name,
        law_type_hint=first.law_type,
    )

    print()
    summarize_articles(articles)

    if articles:
        a = articles[0]
        print(f"\n--- 첫 번째 조문 전체 ---")
        print(f"  {a.article_no} [{a.article_title}]")
        print(f"  시행일: {a.effective_date} | 공포일: {a.amendment_date}")
        print(f"  본문:\n{a.article_text}")


async def ingest_single_law(query: str, embed: bool = False) -> None:
    """단일 법령을 API에서 가져와 law_articles 테이블에 저장한다."""
    from app.services.law.ingestion_service import LAW_TARGETS, ingest_law

    tax_type_map = {t["law_name"]: t["tax_type"] for t in LAW_TARGETS}
    tax_type = tax_type_map.get(query, "ALL")

    print(f"\n{'='*50}")
    print(f" 단일 법령 수집: '{query}' (tax_type={tax_type}, embed={embed})")
    print(f"{'='*50}")

    try:
        result = await ingest_law(law_name=query, tax_type=tax_type, embed=embed)
    except ValueError as e:
        print(f"[오류] {e}")
        return
    except Exception as e:
        print(f"[오류] {type(e).__name__}: {e}")
        return

    print(f"\n  법령명:      {result['law_name']}")
    print(f"  MST:         {result['mst']}")
    print(f"  파싱 조문:   {result['total_articles']}건")
    print(f"  신규 저장:   {result['inserted_count']}건")
    print(f"  중복 스킵:   {result['skipped_count']}건")
    print(f"  저장 실패:   {result['failed_count']}건")
    if embed:
        print(f"  임베딩 성공: {result['embedded_count']}건")
        print(f"  임베딩 실패: {result['embed_failed_count']}건")

    if result["inserted_count"] > 0:
        print(f"\n  확인 SQL:")
        print(f"    SELECT article_no, article_title,")
        print(f"           LEFT(article_text, 50),")
        print(f"           embedding IS NOT NULL AS has_embedding")
        print(f"    FROM law_articles")
        print(f"    WHERE law_name = '{result['law_name']}' AND is_current = TRUE")
        print(f"    ORDER BY article_no;")


async def ingest_all_laws_to_db(embed: bool = False) -> None:
    """LAW_TARGETS의 전체 세목 법령을 순차적으로 law_articles 테이블에 저장한다."""
    from app.services.law.ingestion_service import ingest_all_laws

    print(f"\n{'='*50}")
    print(f" 전체 세목 법령 일괄 수집 (embed={embed})")
    print(f"{'='*50}")

    await ingest_all_laws(embed=embed)

    print("\n  최종 확인 SQL:")
    print("    SELECT law_name,")
    print("           COUNT(*) AS 조문수,")
    print("           COUNT(embedding) AS 임베딩완료")
    print("    FROM law_articles WHERE is_current = TRUE")
    print("    GROUP BY law_name ORDER BY law_name;")


async def main(
    query: str,
    show_xml: bool,
    run_ingest: bool,
    ingest_all: bool,
    embed: bool,
) -> None:
    if ingest_all:
        await ingest_all_laws_to_db(embed=embed)
    elif run_ingest:
        await ingest_single_law(query, embed=embed)
    else:
        await search_and_parse_law(query, show_xml=show_xml)


if __name__ == "__main__":
    args  = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    query       = args[0] if args else "소득세법"
    show_xml    = "--xml"        in flags
    run_ingest  = "--ingest"     in flags
    ingest_all  = "--ingest-all" in flags
    embed       = "--embed"      in flags

    asyncio.run(main(query, show_xml, run_ingest, ingest_all, embed))
