"""Bounded text extraction for user-uploaded office documents and scanned PDFs."""
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePath
import posixpath
import re
import shutil
import subprocess
import zipfile

import pypdfium2 as pdfium
from defusedxml import ElementTree as SafeET


SUPPORTED_EXTENSIONS = frozenset({'.pdf', '.docx', '.hwpx', '.pptx', '.html', '.htm'})
MAX_TEXT_CHARS = 500_000
MAX_PDF_PAGES = 200
MAX_OCR_PAGES = 20
MAX_ZIP_MEMBERS = 500
MAX_ZIP_BYTES = 80 * 1024 * 1024
MAX_XML_BYTES = 12 * 1024 * 1024


class ExtractionError(ValueError):
    pass


class OCRUnavailable(ExtractionError):
    pass


@dataclass(frozen=True)
class DocumentBlock:
    text: str
    kind: str = 'paragraph'
    page: int | None = None
    slide: int | None = None
    section: int | None = None
    heading: str = ''
    table: int | None = None
    row: int | None = None
    ocr: bool = False


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    format: str
    extraction_method: str
    ocr_pages: int = 0
    pages: int | None = None
    blocks: tuple[DocumentBlock, ...] = ()


def extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def _bounded(text: str) -> str:
    text = text.strip()
    if not text:
        raise ExtractionError('문서에서 검색할 텍스트를 찾지 못했습니다.')
    if len(text) > MAX_TEXT_CHARS:
        raise ExtractionError('추출된 텍스트가 처리 한도를 초과합니다. 문서를 나누어 업로드해 주세요.')
    return text


def _pdf(data: bytes) -> ExtractedDocument:
    if not data.startswith(b'%PDF-'):
        raise ExtractionError('PDF 형식과 파일 내용이 일치하지 않습니다.')
    try:
        document = pdfium.PdfDocument(data)
    except Exception as exc:
        raise ExtractionError('PDF를 열 수 없습니다. 손상되었거나 암호화된 파일인지 확인해 주세요.') from exc
    try:
        if len(document) > MAX_PDF_PAGES:
            raise ExtractionError(f'PDF는 최대 {MAX_PDF_PAGES}페이지까지 업로드할 수 있습니다.')
        pieces, blocks, ocr_pages = [], [], 0
        for index in range(1, len(document) + 1):
            page = document[index - 1]
            text_page = page.get_textpage()
            text = (text_page.get_text_bounded() or '').strip()
            text_page.close()
            used_ocr = len(text) < 20
            if used_ocr:
                ocr_pages += 1
                if ocr_pages > MAX_OCR_PAGES:
                    raise ExtractionError(f'OCR이 필요한 페이지는 최대 {MAX_OCR_PAGES}쪽까지 처리합니다.')
                width, height = page.get_size()
                if width * height > 2_000_000:
                    raise ExtractionError(f'{index}쪽의 이미지 크기가 OCR 처리 한도를 초과합니다.')
                if not shutil.which('tesseract'):
                    raise OCRUnavailable('OCR 엔진이 설치되지 않아 스캔 PDF를 읽을 수 없습니다.')
                bitmap = page.render(scale=200 / 72, grayscale=True)
                image = BytesIO()
                bitmap.to_pil().save(image, format='PNG')
                bitmap.close()
                try:
                    result = subprocess.run(
                        ['tesseract', 'stdin', 'stdout', '-l', 'kor+eng', '--psm', '3'],
                        input=image.getvalue(), capture_output=True, timeout=25, check=False)
                except subprocess.TimeoutExpired as exc:
                    raise ExtractionError(f'{index}쪽 OCR 시간이 초과되었습니다.') from exc
                if result.returncode:
                    raise OCRUnavailable('한국어 OCR 언어 데이터가 없거나 OCR 실행에 실패했습니다.')
                text = result.stdout.decode('utf-8', errors='replace').strip()
            if text:
                pieces.append(f'[페이지 {index}]\n{text}')
                # PDF text extraction does not reliably identify table cells or headings.
                for paragraph in re.split(r'\n\s*\n', text):
                    if paragraph.strip():
                        blocks.append(DocumentBlock(paragraph.strip(), page=index, ocr=used_ocr))
            page.close()
        return ExtractedDocument(_bounded('\n\n'.join(pieces)), 'pdf',
                                 'ocr' if ocr_pages else 'text', ocr_pages, len(document), tuple(blocks))
    finally:
        document.close()


