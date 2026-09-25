"""Isolation and integrity checks for the official-source pilot collector."""

import hashlib
import json

import pytest

from evaluation.international_sources import SOURCES, Source, audit, collect, validate_source


def test_pilot_has_all_three_countries_and_three_korea_treaties():
    assert {s.jurisdiction for s in SOURCES} >= {"US", "JP", "CN", "KR-US", "KR-JP", "KR-CN"}
    assert len({s.id for s in SOURCES}) == len(SOURCES)
    assert all(s.url.startswith("https://") for s in SOURCES)


def test_validation_rejects_nonofficial_host_and_wrong_media():
    unsafe = Source("bad", "US", "test", "guidance", "https://example.com/document", "html", "en")
    with pytest.raises(ValueError, match="non-official"):
        validate_source(unsafe, b"<html>" + b"a" * 1000, "text/html")
    official = Source("test", "US", "test", "statute", "https://www.irs.gov/document", "pdf", "en")
    with pytest.raises(ValueError, match="PDF"):
        validate_source(official, b"<html>" + b"a" * 1000, "text/html")


def test_resume_refuses_tampered_saved_document(tmp_path, monkeypatch):
    root = tmp_path / "pilot"
    root.mkdir()
    source = SOURCES[0]
    (root / f"{source.id}.{source.format}").write_bytes(b"changed")
    (root / "manifest.json").write_text(json.dumps({
        "source_set": "KR-US-JP-CN-official-pilot-v1",
        "records": {source.id: {"status": "collected", "url": source.url, "raw_file": f"{source.id}.{source.format}", "sha256": hashlib.sha256(b"original").hexdigest()}},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity mismatch"):
        collect(root, resume=True, pause_seconds=0)


def test_existing_output_requires_resume(tmp_path):
    root = tmp_path / "pilot"
    root.mkdir()
    with pytest.raises(FileExistsError):
        collect(root)


def test_audit_rejects_incomplete_inventory(tmp_path):
    root = tmp_path / "pilot"
    root.mkdir()
    (root / "manifest.json").write_text('{"records": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="inventory incomplete"):
        audit(root)
