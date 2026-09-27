"""Structure and provenance survive user-document ingestion."""
from io import BytesIO
import zipfile

from app.services.document.extractors import DocumentBlock, ExtractedDocument, extract_document
from app.services.document.structured_chunker import chunk_document


def _package(parts):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return output.getvalue()


def test_docx_preserves_heading_and_table_row_fields():
    data = _package({'word/document.xml': '''<w:document xmlns:w="urn:w"><w:body>
      <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>2025년 사업소득</w:t></w:r></w:p>
      <w:tbl><w:tr><w:trPr><w:tblHeader/></w:trPr>
        <w:tc><w:p><w:r><w:t>항목</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>금액</w:t></w:r></w:p></w:tc></w:tr>
        <w:tr><w:tc><w:p><w:r><w:t>매출</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>12,000원</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''})
    document = extract_document(data, '신고.docx')
    chunks = chunk_document(document)
    row = next(chunk for chunk in chunks if '매출 | 12,000원' in chunk.text)
    assert row.metadata['kind'] == 'table_row'
    assert row.metadata['table'] == 1 and row.metadata['row'] == 2
    assert row.metadata['heading'] == '2025년 사업소득'
    assert '표 머리글: 항목 | 금액' in row.text


def test_html_keeps_headings_and_table_cells_but_drops_script():
    document = extract_document(
        b'<h2>VAT 2025</h2><p>Return</p><table><tr><th>Item</th><th>Amount</th></tr>'
        b'<tr><td>Sales</td><td>100</td></tr></table><script>private</script>', 'form.html')
    chunks = chunk_document(document)
    row = next(chunk for chunk in chunks if 'Sales | 100' in chunk.text)
    assert row.metadata['table'] == 1 and row.metadata['row'] == 2
    assert row.metadata['heading'] == 'VAT 2025'
    assert 'Item | Amount' in row.text
    assert all('private' not in chunk.text for chunk in chunks)


def test_explicit_article_boundary_preserves_branch_number_and_page():
    document = ExtractedDocument(
        '법령', 'pdf', 'text', blocks=(DocumentBlock(
            '제59조의4(세액공제)\n① 공제한다.\n제60조(신고)\n① 신고한다.', page=3),))
    chunks = chunk_document(document)
    assert chunks[0].metadata['article_no'] == '제59조의4'
    assert any(chunk.metadata['article_no'] == '제60조' for chunk in chunks)
    assert chunks[1].metadata['kind'] == 'clause'
    assert chunks[1].metadata['paragraph_ref'] == '①'
    assert all(chunk.metadata['page'] == 3 for chunk in chunks)
    assert all('페이지 3' in chunk.text for chunk in chunks)


def test_page_slide_and_ocr_boundaries_are_not_merged():
    document = ExtractedDocument('내용', 'pdf', 'ocr', blocks=(
        DocumentBlock('2024년 금액 100원', page=1, ocr=True),
        DocumentBlock('2025년 금액 200원', page=2, ocr=False)))
    chunks = chunk_document(document)
    assert len(chunks) == 2
    assert chunks[0].metadata['page'] == 1 and chunks[0].metadata['ocr'] is True
    assert chunks[1].metadata['page'] == 2 and chunks[1].metadata['ocr'] is False


def test_legal_paragraphs_in_separate_source_blocks_keep_parent_article():
    document = ExtractedDocument('조문', 'docx', 'text', blocks=(
        DocumentBlock('제59조의4(공제)'),
        DocumentBlock('① 첫 번째 항'),
        DocumentBlock('제1호 공제 대상')))
    chunks = chunk_document(document)
    assert [chunk.metadata['kind'] for chunk in chunks] == ['article', 'clause', 'item']
    assert chunks[2].metadata['article_no'] == '제59조의4'
    assert chunks[2].metadata['paragraph_ref'] == '①'
    assert chunks[2].metadata['item_ref'] == '제1호'


def test_hwpx_sections_keep_source_location():
    data = _package({'Contents/section0.xml': '<hs:sec xmlns:hs="urn:s" xmlns:hp="urn:p">'
                     '<hp:p><hp:run><hp:t>첫 구역</hp:t></hp:run></hp:p></hs:sec>',
                     'Contents/section1.xml': '<hs:sec xmlns:hs="urn:s" xmlns:hp="urn:p">'
                     '<hp:p><hp:run><hp:t>두 번째 구역</hp:t></hp:run></hp:p></hs:sec>'})
    chunks = chunk_document(extract_document(data, '문서.hwpx'))
    assert [chunk.metadata['section'] for chunk in chunks] == [1, 2]


def test_pptx_slide_boundaries_keep_source_location():
    data = _package({'ppt/presentation.xml': '<presentation/>',
                     'ppt/slides/slide1.xml': '<a:p xmlns:a="urn:a"><a:t>첫 슬라이드</a:t></a:p>',
                     'ppt/slides/slide2.xml': '<a:p xmlns:a="urn:a"><a:t>두 번째 슬라이드</a:t></a:p>'})
    chunks = chunk_document(extract_document(data, '발표.pptx'))
    assert [chunk.metadata['slide'] for chunk in chunks] == [1, 2]
