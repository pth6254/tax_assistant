"""Make the current-law table equal to the archive's versions in force today (docs/ai/DATA_STRATEGY.md P2).

    preview  read-only: writes <dir>/rebuild.json and the text replacements as <dir>/text-plan.json
    apply    in order: remove older duplicate rows, move version labels, record since when today's wording
             has been in force (in_force_since), retire articles not in force, insert missing articles (with
             vectors and clauses). Each step writes its backup first.
             Then run: python scripts/repair_law_indexes.py apply --plan <dir>/text-plan.json --limit 0
    rollback reverse of apply (run the repair rollback for text-plan.json first)

Every change is compare-and-swap on the row's content hash, so a row changed meanwhile stops the run.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("LANGSMITH_TRACING", "false")

from app.database import close_pool, get_pool  # noqa: E402
from app.services.embedding_service import close_http_client, embed_texts_for_storage  # noqa: E402
from app.services.law.archive_sync import rebuild_plan  # noqa: E402
from app.services.law.index_repair import SOURCE_FIELDS, apply_repair, prepare_repair, snapshot_row  # noqa: E402


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


async def preview(conn, folder: Path):
    plan = await rebuild_plan(conn)
    run_id = str(uuid4())
    text_items = [item | {"before": {k: item["before"][k] for k in SOURCE_FIELDS},
                          "after": {k: item["after"][k] for k in SOURCE_FIELDS}} for item in plan.pop("text")]
    write_json(folder / "text-plan.json", {"version": 1, "source": "archive", "scope": "all", "run_id": run_id,
                                          "items": text_items, "rejected": [], "findings": None})
    plan["run_id"] = run_id
    plan["text_items"] = len(text_items)
    write_json(folder / "rebuild.json", plan)
    return {"counts": plan["counts"], "text": len(text_items), "since": len(plan["since"]), "labels": len(plan["labels"]),
            "retire": len(plan["retire"]), "insert": len(plan["insert"]), "duplicates": len(plan["duplicates"]),
            "kept": plan["kept"]}


async def apply(pool, folder: Path):
    plan = json.loads((folder / "rebuild.json").read_text(encoding="utf-8"))
    state_path = folder / "rebuild.state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"done": []}
    done = set(state["done"])

    def mark(step):
        done.add(step)
        state["done"] = sorted(done)
        write_json(state_path, state)

    async with pool.acquire() as conn:
        if "duplicates" not in done:
            rows = []
            for pair in plan["duplicates"]:
                row = await conn.fetchrow("SELECT * FROM law_articles WHERE id=$1", pair["delete"])
                if row is None or row["is_current"]:
                    raise ValueError(f"duplicate_changed:{pair['delete']}")
                rows.append(snapshot_row(row))
            write_json(folder / "backup-duplicates.json", rows)
            async with conn.transaction():
                for row in rows:
                    await conn.execute("DELETE FROM law_articles WHERE id=$1 AND NOT is_current AND content_hash=$2",
                                       row["id"], row["content_hash"])
            mark("duplicates")
        if "labels" not in done:
            async with conn.transaction():
                for label in plan["labels"]:
                    status = await conn.execute(
                        "UPDATE law_articles SET effective_date=$3, amendment_date=$4, source_url=$5, updated_at=NOW() "
                        "WHERE id=$1 AND content_hash=$2 AND effective_date=$6 AND source_url=$7",
                        label["id"], label["content_hash"], label["after"]["effective_date"],
                        label["after"]["amendment_date"], label["after"]["source_url"],
                        label["before"]["effective_date"], label["before"]["source_url"])
                    if status != "UPDATE 1":
                        raise ValueError(f"label_row_changed:{label['id']}")
            mark("labels")
        if "since" not in done:
            async with conn.transaction():
                for item in plan.get("since", []):
                    status = await conn.execute(
                        "UPDATE law_articles SET in_force_since=$2 WHERE id=$1 AND in_force_since IS NOT DISTINCT FROM $3",
                        item["id"], item["after"], item["before"])
                    if status != "UPDATE 1":
                        raise ValueError(f"since_row_changed:{item['id']}")
            mark("since")
        if "retire" not in done:
            async with conn.transaction():
                for item in plan["retire"]:
                    status = await conn.execute(
                        "UPDATE law_articles SET is_current=FALSE, updated_at=NOW() "
                        "WHERE id=$1 AND is_current AND content_hash=$2", item["id"], item["content_hash"])
                    if status != "UPDATE 1":
                        raise ValueError(f"retire_row_changed:{item['id']}")
            mark("retire")
    inserted = state.setdefault("inserted", [])
    for item in plan["insert"][len(inserted):]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO law_articles (law_name, law_type, tax_type, article_no, article_title, article_text,
                       effective_date, amendment_date, source_url, content_hash, is_current, index_metadata)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,TRUE,'{}'::jsonb) RETURNING *""",
                item["law_name"], item["law_type"], item["tax_type"], item["article_no"], item["article_title"],
                item["article_text"], item["effective_date"], item["amendment_date"], item["source_url"],
                item["content_hash"])
        before = dict(row)
        candidate = {"before": before, "after": before, "snapshot_source_id": item["snapshot_source_id"],
                     "kind": "insert_in_force"}
        prepared = await prepare_repair(candidate, embed_texts_for_storage, plan["run_id"])
        async with pool.acquire() as conn:
            await apply_repair(conn, prepared, lambda backup: None)
        inserted.append(before["id"])
        write_json(state_path, state)
        print(json.dumps({"inserted": before["id"], "law": item["law_name"], "article": item["article_no"],
                          "clauses": len(prepared.clauses)}, ensure_ascii=False), flush=True)
    mark("insert")
    return state