def _package(data: bytes, expected: str) -> zipfile.ZipFile:
    try:
        package = zipfile.ZipFile(BytesIO(data))
        members = package.infolist()
        if len(members) > MAX_ZIP_MEMBERS or sum(item.file_size for item in members) > MAX_ZIP_BYTES:
            raise ExtractionError('압축 문서의 해제 크기 또는 파일 수가 처리 한도를 초과합니다.')
        if expected not in package.namelist():
            raise ExtractionError('확장자와 실제 문서 형식이 일치하지 않습니다.')
        if any(item.flag_bits & 1 for item in members):
            raise ExtractionError('암호화된 압축 문서는 지원하지 않습니다.')
        return package
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ExtractionError('손상된 압축 문서이거나 지원하지 않는 형식입니다.') from exc


def _xml(package: zipfile.ZipFile, name: str):
    info = package.getinfo(name)
    if info.file_size > MAX_XML_BYTES:
        raise ExtractionError('문서의 XML 본문이 처리 한도를 초과합니다.')
    try:
        return SafeET.fromstring(package.read(name))
    except (ValueError, SyntaxError) as exc:
        raise ExtractionError('문서의 XML 본문을 읽을 수 없습니다.') from exc


def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def _paragraphs(root, paragraph_tags: set[str], text_tags: set[str]) -> list[str]:
    lines = []
    for element in root.iter():
        if _local(element.tag) in paragraph_tags:
            parts = [node.text for node in element.iter()
                     if _local(node.tag) in text_tags and node.text]
            line = ''.join(parts).strip()
            if line:
                lines.append(line)
    return lines


def _element_text(element, text_tags: set[str] = {'t'}) -> str:
    return ''.join(node.text for node in element.iter()
                   if _local(node.tag) in text_tags and node.text).strip()


def _office_blocks(root, *, section: int | None = None) -> list[DocumentBlock]:
    """Read paragraphs and table rows in source order, without flattening cells."""
    body = next((node for node in root.iter() if _local(node.tag) == 'body'), root)
    blocks: list[DocumentBlock] = []
    current_heading = ''
    table_no = 0

    def visit(node) -> None:
        nonlocal current_heading, table_no
        tag = _local(node.tag)
        if tag == 'tbl':
            table_no += 1
            rows = [item for item in node.iter() if _local(item.tag) in {'tr'}]
            for row_no, row in enumerate(rows, 1):
                cells = [_element_text(cell) for cell in row if _local(cell.tag) in {'tc'}]
                if any(cells):
                    explicit_header = any(_local(item.tag) == 'tblHeader' for item in row.iter())
                    blocks.append(DocumentBlock(' | '.join(cells),
                                                'table_header' if explicit_header else 'table_row', section=section,
                                                heading=current_heading, table=table_no, row=row_no))
            return
        if tag == 'p':
            value = _element_text(node)
            if value:
                heading_style = any(_local(item.tag) == 'pStyle' and
                                    re.match(r'(?i)heading|title|제목|표제',
                                             next((value for key, value in item.attrib.items()
                                                   if _local(key) == 'val'), ''))
                                    for item in node.iter())
                if heading_style:
                    current_heading = value
                blocks.append(DocumentBlock(value, 'heading' if heading_style else 'paragraph',
                                            section=section, heading=current_heading))
            return
        for child in node:
            visit(child)

    visit(body)
    return blocks


def _docx(data: bytes) -> ExtractedDocument:
    with _package(data, 'word/document.xml') as package:
        root = _xml(package, 'word/document.xml')
        blocks = _office_blocks(root)
        text = '\n'.join(block.text for block in blocks)
    return ExtractedDocument(_bounded(text), 'docx', 'text', blocks=tuple(blocks))


def _pptx(data: bytes) -> ExtractedDocument:
    with _package(data, 'ppt/presentation.xml') as package:
        names = set(package.namelist())
        slides = sorted((name for name in names
                         if re.fullmatch(r'ppt/slides/slide\d+\.xml', name)),
                        key=lambda name: int(re.search(r'slide(\d+)', name).group(1)))
        relations = 'ppt/_rels/presentation.xml.rels'
        if relations in names:
            targets = {}
            for relation in _xml(package, relations).iter():
                if _local(relation.tag) == 'Relationship':
                    target = relation.get('Target', '')
                    path = posixpath.normpath(target.lstrip('/') if target.startswith('/')
                                            else posixpath.join('ppt', target))
                    if path in names and re.fullmatch(r'ppt/slides/slide\d+\.xml', path):
                        targets[relation.get('Id')] = path
            ordered = []
            for item in _xml(package, 'ppt/presentation.xml').iter():
                if _local(item.tag) == 'sldId':
                    relationship = next((value for key, value in item.attrib.items()
                                         if key.rsplit('}', 1)[-1] == 'id' and value in targets), None)
                    if relationship:
                        ordered.append(targets[relationship])
            if ordered:
                slides = list(dict.fromkeys(ordered))
        if not slides:
            raise ExtractionError('PPTX 슬라이드 본문을 찾지 못했습니다.')
        lines, blocks = [], []
        for index, name in enumerate(slides, 1):
            paragraphs = _paragraphs(_xml(package, name), {'p'}, {'t'})
            content = '\n'.join(paragraphs)
            if content:
                lines.append(f'[슬라이드 {index}]\n{content}')
                blocks.extend(DocumentBlock(value, slide=index) for value in paragraphs)
    return ExtractedDocument(_bounded('\n\n'.join(lines)), 'pptx', 'text',
                             pages=len(slides), blocks=tuple(blocks))


