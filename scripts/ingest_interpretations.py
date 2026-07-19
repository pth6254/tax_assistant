"""
scripts/ingest_interpretations.py — 법령해석례(유권해석) 수집 CLI

사용법:
  # 특정 키워드 1개만 수집 (임베딩 없이 먼저 확인)
  python scripts/ingest_interpretations.py --query 소득세

  # 임베딩까지 함께 생성
  python scripts/ingest_interpretations.py --query 소득세 --embed

  # 세법 전체 키워드로 자동 수집 (ingestion_service._TAX_SEARCH_KEYWORDS 재사용)
  python scripts/ingest_interpretations.py --all-tax-keywords --embed

  # 키워드당 최대 수집 건수 조정 (기본 100)
  python scripts/ingest_interpretations.py --query 부가가치세 --max-results 30 --embed
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import close_pool, get_pool
from app.services.law.ingestion_service import _TAX_SEARCH_KEYWORDS
from app.services.law.interpretation_service import ingest_interpretations
from app.services.embedding_service import close_http_client


def _print_result(result: dict) -> None:
    print(
        f"  '{result['query']}' — 검색 {result['found']}건 | "
        f"저장 {result['inserted_count']} | 중복 {result['skipped_count']} | "
        f"실패 {result['failed_count']} | 임베딩 {result['embedded_count']}건"
        + (f" (임베딩 실패 {result['embed_failed_count']})" if result["embed_failed_count"] else "")
    )


async def main(args: argparse.Namespace) -> None:
    print("DB 연결 중...")
    await get_pool()
    print("DB 연결 완료\n")

    try:
        if args.all_tax_keywords:
            print(f"세법 키워드 {len(_TAX_SEARCH_KEYWORDS)}개로 유권해석 수집 시작...\n")
            totals = {"found": 0, "inserted_count": 0, "skipped_count": 0, "failed_count": 0, "embedded_count": 0}
            for keyword in _TAX_SEARCH_KEYWORDS:
                result = await ingest_interpretations(
                    keyword, embed=args.embed, max_results=args.max_results,
                )
                _print_result(result)
                for key in totals:
                    totals[key] += result[key]
            print(f"\n{'='*50}")
            print(
                f"전체 합계 — 검색 {totals['found']}건 | 저장 {totals['inserted_count']} | "
                f"중복 {totals['skipped_count']} | 실패 {totals['failed_count']} | "
                f"임베딩 {totals['embedded_count']}건"
            )
            print(f"{'='*50}")

        elif args.query:
            print(f"'{args.query}' 유권해석 수집 시작...\n")
            result = await ingest_interpretations(
                args.query, embed=args.embed, max_results=args.max_results,
            )
            _print_result(result)

        else:
            print("--query 또는 --all-tax-keywords 중 하나를 지정하세요.")

    finally:
        await close_pool()
        await close_http_client()
        print("\nDB 연결 종료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="법령해석례(유권해석) 수집 스크립트")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--query",             type=str, default="", help="검색 키워드 (예: --query 소득세)")
    source.add_argument("--all-tax-keywords",  action="store_true", help="세법 전체 키워드로 자동 수집")
    parser.add_argument("--embed",             action="store_true", help="수집 시 임베딩 생성")
    parser.add_argument("--max-results",       type=int, default=100, help="키워드당 최대 수집 건수 (기본 100)")
    args = parser.parse_args()
    asyncio.run(main(args))
