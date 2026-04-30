-- ================================================================
-- V003: documents 테이블에 user_id 컬럼 추가
-- 업로드된 PDF 문서를 사용자 단위로 격리한다.
--
-- 전제:
--   V001(init_db.sql)이 먼저 실행되어 documents 테이블이 존재해야 한다.
--
-- 적용:
--   psql -U postgres -h localhost -p 5433 -d tax_db \
--        -f migrations/V003__add_user_id_to_documents.sql
--
-- 롤백:
--   ALTER TABLE documents DROP COLUMN IF EXISTS user_id;
--   DROP INDEX IF EXISTS documents_user_id_idx;
-- ================================================================

ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id UUID;

CREATE INDEX IF NOT EXISTS documents_user_id_idx
    ON documents (user_id);

DO $$
BEGIN
    RAISE NOTICE '✅ V003 적용 완료: documents.user_id 컬럼 및 인덱스 추가';
END;
$$;