def _hwpx(data: bytes) -> ExtractedDocument:
    with _package(data, 'Contents/section0.xml') as package:
        sections = sorted((name for name in package.namelist()
                           if re.fullmatch(r'Contents/section\d+\.xml', name)),
                          key=lambda name: int(re.search(r'section(\d+)', name).group(1)))
        lines, blocks = [], []
        for index, name in enumerate(sections, 1):
            section_blocks = _office_blocks(_xml(package, name), section=index)
            content = '\n'.join(block.text for block in section_blocks)
            if content:
                lines.append(f'[구역 {index}]\n{content}')
                blocks.extend(section_blocks)
    return ExtractedDocument(_bounded('\n\n'.join(lines)), 'hwpx', 'text', blocks=tuple(blocks))


class _VisibleHTML(HTMLParser):
    BLOCKS = {'p', 'div', 'br', 'li', 'tr', 'td', 'th', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    HIDDEN = {'script', 'style', 'noscript', 'svg', 'template'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        elif not self.hidden and tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self.HIDDEN and self.hidden:
            self.hidden -= 1
        elif not self.hidden and tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class _StructuredHTML(HTMLParser):
    HIDDEN = _VisibleHTML.HIDDEN
    HEADINGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.current = []
        self.kind = 'paragraph'
        self.heading = ''
        self.table = 0
        self.row = 0
        self.blocks: list[DocumentBlock] = []

    def _flush(self):
        value = ''.join(self.current).strip(' |\n\t')
        if value:
            if self.kind == 'heading':
                self.heading = value
            is_table = self.kind in {'table_row', 'table_header'}
            self.blocks.append(DocumentBlock(value, self.kind, heading=self.heading,
                                             table=self.table or None if is_table else None,
                                             row=self.row or None if is_table else None))
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        if self.hidden:
            return
        if tag == 'table':
            self._flush()
            self.table += 1
            self.row = 0
        elif tag == 'tr':
            self._flush()
            self.row += 1
            self.kind = 'table_row'
        elif tag in {'td', 'th'}:
            if tag == 'th':
                self.kind = 'table_header'
            if self.current and self.current[-1] != ' | ':
                self.current.append(' | ')
        elif tag in self.HEADINGS | {'p', 'li', 'br'}:
            self._flush()
            self.kind = 'heading' if tag in self.HEADINGS else 'paragraph'

    def handle_endtag(self, tag):
        if tag in self.HIDDEN:
            self.hidden = max(0, self.hidden - 1)
            return
        if self.hidden:
            return
        if tag in self.HEADINGS | {'p', 'li', 'tr', 'table'}:
            self._flush()
            self.kind = 'paragraph'

    def handle_data(self, data):
        if not self.hidden:
            self.current.append(data)


def _html(data: bytes, suffix: str) -> ExtractedDocument:
    if b'\x00' in data:
        raise ExtractionError('HTML 형식과 파일 내용이 일치하지 않습니다.')
    try:
        decoded = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            decoded = data.decode('cp949')
        except UnicodeDecodeError as exc:
            raise ExtractionError('HTML 문자 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949로 저장해 주세요.') from exc
    parser = _VisibleHTML()
    parser.feed(decoded)
    text = '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
    structured = _StructuredHTML()
    structured.feed(decoded)
    structured._flush()
    return ExtractedDocument(_bounded(text), suffix[1:], 'text', blocks=tuple(structured.blocks))


def extract_document(data: bytes, filename: str) -> ExtractedDocument:
    suffix = extension(filename)
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ExtractionError('PDF, DOCX, HWPX, PPTX, HTML 파일만 업로드할 수 있습니다.')
    try:
        if suffix == '.pdf':
            return _pdf(data)
        if suffix == '.docx':
            return _docx(data)
        if suffix == '.hwpx':
            return _hwpx(data)
        if suffix == '.pptx':
            return _pptx(data)
        return _html(data, suffix)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError('문서를 읽을 수 없습니다. 손상되었거나 지원하지 않는 내용인지 확인해 주세요.') from exc
