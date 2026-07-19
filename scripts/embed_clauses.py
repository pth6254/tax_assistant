"""
scripts/embed_clauses.py — 기존 조문의 항(項) 단위 보조 임베딩 백필

db/migrations/006_law_article_clauses.sql 적용 후 1회 실행한다.
이후 신규 수집분은 ingestion_service._embed_and_update가 자동으로 항 임베딩을 생성한다.

사용법:
  python scripts/embed_clauses.py            # 대상 조문 수만 확인 (dry-run)
  python scripts/embed_clauses.py --run      # 실제 생성
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import close_pool, get_pool
from app.schemas.law import LawArticle
from app.services.law.clause_splitter import CLAUSE_SPLIT_MIN_CHARS, should_split
from app.services.law.ingestion_service import embed_clauses_for_articles
from app.services.embedding_service import close_http_client


async def main(args: argparse.Namespace) -> None:
    print("DB 연결 중...")
    pool = await get_pool()
    print("DB 연결 완료\n")

    try:
        rows = await pool.fetch(
            """
            SELECT id, law_name, law_type, article_no, article_title, article_text
            FROM law_articles
            WHERE is_current = TRUE AND law_type <> '법령해석례'
              AND length(article_text) >= $1
            ORDER BY id
            """,
            CLAUSE_SPLIT_MIN_CHARS,
        )

        items = []
        for r in rows:
            article = LawArticle(
                law_name=r["law_name"], law_type=r["law_type"],
                article_no=r["article_no"], article_title=r["article_title"],
                article_text=r["article_text"], effective_date="", amendment_date="",
            )
            if should_split(article.article_text):
                items.append((article, r["id"]))

        print(f"길이 {CLAUSE_SPLIT_MIN_CHARS}자 이상 조문 {len(rows)}건 중 항 분할 대상 {len(items)}건")

        if not args.run:
            print("\n(dry-run — 실제 생성하려면 --run 옵션을 추가하세요)")
            return

        count = await embed_clauses_for_articles(items)
        print(f"\n항 단위 보조 임베딩 {count}건 생성 완료")

    finally:
        await close_pool()
        await close_http_client()
        print("\nDB 연결 종료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="항 단위 보조 임베딩 백필 스크립트")
    parser.add_argument("--run", action="store_true", help="실제 임베딩 생성 (없으면 dry-run)")
    args = parser.parse_args()
    asyncio.run(main(args))
