"""Resume-safe v2-provider backfill for all searchable embedding tables."""
import argparse
import asyncio
import json

from app.database import close_pool, get_pool
from app.services.embedding_service import close_http_client, embed_texts_for_version


TABLES = {
    "law_articles": "article_text",
    "law_article_clauses": "clause_text",
    "documents": "content",
}


async def backfill_table(table: str, batch_size: int, limit: int | None, dry_run: bool) -> int:
    text_column = TABLES[table]
    pool = await get_pool()
    completed = 0
    while limit is None or completed < limit:
        size = batch_size if limit is None else min(batch_size, limit - completed)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT id, {text_column} AS text FROM {table} "
                "WHERE embedding_v2 IS NULL ORDER BY id LIMIT $1",
                size,
            )
        if not rows:
            break
        if dry_run:
            return len(rows)
        vectors = await embed_texts_for_version([row["text"] for row in rows], "v2")
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    f"UPDATE {table} SET embedding_v2 = $1 WHERE id = $2 AND embedding_v2 IS NULL",
                    [(vector, row["id"]) for vector, row in zip(vectors, rows)],
                )
        completed += len(rows)
        print(json.dumps({"table": table, "completed": completed}, ensure_ascii=False))
    return completed


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", choices=[*TABLES, "all"], default="all")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--run", action="store_true", help="실제 DB 업데이트 실행 (기본값은 dry-run)")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    tables = list(TABLES) if args.table == "all" else [args.table]
    try:
        for table in tables:
            count = await backfill_table(table, args.batch_size, args.limit, not args.run)
            print(json.dumps({"table": table, "processed": count, "dry_run": not args.run}))
        return 0
    finally:
        await close_http_client()
        await close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
