"""Compare the current-law table with the official archive and propose replacements from it.

The current table (law_articles) was filled once from the law API; the archive (law_history) keeps every
official XML version with its hash. Measured 2026-11-07: rows whose text the parser cut short (definition
articles reduced to their first sentence), and laws whose newer version is already in force while the table
still holds the old wording. Both are fixed from the archive, never from a model, by re-parsing the verified
XML with the same parser the table was built with (parser_service.parse_articles), so format stays the same.

Proposals only; scripts/repair_law_indexes.py --source archive previews, applies with backups and rolls back.
"""
import re
from collections import Counter, defaultdict
from datetime import date

from app.services.evidence import digest
from app.services.law.parser_service import parse_articles

_LOAD = """SELECT a.*, (SELECT count(*) FROM law_article_clauses c WHERE c.article_id=a.id) AS clause_count,
                  substring(a.source_url from 'lsiSeq=([0-9]+)') AS mst
           FROM law_articles a WHERE is_current = TRUE AND law_type <> '법령해석례'
           ORDER BY law_name, article_no, id"""
_VERSIONS = """SELECT v.law_id, v.mst, v.effective_date, v.promulgation_date, v.id AS version_id,
                      s.id AS snapshot_id, s.content_hash
               FROM law_history.versions v
               JOIN LATERAL (SELECT id, content_hash FROM law_history.snapshots WHERE version_id = v.id
                             ORDER BY collected_at DESC, id DESC LIMIT 1) s ON true
               WHERE v.fetch_status = 'complete'"""

ANNOTATION = re.compile(r"<(?:개정|신설|삭제|타법개정|본조신설)[^>]*>|\[(?:전문개정|본조신설|제목개정|종전[^\]]*)[^\]]*\]")
NUMBERING = re.compile(r"[①-⑳]|(?<![0-9])[0-9]{1,3}(?:의[0-9]+)?\.|(?<![가-힣])[가-하](?:의[0-9]+)?\.|[()\s]")
HEADER = re.compile(r"^제\d+조(?:의\d+)?\s*(?:\([^)]*\))?")
TRUNCATED = 0.8   # current text shorter than 80% of the same version's official text


def wording(text: str) -> str:
    """The provision's words without amendment notes, numbering marks, the header or spacing."""
    text = re.sub(r"\s+", " ", ANNOTATION.sub("", text or "")).strip()
    return NUMBERING.sub("", HEADER.sub("", text))


def newest_in_force(versions, today: date):
    """Per law, the version in force today: latest effective date, then the last promulgated that day."""
    newest = {}
    for version in sorted(versions, key=lambda v: (v["effective_date"], v["promulgation_date"] or date.min, v["version_id"])):
        if version["effective_date"] <= today:
            newest[version["law_id"]] = version
    return newest


def source_url(mst: str) -> str:
    return f"https://www.law.go.kr/lsInfoP.do?lsiSeq={mst}"


def _yyyymmdd(value) -> str:
    return re.sub(r"\D", "", str(value or ""))[:8]


def classify(row, same, newer, today: date):
    """(kind, replacement article) for one current row; kind None means keep the row.

    newer_version   the version in force today words the article differently -> its text
    restore_truncated  same version, our text is much shorter than the official text -> official text
    """
    current = wording(row["article_text"])
    if newer is not None and _yyyymmdd(newer.effective_date) <= today.strftime("%Y%m%d"):
        if wording(newer.article_text) != current:
            return "newer_version", newer
    if same is not None:
        official = wording(same.article_text)
        if official != current and len(current) < TRUNCATED * len(official):
            return "restore_truncated", same
        if official != current:
            return ("same_version_wording" if len(official) >= TRUNCATED * len(current) else "archive_shorter"), None
    return None, None


DELETION = re.compile(r"^제\d+조(?:의\d+)?\s*삭제")
_ARTICLE_PARTS = re.compile(r"제(\d+)조(?:의(\d+))?")


def in_force_chains(versions, today: date) -> dict:
    """Per law, the versions that were in force one after another up to today, oldest first.

    Several promulgations taking effect on one day leave only the last promulgated one in force.
    """
    chains = defaultdict(dict)
    for version in sorted(versions, key=lambda v: (v["effective_date"], v["promulgation_date"] or date.min, v["version_id"])):
        if version["effective_date"] <= today:
            chains[version["law_id"]][version["effective_date"]] = version
    return {law_id: sorted(days.values(), key=lambda v: v["effective_date"]) for law_id, days in chains.items()}


