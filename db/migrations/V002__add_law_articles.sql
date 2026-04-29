-- ================================================================
-- V002: law_articles 테이블 추가
-- 국가법령정보 API에서 수집한 조문 단위 데이터를 저장한다.
--
-- 전제:
--   V001(init_db.sql)이 먼저 실행되어
--   vector / pgcrypto 확장이 활성화되어 있어야 한다.
--
-- 적용 (실행 중인 컨테이너):
--   psql -U postgres -h localhost -p 5433 -d tax_db \
--        -f migrations/V002__add_law_articles.sql
--
-- 롤백:
--   psql -U postgres -h localhost -p 5433 -d tax_db \
--        -f migrations/V002__add_law_articles.down.sql
--
-- 임베딩 모델: qwen3-embedding:4b = 2560차원
--   → documents 테이블(VECTOR(2560))과 동일 모델 사용.
--   .env의 EMBED_MODEL 및 init_db.sql 주석에서 교차 확인함.
-- ================================================================

-- ── law_articles 테이블 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS law_articles (
    id              BIGSERIAL       PRIMARY KEY,

    -- 법령 식별
    law_name        TEXT            NOT NULL,
    -- 예: "법률", "대통령령", "총리령", "부령"
    law_type        TEXT            NOT NULL DEFAULT '',
    -- chat_service._LAW_KW 세목명과 매핑 (예: "소득세법", "ALL")
    -- law_name에서 자동 추론하지만, 검색 필터링 성능을 위해 별도 컬럼으로 관리
    tax_type        TEXT            NOT NULL DEFAULT 'ALL',

    -- 조문 내용
    -- 예: "제1조", "제3조의2"
    article_no      TEXT            NOT NULL,
    article_title   TEXT            NOT NULL DEFAULT '',
    -- 조문내용 + 항내용 합산 텍스트 (law_parser_service.parse_articles 출력)
    article_text    TEXT            NOT NULL,

    -- 날짜 (API 응답 YYYYMMDD 형식 그대로 보존)
    effective_date  TEXT            NOT NULL DEFAULT '',
    amendment_date  TEXT            NOT NULL DEFAULT '',

    -- 원문 출처 URL
    -- 형식 예: https://www.law.go.kr/법령/소득세법
    -- Phase 4에서 get_law_detail MST 기반으로 채울 예정
    source_url      TEXT            NOT NULL DEFAULT '',

    -- 중복/변경 감지용 해시
    -- Python: hashlib.sha256(article_text.encode('utf-8')).hexdigest()
    -- SQL:    encode(digest(article_text, 'sha256'), 'hex')  (pgcrypto)
    -- 개정 감지: 동일 (law_name, article_no)의 content_hash가 바뀌면 개정 발생
    content_hash    TEXT            NOT NULL,

    -- 벡터 임베딩
    -- qwen3-embedding:4b = 2560차원
    -- documents 테이블과 동일 모델·차원 → 동일 match_documents 함수 호환 가능
    embedding       VECTOR(2560),

    -- 현행 여부: 개정 발생 시 구버전 is_current=FALSE, 신버전 INSERT
    -- TRUE인 행만 RAG 검색 대상으로 사용
    is_current      BOOLEAN         NOT NULL DEFAULT TRUE,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- ── 인덱스 ──────────────────────────────────────────────────────

-- [1] 완전 중복 방지
--   동일 법령 + 동일 조문번호 + 동일 내용의 재삽입을 막는다.
--   같은 조문이 개정된 경우(content_hash가 다름)는 별도 행으로 허용하고
--   is_current 플래그로 현행/구버전을 구분한다.
CREATE UNIQUE INDEX IF NOT EXISTS law_articles_dedup_idx
    ON law_articles (law_name, article_no, content_hash);

-- [2] 현행 조문 빠른 조회
--   Phase 4 동기화에서 "현재 저장된 현행 조문의 hash" 조회에 사용한다.
CREATE INDEX IF NOT EXISTS law_articles_current_idx
    ON law_articles (law_name, article_no)
    WHERE is_current = TRUE;

-- [3] 법령별 전체 조문 조회 (동기화 대상 확인, 관리 UI 등)
-- 참고: pgvector ivfflat/hnsw 인덱스는 최대 2000차원까지만 지원.
--       2560차원 embedding 컬럼은 인덱스 없이 sequential scan으로 검색.
CREATE INDEX IF NOT EXISTS law_articles_law_name_idx
    ON law_articles (law_name, is_current);

-- ── updated_at 자동 갱신 트리거 ──────────────────────────────────
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

-- ── 완료 메시지 ─────────────────────────────────────────────────
DO $$
BEGIN
    RAISE NOTICE '✅ V002 적용 완료: law_articles 테이블 생성 (VECTOR(2560), ivfflat lists=50)';
END;
$$;
