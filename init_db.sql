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
-- qwen3-embedding:4b = 2560차원 (기존 OpenAI 1536 → 2560으로 변경)
CREATE TABLE IF NOT EXISTS documents (
    id          BIGSERIAL   PRIMARY KEY,
    content     TEXT        NOT NULL,
    embedding   VECTOR(2560),
    metadata    JSONB       NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS documents_embedding_idx
    ON documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS documents_metadata_law_idx
    ON documents
    USING gin (metadata);

-- ── 3. 채팅 로그 테이블 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_logs (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  UUID        NOT NULL,
    message     JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_logs_session_idx
    ON chat_logs (session_id, created_at DESC);

-- ── 4. 유사도 검색 함수 ─────────────────────────────────────────
-- 차원을 2560으로 변경
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding VECTOR(2560),
    match_count     INT,
    law_filter      TEXT DEFAULT 'ALL'
)
RETURNS TABLE (
    id         BIGINT,
    content    TEXT,
    metadata   JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF law_filter = 'ALL' THEN
        RETURN QUERY
        SELECT
            d.id,
            d.content,
            d.metadata,
            1 - (d.embedding <=> query_embedding) AS similarity
        FROM documents d
        ORDER BY d.embedding <=> query_embedding
        LIMIT match_count;
    ELSE
        RETURN QUERY
        SELECT
            d.id,
            d.content,
            d.metadata,
            1 - (d.embedding <=> query_embedding) AS similarity
        FROM documents d
        WHERE d.metadata->>'law_name' = law_filter
        ORDER BY d.embedding <=> query_embedding
        LIMIT match_count;
    END IF;
END;
$$;

DO $$
BEGIN
    RAISE NOTICE '✅ DB 초기화 완료 (Ollama qwen3-embedding:4b, 2560차원)';
END;
$$;