async def rollback(pool, folder: Path):
    plan = json.loads((folder / "rebuild.json").read_text(encoding="utf-8"))
    state_path = folder / "rebuild.state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    async with pool.acquire() as conn:
        async with conn.transaction():
            for article_id in state.get("inserted", []):
                await conn.execute("DELETE FROM law_article_clauses WHERE article_id=$1", article_id)
                await conn.execute("DELETE FROM law_articles WHERE id=$1", article_id)
            if "retire" in state["done"]:
                for item in plan["retire"]:
                    await conn.execute("UPDATE law_articles SET is_current=TRUE WHERE id=$1 AND content_hash=$2",
                                       item["id"], item["content_hash"])
            if "since" in state["done"]:
                for item in plan.get("since", []):
                    await conn.execute("UPDATE law_articles SET in_force_since=$2 WHERE id=$1", item["id"], item["before"])
            if "labels" in state["done"]:
                for label in plan["labels"]:
                    await conn.execute(
                        "UPDATE law_articles SET effective_date=$3, amendment_date=$4, source_url=$5 "
                        "WHERE id=$1 AND content_hash=$2", label["id"], label["content_hash"],
                        label["before"]["effective_date"], label["before"]["amendment_date"], label["before"]["source_url"])
            if "duplicates" in state["done"]:
                for row in json.loads((folder / "backup-duplicates.json").read_text(encoding="utf-8")):
                    columns = list(row)
                    await conn.execute(
                        f"INSERT INTO law_articles ({', '.join(columns)}) VALUES "
                        f"({', '.join(f'${i + 1}' for i in range(len(columns)))})",
                        *[row[c] for c in columns])
    state_path.rename(state_path.with_suffix(".rolled-back.json"))


async def main(args):
    pool = await get_pool()
    folder = Path(args.dir)
    try:
        if args.command == "preview":
            async with pool.acquire() as conn:
                print(json.dumps(await preview(conn, folder), ensure_ascii=False, indent=1))
        elif args.command == "apply":
            print(json.dumps(await apply(pool, folder), ensure_ascii=False))
        else:
            await rollback(pool, folder)
            print(json.dumps({"rolled_back": True}))
    finally:
        await close_http_client()
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preview", "apply", "rollback"))
    parser.add_argument("--dir", required=True)
    asyncio.run(main(parser.parse_args()))
