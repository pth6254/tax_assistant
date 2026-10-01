"""Server-owned evidence. Display text never grants source authority."""
import hashlib
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
from app.schemas.reliability import EvidenceRecord


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_missing_items(text):
    sections = re.split(r"[①-⑳㉑-㉟]", text)
    # Some official XML bodies list alternatives as 가./나. directly under a
    # paragraph. Presence of that list prevents a truncation false positive;
    # it does not establish whether a requested numeric 호/목 exists.
    listed = r"(?:^|\n)\s*(?:\d+|[가나다라마바사아자차카타파하])\s*\."
    return any(re.search(r"다음\s*각\s*호", part)
               and not re.search(listed, part) for part in sections)


class EvidenceContext(str):
    """String adapter for existing prompts; checks use the records, never this text.

    Concatenating/slicing a str intentionally drops provenance. Callers must use
    with_text when preserving the same immutable evidence records is appropriate.
    """
    def __new__(cls, text, records=(), *, plan=None, coverage=None):
        obj = super().__new__(cls, text)
        obj.records = tuple(records)
        obj.plan = plan
        obj.coverage = coverage or {}
        return obj

    def with_text(self, text):
        return EvidenceContext(text, self.records, plan=self.plan, coverage=self.coverage)


def record_from_result(result):
    text = result.content
    origin = getattr(result, "origin_kind", "unknown")
    source_id = str(getattr(result, "source_id", "") or "")
    original = getattr(result, "original_text", "")
    original_hash = getattr(result, "content_hash", "")
    integrity = "unavailable"
    if source_id and original_hash and original:
        integrity = "verified" if digest(original) == original_hash else "mismatch"
    effective = str(getattr(result, "effective_date", "") or "")
    identity = f"{origin}:{source_id}:{effective}:{digest(text)}"
    # A common legacy ingestion loss: a paragraph promises a numbered list,
    # but the child item texts were never stored. Hash equality cannot fix that.
    missing_items = has_missing_items(text)
    return EvidenceRecord(
        id="E" + digest(identity)[:24], origin=origin,
        source_id=source_id, source=result.source,
        law_name=getattr(result, "law_name", ""), category=getattr(result, "category", ""),
        reference=getattr(result, "article_no", ""),
        version_id=f"{source_id}:{effective}:{original_hash}" if source_id else "",
        effective_from=effective, content_hash=digest(text), original_hash=original_hash,
        text=text, location=getattr(result, "document_location", ""), integrity=integrity,
        graph_evidence=getattr(result, "graph_evidence", ""),
        completeness="missing_items" if missing_items else "not_assessed",
    )


def context_from_records(records, *, plan=None, coverage=None):
    # JSON escaping prevents source-looking lines from altering the envelope.
    records = tuple({r.id: r for r in records}.values())
    text = "\n\n---\n\n".join(json.dumps(r.model_dump(), ensure_ascii=False)
        + ("\n[관계 검색 보조 근거 — 공식 원문과 별도 대조됨]" if r.graph_evidence else "") for r in records)
    return EvidenceContext(text or "관련 문서를 찾지 못했습니다.", records, plan=plan, coverage=coverage)


def is_official(record):
    if record.effective_from:
        try:
            if date.fromisoformat(record.effective_from.replace("-", "")) > datetime.now(ZoneInfo("Asia/Seoul")).date():
                return False
        except ValueError:
            return False
    return (record.origin == "official_law" and record.integrity == "verified"
            and record.completeness != "missing_items"
            and bool(record.source_id) and digest(record.text) == record.content_hash)
