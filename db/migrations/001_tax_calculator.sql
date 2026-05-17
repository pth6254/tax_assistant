-- 001_tax_calculator.sql — 세율 구간 & 공제 항목 테이블 + 2024년 시드 데이터

CREATE TABLE IF NOT EXISTS tax_brackets (
    id                  BIGSERIAL PRIMARY KEY,
    tax_type            TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'default',
    bracket_from        BIGINT NOT NULL,
    bracket_to          BIGINT NULL,
    rate                NUMERIC(5,4) NOT NULL,
    progressive_deduction BIGINT NOT NULL DEFAULT 0,
    effective_date      DATE NOT NULL,
    source_article      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tax_deductions (
    id              BIGSERIAL PRIMARY KEY,
    tax_type        TEXT NOT NULL,
    deduction_name  TEXT NOT NULL,
    condition       JSONB NOT NULL DEFAULT '{}',
    amount          BIGINT NULL,
    rate            NUMERIC(5,4) NULL,
    max_amount      BIGINT NULL,
    effective_date  DATE NOT NULL,
    source_article  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tax_brackets_lookup_idx
    ON tax_brackets (tax_type, category, effective_date DESC);

CREATE INDEX IF NOT EXISTS tax_deductions_lookup_idx
    ON tax_deductions (tax_type, deduction_name, effective_date DESC);

-- ── 소득세 세율 (소득세법 제55조) ────────────────────────────────────────────
INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction, effective_date, source_article) VALUES
    ('소득세', 'default',          0,           14000000,  0.0600,         0, '2024-01-01', '소득세법 제55조'),
    ('소득세', 'default',   14000000,           50000000,  0.1500,   1260000, '2024-01-01', '소득세법 제55조'),
    ('소득세', 'default',   50000000,           88000000,  0.2400,   5760000, '2024-01-01', '소득세법 제55조'),
    ('소득세', 'default',   88000000,          150000000,  0.3500,  15440000, '2024-01-01', '소득세법 제55조'),
    ('소득세', 'default',  150000000,          300000000,  0.3800,  19940000, '2024-01-01', '소득세법 제55조'),
    ('소득세', 'default',  300000000,          500000000,  0.4000,  25940000, '2024-01-01', '소득세법 제55조'),
    ('소득세', 'default',  500000000,         1000000000,  0.4200,  35940000, '2024-01-01', '소득세법 제55조'),
    ('소득세', 'default', 1000000000,                NULL,  0.4500,  65940000, '2024-01-01', '소득세법 제55조');

-- ── 상속세 세율 (상속세및증여세법 제26조) ────────────────────────────────────
INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction, effective_date, source_article) VALUES
    ('상속세', 'default',           0,          100000000,  0.1000,         0, '2024-01-01', '상속세및증여세법 제26조'),
    ('상속세', 'default',   100000000,          500000000,  0.2000,  10000000, '2024-01-01', '상속세및증여세법 제26조'),
    ('상속세', 'default',   500000000,         1000000000,  0.3000,  60000000, '2024-01-01', '상속세및증여세법 제26조'),
    ('상속세', 'default',  1000000000,         3000000000,  0.4000, 160000000, '2024-01-01', '상속세및증여세법 제26조'),
    ('상속세', 'default',  3000000000,               NULL,  0.5000, 460000000, '2024-01-01', '상속세및증여세법 제26조');

-- ── 증여세 세율 (상속세및증여세법 제26조) ────────────────────────────────────
INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction, effective_date, source_article) VALUES
    ('증여세', 'default',           0,          100000000,  0.1000,         0, '2024-01-01', '상속세및증여세법 제26조'),
    ('증여세', 'default',   100000000,          500000000,  0.2000,  10000000, '2024-01-01', '상속세및증여세법 제26조'),
    ('증여세', 'default',   500000000,         1000000000,  0.3000,  60000000, '2024-01-01', '상속세및증여세법 제26조'),
    ('증여세', 'default',  1000000000,         3000000000,  0.4000, 160000000, '2024-01-01', '상속세및증여세법 제26조'),
    ('증여세', 'default',  3000000000,               NULL,  0.5000, 460000000, '2024-01-01', '상속세및증여세법 제26조');

