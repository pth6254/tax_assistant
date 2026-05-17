-- ================================================================
-- 002_user_profile.sql — 사용자 프로필 필드 추가
-- ================================================================
ALTER TABLE users ADD COLUMN IF NOT EXISTS name  TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL DEFAULT '';