async def wording_since(conn, chain, article_no: str) -> date | None:
    """First effective date of the run of in-force versions, ending today, that word the article alike.

    Compares the archive's own parse of every version (one parser, so format never breaks the run); an
    amended or absent article ends the run. A deleted article ("제13조 삭제") is compared like any other
    wording, so a deletion keeps its run back to the version that deleted it.
    """
    match = _ARTICLE_PARTS.fullmatch(article_no)
    if not match or not chain:
        return None
    rows = await conn.fetch(
        """SELECT s.version_id, a.body FROM law_history.articles a JOIN law_history.snapshots s ON s.id = a.snapshot_id
           WHERE s.id = ANY($1::bigint[]) AND a.article_number = $2 AND a.article_branch = $3 AND a.unit_kind = '조문'""",
        [v["snapshot_id"] for v in chain], match[1], match[2] or "")
    bodies = {r["version_id"]: r["body"] for r in rows}
    latest = bodies.get(chain[-1]["version_id"])
    if latest is None:
        return None
    target, since = wording(latest), chain[-1]["effective_date"]
    for version in reversed(chain[:-1]):
        body = bodies.get(version["version_id"])
        if body is None or wording(body) != target:
            break
        since = version["effective_date"]
    return since


def text_kind(row_text: str, official_text: str, future_texts=()) -> str | None:
    """How the version in force differs from the stored text; None keeps the row (archive parser gap)."""
    if wording(official_text) == wording(row_text):
        return "official_format"
    if DELETION.match(official_text.strip()):
        return "deleted_in_force"
    if len(wording(official_text)) < TRUNCATED * len(wording(row_text)):
        # The API also served text of versions not in force yet; that is replaced by today's text. A
        # shorter official text matching no version is a gap of the archive parser and is kept.
        return "future_text_replaced" if wording(row_text) in {wording(t) for t in future_texts} else None
    return "official_text"


