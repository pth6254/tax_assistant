"""Choosing replacements for the current-law table from the official archive (no database)."""
from datetime import date

from app.schemas.law import LawArticle
from app.services.law import archive_sync as sync

TODAY = date(2026, 11, 7)


def article(text, effective="20260701"):
    return LawArticle(law_name="법인세법", law_type="법률", article_no="제2조", article_title="정의",
                      article_text=text, effective_date=effective, amendment_date="20260630")


FULL = "제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다. <개정 2022.12.31>\n1. \"내국법인\"이란 …\n2. \"외국법인\"이란 …"
CUT = "제2조(정의) 이 법에서 사용하는 용어의 뜻은 다음과 같다. <개정 2018.12.24>"


def test_wording_ignores_amendment_notes_numbering_and_spacing():
    assert sync.wording("제2조(정의)\n① 내국법인은 <개정 2019.1.1> 과세한다.") == sync.wording("제2조(정의) 내국법인은 과세한다.")
    assert sync.wording(FULL) != sync.wording(CUT)


def test_a_newer_version_in_force_with_other_wording_replaces_the_row():
    row = {"article_text": CUT}
    kind, replacement = sync.classify(row, article(CUT, "20260101"), article(FULL), TODAY)
    assert kind == "newer_version" and replacement.article_text == FULL
    # A version not in force yet is not today's law.
    assert sync.classify(row, article(CUT, "20260101"), article(FULL, "20270101"), TODAY) == (None, None)


def test_a_row_cut_short_is_restored_from_the_same_version():
    kind, replacement = sync.classify({"article_text": CUT}, article(FULL), None, TODAY)
    assert kind == "restore_truncated" and replacement.article_text == FULL
    # Same wording is kept; a small wording difference is only reported; a shorter archive text never wins.
    assert sync.classify({"article_text": FULL}, article(FULL), None, TODAY) == (None, None)
    assert sync.classify({"article_text": FULL}, article(FULL.replace("외국법인", "외국 법인등")), None, TODAY)[0] \
        == "same_version_wording"
    assert sync.classify({"article_text": FULL}, article(CUT), None, TODAY) == ("archive_shorter", None)


def test_the_rebuild_takes_todays_text_but_keeps_rows_the_archive_parse_cut_short():
    assert sync.text_kind(FULL.replace("\n", "\n\n"), FULL) == "official_format"
    assert sync.text_kind(FULL, "제2조 삭제 <2026.2.27>") == "deleted_in_force"
    future = FULL + "\n3. \"가상자산\"이란 … (2027년 시행)"
    # The table held a provision not in force yet: today's (shorter) text replaces it.
    assert sync.text_kind(future * 2, CUT, future_texts=[future * 2]) == "future_text_replaced"
    # A shorter official text that matches no version is a parser gap: the row is kept.
    assert sync.text_kind(future * 2, CUT) is None
    assert sync.text_kind(CUT, FULL) == "official_text"


def test_a_current_article_governs_events_back_to_when_its_wording_took_effect():
    from app.schemas.reliability import EvidenceRecord
    from app.services.evidence import digest
    from app.services.temporal_scope import unresolved_dates
    record = EvidenceRecord(id="E1", origin="official_law", source_id="1", law_name="소득세법", reference="제89조",
                            effective_from="20260701", in_force_since="20220101", content_hash=digest("t"), text="t",
                            integrity="verified")
    assert unresolved_dates(["2026-03-15", "2025년"], [record], today=TODAY) == []
    assert unresolved_dates(["2021-06-01"], [record], today=TODAY) == ["2021-06-01"]
    # Without the date the version label alone decides, as before; archived versions keep their own window.
    assert unresolved_dates(["2026-03-15"], [record.model_copy(update={"in_force_since": ""})], today=TODAY) == ["2026-03-15"]
    archived = record.model_copy(update={"effective_to": "20260630"})
    assert unresolved_dates(["2026-03-15"], [archived], today=TODAY) == ["2026-03-15"]


class _Rows:
    def __init__(self, bodies):
        self.bodies = bodies

    async def fetch(self, sql, snapshot_ids, number, branch):
        return [{"version_id": v, "body": b} for v, b in self.bodies.items()]


async def _since(bodies, chain):
    return await sync.wording_since(_Rows(bodies), chain, "제89조")


def test_the_wording_run_ends_at_the_last_amendment_and_keeps_deletions():
    import asyncio
    chain = [{"version_id": i, "snapshot_id": i, "effective_date": date(2020 + i, 1, 1)} for i in range(5)]
    same = "제89조(비과세) ① 1세대 1주택 <개정 2021.12.8>"
    bodies = {0: "제89조(비과세) ① 옛 문구", 1: same.replace("2021.12.8", "2019.1.1"), 2: same, 3: same, 4: same}
    assert asyncio.run(_since(bodies, chain)) == date(2021, 1, 1)
    deleted = {i: "제89조 삭제 <2009.12.31>" for i in range(5)}
    assert asyncio.run(_since(deleted, chain)) == date(2020, 1, 1)
    assert asyncio.run(_since({0: same}, chain)) is None


def test_a_vector_counts_as_current_only_when_its_record_names_todays_input():
    from app.services.evidence import digest
    from app.services.law.vector_provenance import article_input, stale
    row = {"law_name": "법인세법", "law_type": "법률", "tax_type": "법인세법", "article_no": "제2조",
           "article_title": "정의", "article_text": FULL, "content_hash": digest(FULL)}
    text = article_input(row)
    assert stale(row | {"index_metadata": {}}, text)
    assert not stale(row | {"index_metadata": {"input_hash": digest(text), "source_hash": digest(FULL)}}, text)
    # A record from the cut-short text no longer describes the row.
    assert stale(row | {"index_metadata": {"input_hash": digest(text), "source_hash": digest(CUT)}}, text)
    assert stale(row | {"index_metadata": '{"input_hash": "other", "source_hash": "%s"}' % digest(FULL)}, text)


def test_the_version_in_force_is_the_latest_effective_then_last_promulgated():
    versions = [
        {"law_id": "1", "version_id": 1, "effective_date": date(2026, 1, 1), "promulgation_date": date(2025, 12, 31)},
        {"law_id": "1", "version_id": 2, "effective_date": date(2026, 7, 1), "promulgation_date": date(2025, 12, 31)},
        {"law_id": "1", "version_id": 3, "effective_date": date(2026, 7, 1), "promulgation_date": date(2026, 3, 1)},
        {"law_id": "1", "version_id": 4, "effective_date": date(2027, 1, 1), "promulgation_date": date(2025, 12, 31)},
    ]
    assert sync.newest_in_force(versions, TODAY)["1"]["version_id"] == 3
