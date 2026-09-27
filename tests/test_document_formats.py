"""Upload-format extraction and security boundary tests."""
from io import BytesIO
from unittest.mock import patch
import zipfile

import pytest
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from app.services.document.extractors import extract_document, ExtractionError, OCRUnavailable


def package(parts):
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return output.getvalue()


def test_docx_extracts_paragraphs_and_table_cells():
    data = package({'word/document.xml': '''<w:document xmlns:w="urn:w"><w:body>
      <w:p><w:r><w:t>사업소득</w:t></w:r></w:p>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>수입 12,000원</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''})
    result = extract_document(data, '증빙.docx')
    assert result.text.splitlines() == ['사업소득', '수입 12,000원']


def test_hwpx_extracts_sections_without_header_or_script():
    data = package({'Contents/section0.xml': '''<hs:sec xmlns:hs="urn:section" xmlns:hp="urn:paragraph">
      <hp:p><hp:run><hp:t>증여세 신고</hp:t></hp:run></hp:p></hs:sec>''',
                    'Contents/header.xml': '<head>ignore this</head>',
                    'Contents/Scripts/source.js': 'untrusted'})
    result = extract_document(data, '문서.hwpx')
    assert '증여세 신고' in result.text and 'ignore this' not in result.text


def test_pptx_keeps_slide_order_and_table_text():
    data = package({'ppt/presentation.xml': '<presentation/>',
                    'ppt/slides/slide2.xml': '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:p><a:t>두 번째</a:t></a:p></p:sld>',
                    'ppt/slides/slide1.xml': '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:p><a:t>첫 번째</a:t></a:p></p:sld>'})
    result = extract_document(data, '안내.pptx')
    assert result.text.index('첫 번째') < result.text.index('두 번째')
    assert '[슬라이드 1]' in result.text and result.pages == 2


def test_pptx_uses_presentation_order_when_slides_are_rearranged():
    data = package({'ppt/presentation.xml': '''<p:presentation xmlns:p="urn:p" xmlns:r="urn:r">
        <p:sldIdLst><p:sldId r:id="rId2"/><p:sldId r:id="rId1"/></p:sldIdLst></p:presentation>''',
                    'ppt/_rels/presentation.xml.rels': '''<Relationships>
        <Relationship Id="rId1" Target="slides/slide1.xml"/>
        <Relationship Id="rId2" Target="slides/slide2.xml"/></Relationships>''',
                    'ppt/slides/slide1.xml': '<a:p xmlns:a="urn:a"><a:t>원래 첫 슬라이드</a:t></a:p>',
                    'ppt/slides/slide2.xml': '<a:p xmlns:a="urn:a"><a:t>앞으로 옮긴 슬라이드</a:t></a:p>'})
    text = extract_document(data, 'slides.pptx').text
    assert text.index('앞으로 옮긴 슬라이드') < text.index('원래 첫 슬라이드')


def test_html_drops_active_content_and_decodes_korean():
    data = b'<html><body><h1>Tax</h1><script>alert("private")</script><p>VAT &amp; duty</p></body></html>'
    result = extract_document(data, 'guide.html')
    assert 'Tax' in result.text and 'VAT & duty' in result.text
    assert 'private' not in result.text


def test_mismatched_or_oversized_packages_are_rejected():
    with pytest.raises(ExtractionError):
        extract_document(package({'xl/workbook.xml': '<book/>'}), 'fake.docx')
    with pytest.raises(ExtractionError):
        extract_document(b'not a pdf', 'fake.pdf')
    with pytest.raises(ExtractionError):
        extract_document(b'legacy binary', 'old.hwp')


def test_xml_entities_are_not_expanded():
    data = package({'word/document.xml': '<!DOCTYPE x [<!ENTITY bomb "private">]>'
                    '<w:document xmlns:w="urn:w"><w:p><w:t>&bomb;</w:t></w:p></w:document>'})
    with pytest.raises(ExtractionError):
        extract_document(data, 'entity.docx')


def scanned_pdf():
    image = Image.new('RGB', (1200, 400), 'white')
    ImageDraw.Draw(image).text((40, 140), 'VAT 2024 amount 120000', fill='black')
    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawImage(ImageReader(image), 40, 450, width=500, height=167)
    pdf.save()
    return stream.getvalue()


def test_scanned_pdf_uses_ocr_and_keeps_page_label():
    with patch('app.services.document.extractors.shutil.which', return_value='/usr/bin/tesseract'), \
         patch('app.services.document.extractors.subprocess.run') as run:
        run.return_value.returncode = 0
        run.return_value.stdout = '부가가치세 신고 120000원'.encode()
        result = extract_document(scanned_pdf(), 'scan.pdf')
    assert result.extraction_method == 'ocr' and result.ocr_pages == 1
    assert '[페이지 1]' in result.text and '부가가치세' in result.text
    assert run.call_args.args[0][:3] == ['tesseract', 'stdin', 'stdout']


def test_scanned_pdf_without_ocr_engine_fails_closed():
    with patch('app.services.document.extractors.shutil.which', return_value=None):
        with pytest.raises(OCRUnavailable):
            extract_document(scanned_pdf(), 'scan.pdf')
