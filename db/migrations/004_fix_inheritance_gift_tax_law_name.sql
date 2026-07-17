-- ================================================================
-- 004_fix_inheritance_gift_tax_law_name.sql
-- 상속세및증여세법(붙여쓰기) → 상속세 및 증여세법(국가법령정보 API 공식 표기)로 통일.
-- 001_tax_calculator.sql이 이미 적용된 DB의 기존 데이터를 갱신한다.
-- ================================================================

UPDATE law_articles
SET tax_type = '상속세 및 증여세법'
WHERE tax_type = '상속세및증여세법';

UPDATE tax_brackets
SET source_article = REPLACE(source_article, '상속세및증여세법', '상속세 및 증여세법')
WHERE source_article LIKE '상속세및증여세법%';

UPDATE tax_deductions
SET source_article = REPLACE(source_article, '상속세및증여세법', '상속세 및 증여세법')
WHERE source_article LIKE '상속세및증여세법%';
