-- ================================================================
-- 세무 자동화 어시스턴트 - 로컬 PostgreSQL 초기화 스크립트
-- ================================================================
-- 실행 방법:
--   psql -U postgres -d tax_db -f init_db.sql
--
-- DB 먼저 생성:
--   psql -U postgres -c "CREATE DATABASE tax_db;"
-- ================================================================

-- pgvector 확장 활성화
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()

-- ── 1. 사용자 테이블 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT        NOT NULL UNIQUE,
    password    TEXT        NOT NULL,        -- bcrypt 해시
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 2. 문서 벡터 저장소 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id          BIGSERIAL   PRIMARY KEY,
    content     TEXT        NOT NULL,
    embedding   VECTOR(1536),               -- text-embedding-3-small 차원
    metadata    JSONB       NOT NULL DEFAULT '{}'
);

-- 빠른 유사도 검색을 위한 IVFFlat 인덱스
-- (문서 수가 1만 건 이상이 되면 성능 향상)
CREATE INDEX IF NOT EXISTS documents_embedding_idx
    ON documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 메타데이터 필터링 인덱스
CREATE INDEX IF NOT EXISTS documents_metadata_law_idx
    ON documents
    USING gin (metadata);

-- ── 3. 채팅 로그 테이블 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_logs (
    id          BIGSERIAL   PRIMARY KEY,
    session_id  UUID        NOT NULL,        -- users.id 참조
    message     JSONB       NOT NULL,        -- {"role": "user"|"assistant", "content": "..."}
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_logs_session_idx
    ON chat_logs (session_id, created_at DESC);

-- ── 4. 유사도 검색 함수 ─────────────────────────────────────────
-- law_name 필터: 'ALL' 이면 전체 검색, 특정 세법이면 메타데이터 필터 적용
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding VECTOR(1536),
    match_count     INT,
    law_filter      TEXT DEFAULT 'ALL'
)
RETURNS TABLE (
    id       BIGINT,
    content  TEXT,
    metadata JSONB,
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

-- 완료 메시지
DO $$
BEGIN
    RAISE NOTICE '✅ 세무 자동화 어시스턴트 DB 초기화 완료';
    RAISE NOTICE '   테이블: users, documents, chat_logs';
    RAISE NOTICE '   함수:   match_documents()';
END;
$$;
