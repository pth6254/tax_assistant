"""Attach the archived text of each retrieved article that was in force on the event dates.

Retrieval finds current articles. When a question's event date falls before the
current version, the archive (law_history) is asked for the same article as it
stood during the event. The text is used only when it is determined:

- every archived version in force at some point in the event interval holds that
  article, all with the same text, and every text matches its stored SHA-256;
- the statute name maps to exactly one archived law.

Otherwise nothing is added and the claim gate keeps withholding definite legal
claims for that date. Article-level effective dates and transitional rules in
supplementary provisions (부칙) are not resolved here; answers keep the notice
that they need separate confirmation.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
from zoneinfo import ZoneInfo

from app.schemas.law import HybridSearchResult
from app.services.evidence import context_from_records, is_official, record_from_result
from app.services.law.reference_parser import extract_law_reference
from app.services.temporal_scope import event_interval, unresolved_dates

MAX_LOOKUPS = 12


@dataclass(frozen=True)
class ArchivedArticle:
    version_id: int
    law_name: str
    effective_from: date
    effective_to: date | None      # last day before the next archived version, if any
    title: str
    body: str
    content_hash: str
    source_url: str


def determined_article(rows):
    """One text, present in every in-force version, each matching its stored hash."""
    if not rows or any(row is None for row in rows):
        return None
    hashes = {row["content_hash"] for row in rows}
    if len(hashes) != 1:
        return None
    if any(hashlib.sha256(row["body"].encode("utf-8")).hexdigest() != row["content_hash"] for row in rows):
        return None
    return rows[0]


async def archived_article(law_name, reference, start, end, *, pool=None):
    """The article as in force throughout [start, end], or None when not determined."""
    if pool is None:
        from app.database import get_pool
        pool = await get_pool()
    law_ids = await pool.fetch("SELECT DISTINCT law_id FROM law_history.versions WHERE law_name=$1", law_name)
    if len(law_ids) != 1:
        return None
    law_id = law_ids[0]["law_id"]
    base = await pool.fetchval(
        """SELECT max(effective_date) FROM law_history.versions
           WHERE law_id=$1 AND effective_date<=$2 AND promulgation_date<=$3""", law_id, start, end)
    if base is None:
        return None
    versions = await pool.fetch(
        """SELECT v.id, v.effective_date, v.fetch_status, s.id AS snapshot_id, s.source_url
           FROM law_history.versions v
           LEFT JOIN LATERAL (SELECT id, source_url FROM law_history.snapshots
                              WHERE version_id=v.id ORDER BY collected_at DESC, id DESC LIMIT 1) s ON true
           WHERE v.law_id=$1 AND v.effective_date BETWEEN $2 AND $3 AND v.promulgation_date<=$3
           ORDER BY v.effective_date, v.id""", law_id, base, end)
    if not versions or any(v["fetch_status"] != "complete" or v["snapshot_id"] is None for v in versions):
        return None
    rows = []
    for version in versions:
        found = await pool.fetch(
            """SELECT title, body, content_hash FROM law_history.articles
               WHERE snapshot_id=$1 AND article_number=$2 AND article_branch=$3 AND unit_kind='조문'""",
            version["snapshot_id"], str(reference.article), str(reference.article_branch or ""))
        rows.append(found[0] if len(found) == 1 else None)
    row = determined_article(rows)
    if row is None:
        return None
    following = await pool.fetchval(
        """SELECT min(effective_date) FROM law_history.versions
           WHERE law_id=$1 AND effective_date>$2""", law_id, end)
    return ArchivedArticle(
        version_id=versions[0]["id"], law_name=law_name, effective_from=versions[0]["effective_date"],
        effective_to=following - timedelta(days=1) if following else None, title=row["title"] or "",
        body=row["body"], content_hash=row["content_hash"], source_url=versions[0]["source_url"] or "")


def archived_record(current, article):
    """Same shape as a retrieved current article; integrity is checked against the archive hash."""
    header = current.reference + (f" [{article.title}]" if article.title else "")
    result = HybridSearchResult(
        content=f"{header}\n{article.body}", source=article.source_url or current.source,
        law_name=current.law_name, category=current.category, source_type="law",
        similarity_score=1.0, priority=0, article_no=current.reference, origin_kind="official_law",
        source_id=f"history:{article.version_id}:{current.reference}",
        effective_date=article.effective_from.isoformat(), content_hash=article.content_hash,
        original_text=article.body)
    return record_from_result(result).model_copy(update={
        "effective_to": article.effective_to.isoformat() if article.effective_to else "",
        "location": f"{article.effective_from.isoformat()} 시행본"})


async def attach_event_versions(context, *, lookup=archived_article, today=None):
    """Add in-force archived articles for event dates the current versions do not cover."""
    plan = context.plan
    if not plan or not plan.dates:
        return context
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    records = list(context.records)
    coverage = {key: dict(state) for key, state in context.coverage.items()}
    existing = {r.id for r in records}
    found = {}  # (law, reference, interval) -> archived record or None; one lookup each
    linked = False
    for value in plan.dates:
        interval = event_interval(value)
        if interval is None or interval[1] > today:
            continue
        for current in [r for r in context.records if is_official(r) and unresolved_dates([value], [r], today)]:
            reference = extract_law_reference(current.reference)
            if not reference or reference.article is None:
                continue
            key = (current.law_name, current.reference, interval)
            if key not in found:
                if len(found) >= MAX_LOOKUPS:
                    continue
                try:
                    article = await lookup(current.law_name, reference, interval[0], interval[1])
                except Exception:
                    article = None  # An archive failure is not evidence; the date gate stays closed.
                record = archived_record(current, article) if article else None
                found[key] = record if record is not None and is_official(record) else None
            record = found[key]
            if record is None:
                continue
            if record.id not in existing:
                existing.add(record.id)
                records.append(record)
            for state in coverage.values():
                # The archived text joins every issue that retrieved the current article.
                for field in ("evidence_ids", "relevant_ids"):
                    if current.id in state.get(field, []) and record.id not in state[field]:
                        state[field] = [*state[field], record.id]
                        linked = True
    if len(records) == len(context.records) and not linked:
        return context
    return context_from_records(records, plan=plan, coverage=coverage)
