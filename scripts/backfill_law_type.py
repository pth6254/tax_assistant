"""
scripts/backfill_law_type.py — 기존 law_articles의 law_type 일괄 보정 (일회성)

국가법령정보 API의 실제 응답 태그명이 "법령구분명"/"법종구분"인데 코드가
"법령종류명" 등 잘못된 후보를 찾고 있었던 버그(api_service.py, parser_service.py에서 수정됨)로
인해, 그 버그가 고쳐지기 전에 수집된 조문들은 law_type이 전부 빈 문자열로 저장되어 있다.

법률/시행령/시행규칙 우선순위(hybrid_search_service._LAW_ARTICLE_PRIORITY)가
law_type 값에 의존하므로, 기존 데이터를 보정하지 않으면 법령 위계 반영 기능이
계속 무력화된 상태로 남는다. 조문 내용은 바뀐 게 없으므로(content_hash 그대로)
scripts/sync_laws.py의 재수집으로는 고쳐지지 않는다 — 이 스크립트로 별도 보정한다.

사용법:
  python scripts/backfill_law_type.py            # 실제 반영
  python scripts/backfill_law_type.py --dry-run  # 무엇이 바뀔지만 확인
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import close_pool, get_pool
from app.services.law.api_service import search_law


async def main(args: argparse.Namespace) -> int:
    print("DB 연결 중...")
    pool = await get_pool()
    print("DB 연결 완료\n")

    exit_code = 0
    try:
        rows = await pool.fetch(
            "SELECT DISTINCT law_name FROM law_articles WHERE is_current = TRUE AND law_type = '' ORDER BY law_name"
        )
        law_names = [r["law_name"] for r in rows]
        if not law_names:
            print("보정이 필요한 법령이 없습니다.")
            return 0

        print(f"보정 대상 {len(law_names)}개 법령{' (dry-run)' if args.dry_run else ''}\n")

        fixed = 0
        not_found: list[str] = []

        for law_name in law_names:
            try:
                laws = await search_law(law_name, exact=True, display=5)
            except Exception as e:
                print(f"  '{law_name}' — 검색 실패: {e}")
                not_found.append(law_name)
                continue

            if not laws or not laws[0].law_type:
                print(f"  '{law_name}' — 법령구분을 확인하지 못함, 건너뜀")
                not_found.append(law_name)
                continue

            law_type = laws[0].law_type
            if args.dry_run:
                print(f"  '{law_name}' → law_type='{law_type}' (dry-run, 미반영)")
            else:
                result = await pool.execute(
                    "UPDATE law_articles SET law_type = $1 WHERE law_name = $2 AND law_type = ''",
                    law_type, law_name,
                )
                print(f"  '{law_name}' → law_type='{law_type}' ({result})")
            fixed += 1

        print(f"\n{'='*50}")
        print(f"완료 — 보정 {fixed}개 | 확인 실패 {len(not_found)}개")
        if not_found:
            print("확인 실패 법령:", ", ".join(not_found))
            exit_code = 1
        print(f"{'='*50}")

    finally:
        await close_pool()
        print("\nDB 연결 종료")

    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="law_articles.law_type 일괄 보정 스크립트")
    parser.add_argument("--dry-run", action="store_true", help="실제 반영 없이 변경 내용만 출력")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args)))
