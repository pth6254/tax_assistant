"""Isolated, append-only historical law archive; no changes to live retrieval.

Revision ID: 20260922_0003
Revises: 20260822_0002
"""
from alembic import op

revision = '20260922_0003'
down_revision = '20260822_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
    CREATE SCHEMA law_history;
    CREATE TABLE law_history.scope (
        id bigserial PRIMARY KEY, law_name text NOT NULL UNIQUE,
        seed_mst text NOT NULL, law_id text,
        discovery_status text NOT NULL DEFAULT 'pending'
            CHECK(discovery_status IN ('pending','complete','failed')),
        expected_count integer, error_type text,
        discovered_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE law_history.laws (
        law_id text PRIMARY KEY, seed_name text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE law_history.versions (
        id bigserial PRIMARY KEY,
        law_id text NOT NULL REFERENCES law_history.laws(law_id),
        mst text NOT NULL, effective_date date NOT NULL,
        law_name text NOT NULL, law_type text NOT NULL,
        promulgation_date date, promulgation_number text NOT NULL,
        revision_type text NOT NULL, listing_status text NOT NULL,
        listing_metadata jsonb NOT NULL,
        fetch_status text NOT NULL DEFAULT 'pending'
            CHECK(fetch_status IN ('pending','complete','failed')),
        attempts integer NOT NULL DEFAULT 0, error_type text,
        last_attempt_at timestamptz,
        UNIQUE(law_id,mst,effective_date)
    );
    CREATE INDEX history_versions_timeline ON law_history.versions(law_id,effective_date,promulgation_date);
    CREATE TABLE law_history.snapshots (
        id bigserial PRIMARY KEY,
        version_id bigint NOT NULL REFERENCES law_history.versions(id),
        content_hash text NOT NULL, raw_xml text NOT NULL,
        source_url text NOT NULL, parser_version text NOT NULL,
        collected_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(version_id,content_hash,parser_version)
    );
    CREATE TABLE law_history.articles (
        id bigserial PRIMARY KEY,
        snapshot_id bigint NOT NULL REFERENCES law_history.snapshots(id),
        source_order integer NOT NULL, source_key text NOT NULL,
        article_number text NOT NULL, article_branch text NOT NULL,
        unit_kind text NOT NULL, title text NOT NULL,
        body text NOT NULL, content_hash text NOT NULL,
        structure jsonb NOT NULL,
        UNIQUE(snapshot_id,source_order)
    );
    CREATE INDEX history_articles_number ON law_history.articles(snapshot_id,article_number,article_branch);
    CREATE TABLE law_history.supplements (
        id bigserial PRIMARY KEY,
        snapshot_id bigint NOT NULL REFERENCES law_history.snapshots(id),
        source_order integer NOT NULL, source_key text NOT NULL,
        body text NOT NULL, structure jsonb NOT NULL,
        UNIQUE(snapshot_id,source_order)
    );
    CREATE TABLE law_history.runs (
        id bigserial PRIMARY KEY, phase text NOT NULL,
        status text NOT NULL DEFAULT 'running',
        started_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz, heartbeat_at timestamptz NOT NULL DEFAULT now(),
        completed integer NOT NULL DEFAULT 0, failed integer NOT NULL DEFAULT 0,
        error_type text
    );
    CREATE VIEW law_history.version_sequence AS
      SELECT id,law_id,mst,effective_date,promulgation_date,
        lag(id) OVER(PARTITION BY law_id ORDER BY effective_date,promulgation_date,mst) AS previous_observed_version_id
      FROM law_history.versions;
    CREATE VIEW law_history.coverage AS
      SELECT s.id,s.law_name,s.law_id,s.discovery_status,s.expected_count,s.error_type,
        count(v.id) AS listed,
        count(v.id) FILTER(WHERE v.fetch_status='complete') AS collected,
        count(v.id) FILTER(WHERE v.fetch_status='pending') AS pending,
        count(v.id) FILTER(WHERE v.fetch_status='failed') AS failed
      FROM law_history.scope s LEFT JOIN law_history.versions v ON s.law_id=v.law_id
      GROUP BY s.id;
    ''')


def downgrade():
    # Explicit archive rollback deletes collected history; never run automatically.
    op.execute('DROP VIEW law_history.coverage; DROP VIEW law_history.version_sequence')
    for table in ('runs','supplements','articles','snapshots','versions','laws','scope'):
        op.execute(f'DROP TABLE law_history.{table}')
    op.execute('DROP SCHEMA law_history')
