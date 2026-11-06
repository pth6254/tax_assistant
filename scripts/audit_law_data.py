"""Read-only audit of the law data against the official archive (docs/ai/DATA_STRATEGY.md P0).

Reports, without changing anything:
- rows the archive would replace (newer version in force with different wording, truncated text),
  laws whose table holds an older version than the one in force, articles the table lacks,
  same-version wording differences and rows where the archive parse is the shorter one;
- derived-data provenance: current rows and clauses without an index record (source/input hash).

    python scripts/audit_law_data.py [--output evaluation/runs/law-audit/<date>.json]
"""
import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LANGSMITH_TRACING", "false")

from app.database import close_pool, get_pool  # noqa: E402
from app.services.law.archive_sync import archive_proposals  # noqa: E402


async def audit(today: date) -> dict:
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
    return {
        "date": today.isoformat(),
        "replacements": dict(Counter(c["kind"] for c in candidates)),
        "replacement_laws": dict(Counter(c["before"]["law_name"] for c in candidates).most_common()),
        "definition_articles_replaced": sorted(f"{c['before']['law_name']} {c['before']['article_no']}"
                                               for c in candidates if c["before"]["article_no"] == "제2조"),
        "findings": findings,
        "provenance": provenance,
        "interpretations_in_statute_table": interpretations,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()

    async def run():
        try:
            return await audit(date.today())
        finally:
            await close_pool()
    report = asyncio.run(run())
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
    summary = {k: report[k] for k in ("replacements", "provenance", "interpretations_in_statute_table")}
    summary["laws_behind"] = len(report["findings"].get("laws_behind", []))
    summary["kinds"] = report["findings"].get("kinds")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