-- ── 양도소득세 세율 ─────────────────────────────────────────────────────────
-- 기본세율 (소득세법 제104조) — 소득세와 동일 8구간
INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction, effective_date, source_article) VALUES
    ('양도소득세', '기본',          0,           14000000,  0.0600,         0, '2024-01-01', '소득세법 제104조'),
    ('양도소득세', '기본',   14000000,           50000000,  0.1500,   1260000, '2024-01-01', '소득세법 제104조'),
    ('양도소득세', '기본',   50000000,           88000000,  0.2400,   5760000, '2024-01-01', '소득세법 제104조'),
    ('양도소득세', '기본',   88000000,          150000000,  0.3500,  15440000, '2024-01-01', '소득세법 제104조'),
    ('양도소득세', '기본',  150000000,          300000000,  0.3800,  19940000, '2024-01-01', '소득세법 제104조'),
    ('양도소득세', '기본',  300000000,          500000000,  0.4000,  25940000, '2024-01-01', '소득세법 제104조'),
    ('양도소득세', '기본',  500000000,         1000000000,  0.4200,  35940000, '2024-01-01', '소득세법 제104조'),
    ('양도소득세', '기본', 1000000000,                NULL,  0.4500,  65940000, '2024-01-01', '소득세법 제104조'),
-- 단기 보유 (1년 미만)
    ('양도소득세', '단기1년미만',   0,                NULL,  0.7000,         0, '2024-01-01', '소득세법 제104조'),
-- 단기 보유 (1년 이상 2년 미만)
    ('양도소득세', '단기2년미만',   0,                NULL,  0.6000,         0, '2024-01-01', '소득세법 제104조');

-- ── 소득세 공제 항목 ─────────────────────────────────────────────────────────
INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date, source_article) VALUES
    ('소득세', '기본공제',              1500000, NULL, NULL, '{}', '2024-01-01', '소득세법 제50조'),
    ('소득세', '표준세액공제_사업자',    120000, NULL, NULL, '{}', '2024-01-01', '소득세법 제59조의4'),
    ('소득세', '양도소득기본공제',      2500000, NULL, NULL, '{}', '2024-01-01', '소득세법 제103조');

-- ── 증여세 공제 항목 ─────────────────────────────────────────────────────────
INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date, source_article) VALUES
    ('증여세', '증여재산공제_배우자',       600000000, NULL, NULL, '{"relation":"배우자"}',                              '2024-01-01', '상속세및증여세법 제53조'),
    ('증여세', '증여재산공제_직계존비속',    50000000, NULL, NULL, '{"relation":"직계존비속"}',                          '2024-01-01', '상속세및증여세법 제53조'),
    ('증여세', '증여재산공제_직계존비속_미성년', 20000000, NULL, NULL, '{"relation":"직계존비속","is_minor":true}',       '2024-01-01', '상속세및증여세법 제53조'),
    ('증여세', '증여재산공제_기타친족',      10000000, NULL, NULL, '{"relation":"기타친족"}',                            '2024-01-01', '상속세및증여세법 제53조');

-- ── 상속세 공제 항목 ─────────────────────────────────────────────────────────
INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date, source_article) VALUES
    ('상속세', '기초공제',           200000000, NULL, NULL, '{}', '2024-01-01', '상속세및증여세법 제18조'),
    ('상속세', '일괄공제',           500000000, NULL, NULL, '{}', '2024-01-01', '상속세및증여세법 제21조'),
    ('상속세', '배우자상속공제_최소', 500000000, NULL, NULL, '{}', '2024-01-01', '상속세및증여세법 제19조');

-- ── 양도소득세 공제 항목 (장기보유특별공제) ──────────────────────────────────
INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date, source_article) VALUES
    ('양도소득세', '장기보유특별공제_3년',           NULL, 0.0600, NULL, '{"holding_years":3}',                          '2024-01-01', '소득세법 제95조'),
    ('양도소득세', '장기보유특별공제_4년',           NULL, 0.0800, NULL, '{"holding_years":4}',                          '2024-01-01', '소득세법 제95조'),
    ('양도소득세', '장기보유특별공제_5년',           NULL, 0.1000, NULL, '{"holding_years":5}',                          '2024-01-01', '소득세법 제95조'),
    ('양도소득세', '장기보유특별공제_10년이상',      NULL, 0.2000, NULL, '{"holding_years":10}',                         '2024-01-01', '소득세법 제95조'),
    ('양도소득세', '장기보유특별공제_15년이상_1주택', NULL, 0.3000, NULL, '{"holding_years":15,"is_one_home":true}',     '2024-01-01', '소득세법 제95조');
