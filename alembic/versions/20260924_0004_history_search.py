"""Deduplicated, resumable history search index; preserve archive and live RAG."""
from alembic import op

revision = '20260924_0004'
down_revision = '20260922_0003'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE TABLE law_history.index_texts (
            key text PRIMARY KEY, body text NOT NULL, kind text NOT NULL,
            chunked boolean NOT NULL DEFAULT false, graph_done boolean NOT NULL DEFAULT false
        );
        CREATE TABLE law_history.search_chunks (
            key text PRIMARY KEY, body text NOT NULL,
            embedding vector(2560), model_key text,
            attempts integer NOT NULL DEFAULT 0, error_type text
        );
        CREATE TABLE law_history.text_chunks (
            text_key text REFERENCES law_history.index_texts(key),
            chunk_key text REFERENCES law_history.search_chunks(key),
            position integer NOT NULL, PRIMARY KEY(text_key,position)
        );
        CREATE INDEX history_chunk_members ON law_history.text_chunks(chunk_key);
        CREATE TABLE law_history.graph_progress (
            snapshot_id bigint PRIMARY KEY REFERENCES law_history.snapshots(id),
            indexed_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX history_article_content ON law_history.articles(content_hash);
    ''')


def downgrade():
    op.execute('''DROP TABLE law_history.graph_progress;
        DROP TABLE law_history.text_chunks; DROP TABLE law_history.search_chunks;
        DROP TABLE law_history.index_texts; DROP INDEX law_history.history_article_content''')
