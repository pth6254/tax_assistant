"""
test_law_search.py — law_articles 벡터 검색 수동 테스트

실행:
    python test_law_search.py                                   # 기본 질문
    python test_law_search.py "프리랜서 노트북 비용처리 돼?"
    python test_law_search.py "간이과세자 부가세 신고 기준" 부가가치세법
    python test_law_search.py "상속세 신고 기한" 상속세및증여세법 10
    인수:  [질문]  [tax_type 필터]  [top_k]
"""
import asyncio
import sys

from app.services.law.search_service import format_search_results, search_law_articles

TEST_QUERIES = [
    ("프리랜서 노트북 비용처리 돼?",           None),
    ("간이과세자 부가세 신고 기준 알려줘",       "부가가치세법"),
    ("법인 접대비 한도",                        "법인세법"),
    ("경정청구 기한",                           "국세기본법"),
]


async def run_single(query: str, tax_type: str | None, top_k: int) -> None:
    print(f"\n{'='*55}")
    print(f" 검색 질문: {query}")
    print(f" 세목 필터: {tax_type or '전체'} | top_k: {top_k}")
    print(f"{'='*55}")

    try:
        results = await search_law_articles(query, tax_type=tax_type, top_k=top_k)
    except Exception as e:
        print(f"[오류] {type(e).__name__}: {e}")
        return

    if not results:
        print("  결과 없음 (law_articles에 embedding이 있는 조문이 없을 수 있습니다)")
        return

    print(f"  {len(results)}건 검색됨\n")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.article_no} [{r.article_title}]")
        print(f"       법령: {r.law_name} ({r.law_type}) | 세목: {r.tax_type}")
        print(f"       유사도: {r.similarity_score:.4f}")
        print(f"       본문: {r.article_text[:100].replace(chr(10), ' ')}...")
        print(f"       URL:  {r.source_url}")
        print()


async def run_all_test_queries() -> None:
    print("\n" + "="*55)
    print(" 사전 정의된 테스트 질문 전체 실행")
    print("="*55)

    for query, tax_type in TEST_QUERIES:
        await run_single(query, tax_type, top_k=3)


async def main(query: str | None, tax_type: str | None, top_k: int) -> None:
    if query is None:
        await run_all_test_queries()
    else:
        await run_single(query, tax_type, top_k)


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        asyncio.run(main(None, None, 5))
    else:
        q        = args[0]
        tax      = args[1] if len(args) > 1 else None
        k        = int(args[2]) if len(args) > 2 else 5
        asyncio.run(main(q, tax, k))
