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
