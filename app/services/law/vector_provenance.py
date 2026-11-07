"""Whether each current vector was made from today's input (shared by the audit and scripts/reindex_vectors.py).

A row's index record (index_metadata) names the source text hash and the input text hash its vector was
built from. The input is rebuilt from today's text with the ingestion builders; a missing record or a
different hash means the vector cannot be shown to represent the current text.
"""
import json
from types import SimpleNamespace

from app.services.evidence import digest
from app.services.law.clause_splitter import build_clause_embed_text
from app.services.law.ingestion_service import _build_embed_text

ARTICLES = """SELECT id, law_name, law_type, tax_type, article_no, article_title, article_text, content_hash,
                     index_metadata FROM law_articles WHERE is_current AND law_type <> '법령해석례' ORDER BY id"""
CLAUSES = """SELECT c.id, c.clause_text, c.index_metadata, a.law_name, a.article_no, a.article_title, a.article_text,
                    a.content_hash FROM law_article_clauses c JOIN law_articles a ON a.id = c.article_id
             WHERE a.is_current AND a.law_type <> '법령해석례' ORDER BY c.id"""


def article_input(row) -> str:
    fields = ("law_name", "law_type", "article_no", "article_title", "article_text")
    return _build_embed_text(SimpleNamespace(**{k: row[k] for k in fields}), row["tax_type"])


def clause_input(row) -> str:
    return build_clause_embed_text(row["law_name"], row["article_no"], row["article_title"],
                                   row["article_text"], row["clause_text"])


def stale(row, text) -> bool:
    record = row["index_metadata"] or {}
    if isinstance(record, str):
        record = json.loads(record)
    return not record or record.get("input_hash") != digest(text) or record.get("source_hash") != row["content_hash"]


async def stale_rows(conn):
    """(articles, clauses) as [(row, input text)] whose vector is not shown to match today's input."""
    articles = [(dict(r), article_input(r)) for r in await conn.fetch(ARTICLES)]
    clauses = [(dict(r), clause_input(r)) for r in await conn.fetch(CLAUSES)]
    return [(r, t) for r, t in articles if stale(r, t)], [(r, t) for r, t in clauses if stale(r, t)]
