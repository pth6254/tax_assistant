-- 007_vat_penalty_seed.sql — 부가가치세·가산세 계산기용 세율 시드 데이터

-- ── 부가가치세 세율 (부가가치세법 제30조) ────────────────────────────────────
INSERT INTO tax_brackets (tax_type, category, bracket_from, bracket_to, rate, progressive_deduction, effective_date, source_article) VALUES
    ('부가가치세', 'default', 0, NULL, 0.1000, 0, '2024-01-01', '부가가치세법 제30조');

-- ── 가산세 (국세기본법 제47조의2·제47조의3) ─────────────────────────────────
-- 납부지연가산세(제47조의4, 1일 10만분의 22)는 rate NUMERIC(5,4) 정밀도로
-- 표현 불가능해(소수점 4자리까지만 저장) DB 시드 대신 penalty_tax.py의 코드
-- 상수로 고정한다.
INSERT INTO tax_deductions (tax_type, deduction_name, amount, rate, max_amount, condition, effective_date, source_article) VALUES
    ('가산세', '무신고가산세_일반',   NULL, 0.2000, NULL, '{}', '2024-01-01', '국세기본법 제47조의2'),
    ('가산세', '무신고가산세_부정',   NULL, 0.4000, NULL, '{}', '2024-01-01', '국세기본법 제47조의2'),
    ('가산세', '과소신고가산세_일반', NULL, 0.1000, NULL, '{}', '2024-01-01', '국세기본법 제47조의3'),
    ('가산세', '과소신고가산세_부정', NULL, 0.4000, NULL, '{}', '2024-01-01', '국세기본법 제47조의3');
