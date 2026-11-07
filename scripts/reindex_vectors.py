"""Re-embed current law rows whose vector has no provenance or was made from another input (DATA_STRATEGY.md).

A row is selected when its index record is missing or its recorded input hash differs from the input
built from today's text (the same text builders as ingestion). The new vector gets the full record
(source hash, input hash, provider/model). The old vector is saved first, and the cosine between old and
new is reported: a low value means the stored vector had been made from different text.

    preview  counts only
    apply    re-embeds in batches with the active embedding (local Ollama), saves <dir>/backup-*.jsonl.gz
    rollback restores the saved vectors and records

    python scripts/reindex_vectors.py preview --dir evaluation/runs/reindex-<date>
"""
import argparse
import asyncio
import gzip
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LANGSMITH_TRACING", "false")

import numpy as np  # noqa: E402

from app.database import close_pool, get_pool  # noqa: E402
from app.services.embedding_service import close_http_client, embed_texts_for_version  # noqa: E402
from app.services.law.index_metadata import vector_metadata  # noqa: E402
from app.services.law.vector_provenance import stale_rows  # noqa: E402

BATCH = 32


async def targets(conn):
    return await stale_rows(conn)


def cosine(a, b) -> float:
    a, b = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


async def apply(pool, folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    async with pool.acquire() as conn:
        articles, clauses = await targets(conn)
    report = {"articles": 0, "clauses": 0, "cosines": []}
    for table, items in (("law_articles", articles), ("law_article_clauses", clauses)):
        for start in range(0, len(items), BATCH):
            batch = items[start:start + BATCH]
            vectors = await embed_texts_for_version([text for _, text in batch], "v1")
            async with pool.acquire() as conn:
                old = {r["id"]: r for r in await conn.fetch(
                    f"SELECT id, embedding, index_metadata FROM {table} WHERE id = ANY($1::bigint[])",
                    [row["id"] for row, _ in batch])}
                with gzip.open(folder / f"backup-{table}-{start:06d}.jsonl.gz", "wt", encoding="utf-8") as out:
                    for row, _ in batch:
                        before = old[row["id"]]
                        out.write(json.dumps({"id": row["id"], "embedding": None if before["embedding"] is None
                                              else np.asarray(before["embedding"]).tolist(),
                                              "index_metadata": before["index_metadata"]}, default=str) + "\n")
                async with conn.transaction():
                    for (row, text), vector in zip(batch, vectors):
                        record = vector_metadata(row["article_text"], text, v1=True)
                        if table == "law_articles":
                            status = await conn.execute(
                                "UPDATE law_articles SET embedding=$2, index_metadata=$3 WHERE id=$1 AND content_hash=$4",
                                row["id"], vector, record, row["content_hash"])
                        else:
                            status = await conn.execute(
                                "UPDATE law_article_clauses SET embedding=$2, index_metadata=$3 "
                                "WHERE id=$1 AND clause_text=$4", row["id"], vector, record, row["clause_text"])
                        if status != "UPDATE 1":
                            raise ValueError(f"row_changed:{table}:{row['id']}")
                        if old[row["id"]]["embedding"] is not None:
                            report["cosines"].append(round(cosine(old[row["id"]]["embedding"], vector), 4))
            report["articles" if table == "law_articles" else "clauses"] += len(batch)
            print(json.dumps({"table": table, "done": start + len(batch), "of": len(items)}), flush=True)
    sims = np.array(report.pop("cosines") or [1.0])
    report |= {"cosine_median": round(float(np.median(sims)), 4), "cosine_min": round(float(sims.min()), 4),
               "below_0.99": int((sims < 0.99).sum()), "below_0.95": int((sims < 0.95).sum())}
    (folder / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


async def rollback(pool, folder: Path):
    restored = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for path in sorted(folder.glob("backup-*.jsonl.gz")):
                table = "law_articles" if "law_articles" in path.name else "law_article_clauses"
                with gzip.open(path, "rt", encoding="utf-8") as lines:
                    for line in lines:
                        row = json.loads(line)
                        record = row["index_metadata"]
                        record = json.loads(record) if isinstance(record, str) else (record or {})
                        await conn.execute(f"UPDATE {table} SET embedding=$2, index_metadata=$3 WHERE id=$1",
                                           row["id"], None if row["embedding"] is None else np.asarray(row["embedding"]),
                                           record)
                        restored += 1
    return {"restored": restored}


async def main(args):
    pool = await get_pool()
    folder = Path(args.dir)
    try:
        if args.command == "preview":
            async with pool.acquire() as conn:
                articles, clauses = await targets(conn)
            print(json.dumps({"articles": len(articles), "clauses": len(clauses)}))
        elif args.command == "apply":
            print(json.dumps(await apply(pool, folder)))
        else:
            print(json.dumps(await rollback(pool, folder)))
    finally:
        await close_http_client()
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preview", "apply", "rollback"))
    parser.add_argument("--dir", required=True)
    asyncio.run(main(parser.parse_args()))
