"""Upload: extraction failures, owner-scoped atomic replacement and deletion (no database or model)."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import upload_service
from app.services.document.extractors import DocumentBlock, ExtractedDocument, ExtractionError, OCRUnavailable

USER = str(uuid.uuid4())


class FakeConn:
    def __init__(self, deleted_rows=()):
        self.calls, self.open = [], False
        self.deleted_rows = list(deleted_rows)

    def _log(self, sql, args):
        self.calls.append((sql.split()[0], sql, args, self.open))

    async def fetchval(self, sql, *args):
        self._log(sql, args)
        return 3   # chunks of the earlier upload with the same name

    async def fetch(self, sql, *args):
        self._log(sql, args)
        return self.deleted_rows

    async def execute(self, sql, *args):
        self._log(sql, args)

    async def executemany(self, sql, rows):
        self._log(sql, rows)

    def transaction(self):
        conn = self

        class Transaction:
            async def __aenter__(self):
                conn.open = True

            async def __aexit__(self, *exc):
                conn.open = False
        return Transaction()


@pytest.fixture
def conn(monkeypatch):
    holder = SimpleNamespace(conn=FakeConn())

    class Acquire:
        async def __aenter__(self):
            return holder.conn

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(upload_service, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=Acquire)))
    return holder


@pytest.mark.asyncio
async def test_a_name_that_states_law_and_kind_is_classified_without_a_model(monkeypatch):
    model = AsyncMock(side_effect=AssertionError("no model call"))
    monkeypatch.setattr(upload_service, "call_llm", model)
    meta = await upload_service.classify_document("소득세법(법률)(제20000호).pdf", "본문")
    assert meta == {"category": "법령", "law_name": "소득세법"}


@pytest.mark.asyncio
async def test_a_failed_classification_keeps_what_the_name_shows(monkeypatch):
    monkeypatch.setattr(upload_service, "call_llm", AsyncMock(side_effect=RuntimeError("down")))
    assert await upload_service.classify_document("부가가치세법 메모.pdf", "본문") == {
        "category": "기타", "law_name": "부가가치세법"}


@pytest.mark.asyncio
@pytest.mark.parametrize("error, status", [(ExtractionError("읽을 수 없는 파일"), 422),
                                           (OCRUnavailable("OCR 엔진 없음"), 503)])
async def test_extraction_failures_are_reported_and_nothing_is_stored(monkeypatch, conn, error, status):
    def fail(data, name):
        raise error
    monkeypatch.setattr(upload_service, "extract_document", fail)
    with pytest.raises(HTTPException) as raised:
        await upload_service.process_upload(b"%PDF", "a.pdf", USER, "a@example.com")
    assert raised.value.status_code == status and conn.conn.calls == []


@pytest.mark.asyncio
async def test_a_reupload_replaces_the_owners_chunks_file_and_review_in_one_transaction(monkeypatch, conn):
    text = "제1조 계약 내용\n둘째 문단"
    extracted = ExtractedDocument(text=text, format="pdf", extraction_method="text", pages=1,
                                  blocks=(DocumentBlock(text=text, page=1),))
    monkeypatch.setattr(upload_service, "extract_document", lambda data, name: extracted)
    monkeypatch.setattr(upload_service, "classify_document", AsyncMock(return_value={"category": "기타", "law_name": "공통"}))
    monkeypatch.setattr(upload_service, "embed_texts_for_storage",
                        AsyncMock(side_effect=lambda chunks: ([[0.1] * 3 for _ in chunks], [])))
    result = await upload_service.process_upload(b"%PDF data", "계약서.pdf", USER, "a@example.com")
    assert result["status"] == "ok" and result["chunks_stored"] >= 1
    kinds = [call[0] for call in conn.conn.calls]
    assert kinds == ["SELECT", "DELETE", "INSERT", "INSERT", "DELETE"]
    assert all(call[3] for call in conn.conn.calls)   # every write inside the transaction
    owner = uuid.UUID(USER)
    assert conn.conn.calls[1][2] == ("계약서.pdf", owner)          # old chunks of this owner only
    assert conn.conn.calls[3][2][0] == owner and conn.conn.calls[4][2] == (owner, "계약서.pdf")
    stored = conn.conn.calls[2][2][0]
    assert stored[4] == owner and stored[3]["source"] == "계약서.pdf"


@pytest.mark.asyncio
async def test_deleting_removes_chunks_and_original_together_or_reports_missing(conn):
    conn.conn = FakeConn(deleted_rows=[{"id": 1}, {"id": 2}])
    assert (await upload_service.delete_document("계약서.pdf", USER))["deleted_chunks"] == 2
    assert [call[0] for call in conn.conn.calls] == ["DELETE", "DELETE"] and all(c[3] for c in conn.conn.calls)
    conn.conn = FakeConn()
    with pytest.raises(HTTPException) as raised:
        await upload_service.delete_document("없는파일.pdf", USER)
    assert raised.value.status_code == 404
