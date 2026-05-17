-- ================================================================
-- 003_conversations.sql — 다중 대화 세션 지원
-- ================================================================

-- 1. conversations 테이블 생성
CREATE TABLE IF NOT EXISTS conversations (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL,
    title      TEXT        NOT NULL DEFAULT '새 대화',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS conversations_user_idx
    ON conversations (user_id, updated_at DESC);

-- 2. chat_logs 마이그레이션
--    session_id(=user_id 혼용) → conversation_id 로 의미 명확화
--    기존 데이터는 conversation과 연결 불가 → 초기화
TRUNCATE chat_logs;

ALTER TABLE chat_logs RENAME COLUMN session_id TO conversation_id;

DROP INDEX IF EXISTS chat_logs_session_idx;

CREATE INDEX IF NOT EXISTS chat_logs_conversation_idx
    ON chat_logs (conversation_id, created_at DESC);
