-- ================================================================
-- 세무 자동화 어시스턴트 - PostgreSQL 초기화 스크립트
-- Ollama qwen3-embedding:4b 기준 (2560차원)
-- ================================================================
-- 실행 방법:
--   psql -U postgres -d tax_db -f init_db.sql
-- ================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── 1. 사용자 테이블 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT        NOT NULL UNIQUE,
    password    TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 2. 문서 벡터 저장소 ─────────────────────────────────────────
-- qwen3-embedding:4b = 2560차원
CREATE TABLE IF NOT EXISTS documents (
    id          BIGSERIAL   PRIMARY KEY,
    content     TEXT        NOT NULL,
    embedding   VECTOR(2560),
    metadata    JSONB       NOT NULL DEFAULT '{}',
    user_id     UUID        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ivfflat/hnsw 인덱스는 최대 2000차원까지만 지원 → 2560차원은 sequential scan 사용
CREATE INDEX IF NOT EXISTS documents_metadata_law_idx
    ON documents
    USING gin (metadata);

CREATE INDEX IF NOT EXISTS documents_user_id_idx
    ON documents (user_id);

CREATE INDEX IF NOT EXISTS documents_user_created_idx
    ON documents (user_id, created_at DESC);

-- ── 3. 채팅 로그 테이블 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_logs (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  UUID        NOT NULL,
    message     JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_logs_session_idx
    ON chat_logs (session_id, created_at DESC);

-- ── 4. 법령 조문 테이블 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS law_articles (
    id              BIGSERIAL   PRIMARY KEY,
    law_name        TEXT        NOT NULL,
    law_type        TEXT        NOT NULL DEFAULT '',
    tax_type        TEXT        NOT NULL DEFAULT 'ALL',
    article_no      TEXT        NOT NULL,
    article_title   TEXT        NOT NULL DEFAULT '',
    article_text    TEXT        NOT NULL,
    effective_date  TEXT        NOT NULL DEFAULT '',
    amendment_date  TEXT        NOT NULL DEFAULT '',
    source_url      TEXT        NOT NULL DEFAULT '',
    content_hash    TEXT        NOT NULL,
    embedding       VECTOR(2560),
    is_current      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 완전 중복 방지 (동일 법령 + 조문 + 내용)
CREATE UNIQUE INDEX IF NOT EXISTS law_articles_dedup_idx
    ON law_articles (law_name, article_no, content_hash);

-- 현행 조문 빠른 조회
CREATE INDEX IF NOT EXISTS law_articles_current_idx
    ON law_articles (law_name, article_no)
    WHERE is_current = TRUE;

-- 법령별 전체 조회
CREATE INDEX IF NOT EXISTS law_articles_law_name_idx
    ON law_articles (law_name, is_current);

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS law_articles_updated_at ON law_articles;
CREATE TRIGGER law_articles_updated_at
    BEFORE UPDATE ON law_articles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DO $$
BEGIN
    RAISE NOTICE '✅ DB 초기화 완료 (Ollama qwen3-embedding:4b, 2560차원)';
END;
$$;