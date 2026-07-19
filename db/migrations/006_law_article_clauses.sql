-- ================================================================
-- 006_law_article_clauses.sql — 긴 조문의 항(項) 단위 보조 임베딩
--
-- 조문 전체를 벡터 1개로 임베딩하면 여러 항을 가진 긴 조문에서
-- 특정 항의 내용이 희석되어 검색에 걸리지 않는 문제가 있다
-- (예: 소득세법 제59조의4 ⑨항의 표준세액공제).
-- 긴 조문을 항 단위로 분할해 보조 벡터를 저장하고, 검색 시
-- 조문 벡터와 항 벡터를 함께 조회한다 (컨텍스트는 항상 조문 전체 제공).
-- ================================================================

CREATE TABLE IF NOT EXISTS law_article_clauses (
    id           BIGSERIAL   PRIMARY KEY,
    article_id   BIGINT      NOT NULL REFERENCES law_articles(id) ON DELETE CASCADE,
    clause_label TEXT        NOT NULL,           -- 예: '①', '⑨', 'header'
    clause_text  TEXT        NOT NULL,
    embedding    VECTOR(2560),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS law_article_clauses_embedding_hnsw_idx
    ON law_article_clauses
    USING hnsw ((embedding::halfvec(2560)) halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS law_article_clauses_article_idx
    ON law_article_clauses (article_id);
