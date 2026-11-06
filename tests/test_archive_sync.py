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


def test_the_version_in_force_is_the_latest_effective_then_last_promulgated():
    versions = [
        {"law_id": "1", "version_id": 1, "effective_date": date(2026, 1, 1), "promulgation_date": date(2025, 12, 31)},
        {"law_id": "1", "version_id": 2, "effective_date": date(2026, 7, 1), "promulgation_date": date(2025, 12, 31)},
        {"law_id": "1", "version_id": 3, "effective_date": date(2026, 7, 1), "promulgation_date": date(2026, 3, 1)},
        {"law_id": "1", "version_id": 4, "effective_date": date(2027, 1, 1), "promulgation_date": date(2025, 12, 31)},
    ]
    assert sync.newest_in_force(versions, TODAY)["1"]["version_id"] == 3
