"""Add side-by-side v2 embeddings for a reversible provider migration.

Revision ID: 20260822_0002
Revises: 20260719_0001
"""
from alembic import op


revision = "20260822_0002"
down_revision = "20260719_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("documents", "law_articles", "law_article_clauses"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS embedding_v2 vector(2560)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS documents_embedding_v2_hnsw_idx "
        "ON documents USING hnsw ((embedding_v2::halfvec(2560)) halfvec_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS law_articles_embedding_v2_hnsw_idx "
        "ON law_articles USING hnsw ((embedding_v2::halfvec(2560)) halfvec_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS law_article_clauses_embedding_v2_hnsw_idx "
        "ON law_article_clauses USING hnsw ((embedding_v2::halfvec(2560)) halfvec_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS documents_embedding_v2_hnsw_idx")
    op.execute("DROP INDEX IF EXISTS law_articles_embedding_v2_hnsw_idx")
    op.execute("DROP INDEX IF EXISTS law_article_clauses_embedding_v2_hnsw_idx")
    for table in ("documents", "law_articles", "law_article_clauses"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding_v2")
