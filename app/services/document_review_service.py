"""Read-only source candidates and user-confirmed fields for stored PDFs."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re
import uuid

from fastapi import HTTPException
from pypdf import PdfReader

from app.database import get_pool
from app.services.consultation_catalog import CASE_KINDS
from app.services.document.extractors import extension

AMOUNT_KEYS = {key for flow in CASE_KINDS.values()
               for key, _, kind, _ in flow['questions'] if kind == 'amount'}
# A decimal point must be part of the match; never turn "1.5억원" into "5억원".
AMOUNT_RE = re.compile(
    r'(?<![\d.,])((?:\d{1,3}(?:,\d{3})+|\d{1,12})(?:\.\d+)?)\s*'
    r'(억\s*원|만\s*원|원)(?![\d가-힣])'
)
DATE_RE = re.compile(r'(?<!\d)(?:19|20)\d{2}[.\-/]\s*\d{1,2}[.\-/]\s*\d{1,2}(?!\d)')


def _user(user_id):
    try:
        return uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        raise HTTPException(401, '로그인이 필요합니다.') from None


async def file_row(user_id, filename):
    pool = await get_pool()
    row = await pool.fetchrow('''SELECT content,sha256,uploaded_at FROM user_document_files
        WHERE user_id=$1 AND filename=$2''', _user(user_id), filename)
    if not row:
        raise HTTPException(404, '원본 PDF가 없습니다. 기존 문서는 다시 업로드해 주세요.')
    return row


def candidates(content):
    reader = PdfReader(BytesIO(bytes(content)))
    if len(reader.pages) > 100:
        raise HTTPException(422, '검토 화면은 100페이지 이하 PDF를 지원합니다.')
    found = []
    for page_no, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ''
        for match in AMOUNT_RE.finditer(text):
            unit = match[2].replace(' ', '')
            factor = 100_000_000 if unit.startswith('억') else 10_000 if unit.startswith('만') else 1
            exact = Decimal(match[1].replace(',', '')) * factor
            if exact != exact.to_integral_value() or exact > 10**15:
                continue
            value = int(exact)
            found.append({'type': 'amount', 'value': value, 'display': match[0].strip(),
                          'page': page_no, 'context': ' '.join(text[max(0, match.start()-35):match.end()+35].split())})
        for match in DATE_RE.finditer(text):
            raw = match[0]
            try:
                date_value = datetime.strptime(re.sub(r'\s+', '', raw).replace('.', '-').replace('/', '-'), '%Y-%m-%d').date()
            except ValueError:
                continue
            found.append({'type': 'date', 'value': date_value.isoformat(), 'display': raw,
                          'page': page_no, 'context': ' '.join(text[max(0, match.start()-35):match.end()+35].split())})
        if len(found) >= 150:
            break
    return found[:150]


async def review(user_id, filename):
    if extension(filename) != '.pdf':
        raise HTTPException(422, '원본 페이지별 금액·날짜 검토는 PDF에서만 지원합니다.')
    row = await file_row(user_id, filename)
    pool = await get_pool()
    saved = await pool.fetchrow('''SELECT fields,document_sha256,reviewed_at FROM user_document_reviews
        WHERE user_id=$1 AND filename=$2''', _user(user_id), filename)
    valid = saved and saved['document_sha256'] == row['sha256']
    return {'filename': filename, 'sha256': row['sha256'],
            'uploaded_at': row['uploaded_at'].isoformat(), 'candidates': candidates(row['content']),
            'fields': {key: value for key, value in saved['fields'].items() if key != '_dates'} if valid else {},
            'dates': saved['fields'].get('_dates', []) if valid else [],
            'reviewed_at': saved['reviewed_at'].isoformat() if valid else None}


async def save_review(user_id, filename, fields, dates=None, *, expected_sha256: str,
                      expected_reviewed_at: str | None = None):
    if extension(filename) != '.pdf':
        raise HTTPException(422, '원본 페이지별 금액·날짜 검토는 PDF에서만 지원합니다.')
    if not set(fields) <= AMOUNT_KEYS:
        raise HTTPException(422, '지원하지 않는 계산 항목입니다.')
    dates = dates or []
    pool = await get_pool()
    uid = _user(user_id)
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow('''SELECT sha256,content FROM user_document_files
                WHERE user_id=$1 AND filename=$2 FOR UPDATE''', uid, filename)
            if not row:
                raise HTTPException(404, '원본 PDF를 찾을 수 없습니다.')
            if row['sha256'] != expected_sha256:
                raise HTTPException(409, '문서가 교체되었습니다. 새 원본을 확인한 뒤 다시 저장하세요.')
            current = await conn.fetchrow('''SELECT reviewed_at FROM user_document_reviews
                WHERE user_id=$1 AND filename=$2 FOR UPDATE''', uid, filename)
            current_revision = current['reviewed_at'].isoformat() if current else None
            if current_revision != expected_reviewed_at:
                raise HTTPException(409, '다른 화면에서 검토값이 변경되었습니다. 다시 조회해 주세요.')
            page_count = len(PdfReader(BytesIO(bytes(row['content']))).pages)
            if any(field['page'] > page_count for field in [*fields.values(), *dates]):
                raise HTTPException(422, '원본에 없는 페이지 번호입니다.')
            stored = {**fields, '_dates': dates}
            await conn.execute('''INSERT INTO user_document_reviews
                (user_id,filename,document_sha256,fields) VALUES($1,$2,$3,$4)
                ON CONFLICT(user_id,filename) DO UPDATE SET document_sha256=EXCLUDED.document_sha256,
                    fields=EXCLUDED.fields,reviewed_at=now()''', uid, filename, row['sha256'], stored)
    return await review(user_id, filename)
