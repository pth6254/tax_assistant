-- ================================================================
-- V002 롤백: law_articles 테이블 삭제
--
-- 실행:
--   psql -U postgres -h localhost -p 5433 -d tax_db \
--        -f migrations/V002__add_law_articles.down.sql
--
-- 주의: law_articles의 모든 데이터가 삭제된다.
-- ================================================================

DROP TABLE IF EXISTS law_articles CASCADE;

-- set_updated_at 함수는 다른 테이블의 트리거에서 사용할 수 있으므로
-- 해당 함수를 참조하는 트리거가 없을 때만 삭제한다.
DO $$
DECLARE
    trigger_count INT;
BEGIN
    SELECT COUNT(*) INTO trigger_count
    FROM information_schema.triggers
    WHERE trigger_name LIKE '%updated_at%'
      AND event_object_table != 'law_articles';

    IF trigger_count = 0 THEN
        DROP FUNCTION IF EXISTS set_updated_at() CASCADE;
        RAISE NOTICE '  set_updated_at 함수 삭제 완료';
    ELSE
        RAISE NOTICE '  set_updated_at 함수는 다른 테이블에서 사용 중이므로 유지';
    END IF;
END;
$$;

DO $$
BEGIN
    RAISE NOTICE '✅ V002 롤백 완료: law_articles 테이블 삭제';
END;
$$;
