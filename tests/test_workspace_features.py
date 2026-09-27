from io import BytesIO
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException

from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from app.services.consultation_report_service import build_report
from app.services.document_review_service import candidates
from app.services import personal_tax_calendar_service as calendar


def test_document_candidates_keep_original_page_and_require_human_choice():
    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
    pdf.setFont('HYSMyeongJo-Medium', 12)
    pdf.drawString(50, 700, '수입 12,345,000원 2025-05-01')
    pdf.showPage()
    pdf.setFont('HYSMyeongJo-Medium', 12)
    pdf.drawString(50, 700, '경비 500,000원')
    pdf.save()
    rows = candidates(stream.getvalue())
    assert any(row['value'] == 12_345_000 and row['page'] == 1 for row in rows)
    assert any(row['type'] == 'date' and row['page'] == 1 for row in rows)
    assert any(row['value'] == 500_000 and row['page'] == 2 for row in rows)


def test_report_contains_saved_calculation_and_source_labels():
    case = {'id': 'case-test', 'kind': 'income_tax', 'kind_label': '종합소득세',
            'reference_date': '2025-12-31', 'question': '세액을 검토해 주세요.',
            'facts': {'income': 50_000_000, 'expense': 0, 'personal_deduction_count': 1,
                      'other_deductions': 0},
            'checklist': [{'title': '수입금액 확인 자료', 'status': 'pending', 'filename': None}],
            'calculation': {'calculated_at': '2026-01-01T00:00:00Z',
                            'result': {'final_tax': 3_000_000,
                                       'steps': [{'label': '결정세액', 'amount': 3_000_000}],
                                       'source_articles': ['소득세법 제55조'],
                                       'basis': {'queried_on': '2025-12-31',
                                                 'effective_dates': ['2024-01-01']}}}}
    data = build_report(case)
    reader = PdfReader(BytesIO(data))
    assert data.startswith(b'%PDF') and len(reader.pages) >= 1
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert '3,000,000' in text
    assert '2025-12-31' in text


@pytest.mark.asyncio
async def test_personal_schedule_only_saves_exact_current_official_event(monkeypatch):
    day = date.today()
    title = '공식 게시 일정'
    uid = str(uuid.uuid4())
    official = AsyncMock(return_value={'events': [{'date': day.isoformat(), 'title': title,
                                                   'note': '공식 비고'}],
                                       'source_url': 'https://www.nts.go.kr/example'})
    fetchrow = AsyncMock(return_value={'id': uuid.uuid4(), 'user_id': uuid.UUID(uid),
                                       'due_date': day, 'title': title, 'note': '공식 비고',
                                       'source_url': 'https://www.nts.go.kr/example',
                                       'status': 'watching', 'created_at': datetime.now(timezone.utc),
                                       'updated_at': datetime.now(timezone.utc)})
    monkeypatch.setattr(calendar, 'get_official_month', official)
    monkeypatch.setattr(calendar, 'get_pool', AsyncMock(return_value=SimpleNamespace(fetchrow=fetchrow)))
    with pytest.raises(HTTPException) as error:
        await calendar.watch_event(uid, day, '게시되지 않은 임의 일정')
    assert error.value.status_code == 422
    fetchrow.assert_not_awaited()
    row = await calendar.watch_event(uid, day, title)
    assert row['title'] == title and row['due_date'] == day.isoformat()
    assert official.await_args.kwargs['refresh'] is True
