"""Read-only audit of the law data against the official archive (docs/ai/DATA_STRATEGY.md P0).

Reports, without changing anything:
- rows the archive would replace (newer version in force with different wording, truncated text),
  laws whose table holds an older version than the one in force, articles the table lacks,
  same-version wording differences and rows where the archive parse is the shorter one;
- derived-data provenance: current rows and clauses without an index record (source/input hash), and
  vectors whose record does not match the input built from today's text (optionally a re-embedded sample);
- event-date reach: how many current articles can answer for dates 30 days to 2 years back.

    python scripts/audit_law_data.py [--output evaluation/runs/law-audit/<date>.json]
"""
import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LANGSMITH_TRACING", "false")

from app.database import close_pool, get_pool  # noqa: E402
from app.services.law.archive_sync import archive_proposals  # noqa: E402
from app.services.law.vector_provenance import stale_rows  # noqa: E402


async def audit(today: date, sample: int = 0) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        candidates, findings = await archive_proposals(conn, today=today)
        provenance = dict(await conn.fetchrow("""
            SELECT count(*) FILTER (WHERE index_metadata = '{}'::jsonb OR index_metadata IS NULL) AS articles_without_record,
                   count(*) FILTER (WHERE index_metadata ? 'input_hash') AS articles_with_input_hash,
                   count(*) FILTER (WHERE index_metadata ? 'source_hash' AND index_metadata->>'source_hash' <> content_hash)
                       AS articles_with_stale_record,
                   count(*) AS articles
            FROM law_articles WHERE is_current AND law_type <> '법령해석례'"""))
        provenance |= dict(await conn.fetchrow("""
            SELECT count(*) FILTER (WHERE c.index_metadata = '{}'::jsonb OR c.index_metadata IS NULL) AS clauses_without_record,
                   count(*) FILTER (WHERE c.index_metadata ? 'source_hash' AND c.index_metadata->>'source_hash' <> a.content_hash)
                       AS clauses_with_stale_record,
                   count(*) AS clauses
            FROM law_article_clauses c JOIN law_articles a ON a.id = c.article_id WHERE a.is_current"""))
        interpretations = await conn.fetchval("SELECT count(*) FROM law_articles WHERE law_type = '법령해석례'")
        # Event-date reach: how many current articles the current text can answer for on a past date
        # (in_force_since, else the version label). A drop here means dated questions fall back to the
        # archive or are withheld (2026-11-07: moving version labels forward had cut this by 71%).
        dates = [today - timedelta(days=30), date(today.year, 1, 1), today - timedelta(days=365),
                 today - timedelta(days=730)]
        reach = await conn.fetchrow(
            "SELECT count(*) AS articles, count(in_force_since) AS with_since, "
            + ", ".join(f"count(*) FILTER (WHERE coalesce(in_force_since, effective_date) <= '{d:%Y%m%d}') AS d{i}"
                        for i, d in enumerate(dates))
            + " FROM law_articles WHERE is_current AND law_type <> '법령해석례'")
        date_reach = {"articles": reach["articles"], "with_in_force_since": reach["with_since"],
                      **{d.isoformat(): reach[f"d{i}"] for i, d in enumerate(dates)}}
        stale_articles, stale_clauses = await stale_rows(conn)
        vectors = {"articles_not_matching_input": len(stale_articles), "clauses_not_matching_input": len(stale_clauses)}
        if sample:
            vectors["sample"] = await vector_sample(conn, sample)
    return {
        "date": today.isoformat(),
        "replacements": dict(Counter(c["kind"] for c in candidates)),
        "replacement_laws": dict(Counter(c["before"]["law_name"] for c in candidates).most_common()),
        "definition_articles_replaced": sorted(f"{c['before']['law_name']} {c['before']['article_no']}"
                                               for c in candidates if c["before"]["article_no"] == "제2조"),
        "findings": findings,
        "provenance": provenance,
        "date_reach": date_reach,
        "vectors": vectors,
        "interpretations_in_statute_table": interpretations,
    }


async def vector_sample(conn, size: int) -> dict:
    """Re-embed a random sample with the active model; a low cosine to the stored vector means the stored
    vector was made from another text even when its record says otherwise (needs the embedding server)."""
    import random
    import numpy as np
    from app.services.embedding_service import close_http_client, embed_texts_for_version
    from app.services.law.vector_provenance import ARTICLES, article_input
    rows = random.Random(7).sample([dict(r) for r in await conn.fetch(ARTICLES)], size)
    fresh = []
    for start in range(0, size, 16):
        fresh += await embed_texts_for_version([article_input(r) for r in rows[start:start + 16]], "v1")
    stored = {r["id"]: r["embedding"] for r in await conn.fetch(
        "SELECT id, embedding FROM law_articles WHERE id = ANY($1::bigint[])", [r["id"] for r in rows])}
    sims = np.array([float(np.dot(stored[r["id"]], v) / (np.linalg.norm(stored[r["id"]]) * np.linalg.norm(v)))
                     for r, v in zip(rows, fresh)])
    await close_http_client()
    return {"size": size, "cosine_median": round(float(np.median(sims)), 4), "cosine_min": round(float(sims.min()), 4),
            "below_0.99": int((sims < 0.99).sum())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--vector-sample", type=int, default=0,
                        help="re-embed this many random articles and compare with the stored vectors")
    args = parser.parse_args()

    async def run():
        try:
            return await audit(date.today(), args.vector_sample)
        finally:
            await close_pool()
    report = asyncio.run(run())
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
    summary = {k: report[k] for k in ("replacements", "provenance", "date_reach", "vectors",
                                      "interpretations_in_statute_table")}
    summary["laws_behind"] = len(report["findings"].get("laws_behind", []))
    summary["kinds"] = report["findings"].get("kinds")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