async def rebuild_plan(conn, *, today: date | None = None) -> dict:
    """Everything that makes the current table equal to the archive's versions in force today (P2).

    text       rows whose text or title differs: replaced through index_repair (backups, vectors, clauses)
    labels     same text, older version label: effective/promulgation date and source move, vectors kept
    retire     articles the version in force does not contain (not yet in force, or removed): is_current off
    insert     articles of the version in force the table lacks
    duplicates older non-current rows holding exactly the replacement text (unique law/article/text): removed
    kept       shorter official text matching no version (archive parser gap): left as is, reported
    """
    today = today or date.today()
    rows = [dict(r) for r in await conn.fetch(_LOAD)]
    versions = [dict(v) for v in await conn.fetch(_VERSIONS)]
    by_key = {(v["mst"], v["effective_date"].strftime("%Y%m%d")): v for v in versions}
    newest = newest_in_force(versions, today)
    future = defaultdict(list)
    for v in versions:
        if v["effective_date"] > today:
            future[v["law_id"]].append(v)
    stored = defaultdict(list)
    for r in await conn.fetch("SELECT id, law_name, article_no, content_hash, is_current FROM law_articles"):
        stored[(r["law_name"], r["article_no"], r["content_hash"])].append(dict(r))
    parsed = {}

    async def articles(version):
        key = version["snapshot_id"]
        if key not in parsed:
            snapshot = await conn.fetchrow("SELECT raw_xml, content_hash FROM law_history.snapshots WHERE id=$1", key)
            parsed[key] = None if snapshot is None or digest(snapshot["raw_xml"]) != snapshot["content_hash"] else {
                re.sub(r"\s", "", a.law_name) + "|" + a.article_no: a for a in parse_articles(snapshot["raw_xml"])}
        return parsed[key] or {}

    plan = {"text": [], "labels": [], "retire": [], "insert": [], "duplicates": [], "kept": [], "since": [],
            "counts": Counter()}
    present, law_rows = set(), {}
    chains = in_force_chains(versions, today)
    for row in rows:
        key = re.sub(r"\s", "", row["law_name"]) + "|" + row["article_no"]
        present.add(key)
        version = by_key.get((row["mst"] or "", _yyyymmdd(row["effective_date"])))
        if version is None:
            plan["counts"]["version_not_archived"] += 1
            continue
        law_rows.setdefault(version["law_id"], row)
        target = newest[version["law_id"]]
        official = (await articles(target)).get(key)
        identity = {"effective_date": target["effective_date"].strftime("%Y%m%d"),
                    "amendment_date": _yyyymmdd(target["promulgation_date"]) or row["amendment_date"],
                    "source_url": source_url(target["mst"])}
        if official is None:
            later = [v for v in future[version["law_id"]] if key in await articles(v)]
            plan["retire"].append({"id": row["id"], "law_name": row["law_name"], "article_no": row["article_no"],
                                   "content_hash": row["content_hash"],
                                   "reason": "not_yet_in_force" if later else "not_in_version_in_force"})
            plan["counts"]["retire"] += 1
            continue
        # The event-date check reads how long today's wording has governed (law_articles.in_force_since).
        since = await wording_since(conn, chains.get(version["law_id"], []), row["article_no"])
        since_text = since.strftime("%Y%m%d") if since else None
        if since_text != (row.get("in_force_since") or None):
            plan["since"].append({"id": row["id"], "before": row.get("in_force_since"), "after": since_text})
            plan["counts"]["since"] += 1
        if official.article_text == row["article_text"] and (official.article_title or "") == (row["article_title"] or ""):
            if target["version_id"] == version["version_id"]:
                plan["counts"]["current"] += 1
            else:
                plan["labels"].append({"id": row["id"], "content_hash": row["content_hash"],
                                       "before": {k: row[k] for k in identity}, "after": identity})
                plan["counts"]["labels"] += 1
            continue
        future_texts = [a.article_text for v in future[version["law_id"]] if (a := (await articles(v)).get(key))]
        kind = text_kind(row["article_text"], official.article_text, future_texts)
        if kind is None:
            plan["kept"].append([row["law_name"], row["article_no"], len(row["article_text"]), len(official.article_text)])
            plan["counts"]["kept"] += 1
            continue
        others = [r for r in stored[(row["law_name"], row["article_no"], digest(official.article_text))] if r["id"] != row["id"]]
        if any(r["is_current"] for r in others):
            plan["kept"].append([row["law_name"], row["article_no"], "current_duplicate"])
            plan["counts"]["kept"] += 1
            continue
        plan["duplicates"] += [{"keep": row["id"], "delete": r["id"]} for r in others]
        after = dict(row) | identity | {"article_title": official.article_title, "article_text": official.article_text,
                                        "content_hash": digest(official.article_text)}
        plan["text"].append({"before": row, "after": after, "kind": kind,
                             "snapshot_source_id": f"history_snapshot:{target['snapshot_id']}",
                             "lengths": [len(row["article_text"]), len(official.article_text)]})
        plan["counts"][kind] += 1
    for law_id, sample in law_rows.items():
        target = newest[law_id]
        for key, article in (await articles(target)).items():
            if key in present or DELETION.match(article.article_text.strip()):
                continue
            plan["insert"].append({"law_name": sample["law_name"], "law_type": sample["law_type"],
                                   "tax_type": sample["tax_type"], "article_no": article.article_no,
                                   "article_title": article.article_title, "article_text": article.article_text,
                                   "content_hash": digest(article.article_text),
                                   "effective_date": target["effective_date"].strftime("%Y%m%d"),
                                   "amendment_date": _yyyymmdd(target["promulgation_date"]),
                                   "source_url": source_url(target["mst"]),
                                   "snapshot_source_id": f"history_snapshot:{target['snapshot_id']}"})
            plan["counts"]["insert"] += 1
    plan["counts"] = dict(plan["counts"])
    return plan


async def archive_article(conn, snapshot_source_id: str, law_name: str, article_no: str) -> dict:
    """Re-read one article from its verified snapshot; apply refuses when it no longer matches the plan."""
    snapshot_id = int(snapshot_source_id.rsplit(":", 1)[1])
    snapshot = await conn.fetchrow("SELECT raw_xml, content_hash FROM law_history.snapshots WHERE id=$1", snapshot_id)
    if snapshot is None or digest(snapshot["raw_xml"]) != snapshot["content_hash"]:
        raise ValueError("archive_snapshot_changed")
    key = re.sub(r"\s", "", law_name) + "|" + article_no
    found = [a for a in parse_articles(snapshot["raw_xml"]) if re.sub(r"\s", "", a.law_name) + "|" + a.article_no == key]
    if len(found) != 1:
        raise ValueError("archive_article_not_unique")
    return {"article_text": found[0].article_text, "content_hash": digest(found[0].article_text)}


async def archive_proposals(conn, *, today: date | None = None, laws=None):
    """Replacement candidates (shape of index_repair.repair_candidates) and a findings report."""
    today = today or date.today()
    rows = [dict(r) for r in await conn.fetch(_LOAD) if not laws or r["law_name"] in laws]
    versions = [dict(v) for v in await conn.fetch(_VERSIONS)]
    # One promulgation (MST) can take effect in stages; the archive keeps one version per effective date,
    # so a row's version is (MST, its effective date), never the MST alone.
    by_key = {(v["mst"], v["effective_date"].strftime("%Y%m%d")): v for v in versions}
    newest = newest_in_force(versions, today)
    parsed = {}

    async def articles(version):
        key = version["snapshot_id"]
        if key not in parsed:
            snapshot = await conn.fetchrow("SELECT raw_xml, content_hash FROM law_history.snapshots WHERE id=$1", key)
            if snapshot is None or digest(snapshot["raw_xml"]) != snapshot["content_hash"]:
                parsed[key] = None
            else:
                parsed[key] = {re.sub(r"\s", "", a.law_name) + "|" + a.article_no: a
                               for a in parse_articles(snapshot["raw_xml"])}
        return parsed[key]

    # law_articles keeps one row per (law, article, text); a replacement equal to an older row's text would
    # collide, so it is reported for the rebuild instead of proposed.
    stored = {(r["law_name"], r["article_no"], r["content_hash"]): r["id"] for r in await conn.fetch(
        "SELECT id, law_name, article_no, content_hash FROM law_articles")}
    candidates, findings, kinds = [], defaultdict(list), Counter()
    current_keys, laws_seen = set(), {}
    for row in rows:
        key = re.sub(r"\s", "", row["law_name"]) + "|" + row["article_no"]
        current_keys.add(key)
        version = by_key.get((row["mst"] or "", _yyyymmdd(row["effective_date"])))
        if version is None:
            kinds["version_not_archived"] += 1
            continue
        laws_seen[version["law_id"]] = row["law_name"]
        same_set = await articles(version)
        if same_set is None:
            kinds["snapshot_hash_mismatch"] += 1
            continue
        target_version = newest.get(version["law_id"])
        newer = target_version is not None and target_version["version_id"] != version["version_id"]
        newer_set = await articles(target_version) if newer else None
        kind, replacement = classify(row, same_set.get(key), (newer_set or {}).get(key), today)
        kinds[kind or "unchanged"] += 1
        if kind in {"same_version_wording", "archive_shorter"}:
            findings[kind].append([row["law_name"], row["article_no"]])
        if replacement is None:
            continue
        if stored.get((row["law_name"], row["article_no"], digest(replacement.article_text)), row["id"]) != row["id"]:
            kinds[kind] -= 1
            kinds["duplicate_text_conflict"] += 1
            findings["duplicate_text_conflict"].append([row["law_name"], row["article_no"]])
            continue
        chosen = target_version if kind == "newer_version" else version
        after = dict(row) | {"article_title": replacement.article_title, "article_text": replacement.article_text,
                             "content_hash": digest(replacement.article_text)}
        if kind == "newer_version":
            # The version identity moves with the text; a same-version restore changes the text only.
            after |= {"effective_date": chosen["effective_date"].strftime("%Y%m%d"),
                      "amendment_date": _yyyymmdd(chosen["promulgation_date"]) or row["amendment_date"],
                      "source_url": source_url(chosen["mst"])}
        candidates.append({"before": row, "after": after, "kind": kind,
                           "snapshot_source_id": f"history_snapshot:{chosen['snapshot_id']}",
                           "lengths": [len(row["article_text"]), len(replacement.article_text)]})
    # Articles the version in force has but the table lacks (inserted by the full rebuild, not here).
    for law_id, name in laws_seen.items():
        version = newest.get(law_id)
        found = await articles(version) if version else None
        for key, article in (found or {}).items():
            if key not in current_keys and not re.match(r"^제\d+조(?:의\d+)?\s*삭제", article.article_text.strip()):
                findings["missing_article"].append([name, article.article_no])
                kinds["missing_article"] += 1
    row_versions = {by_key[k]["version_id"]: by_key[k]["law_id"]
                    for k in {(r["mst"] or "", _yyyymmdd(r["effective_date"])) for r in rows} if k in by_key}
    stale = sorted({(laws_seen[law_id], str(v["effective_date"])) for law_id, v in newest.items()
                    if law_id in laws_seen and any(lid == law_id and vid != v["version_id"]
                                                   for vid, lid in row_versions.items())})
    return candidates, {"kinds": dict(kinds), "laws_behind": stale, **{k: v for k, v in findings.items()}}
