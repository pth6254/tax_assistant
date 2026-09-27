"""Generate a user-owned consultation summary as an on-demand PDF."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.consultation_catalog import case_kind

pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
FONT = 'HYSMyeongJo-Medium'
BODY = ParagraphStyle('body', fontName=FONT, fontSize=9, leading=15, wordWrap='CJK', spaceAfter=6)
TITLE = ParagraphStyle('title', parent=BODY, fontSize=18, leading=25, alignment=TA_CENTER, spaceAfter=16)
SECTION = ParagraphStyle('section', parent=BODY, fontSize=12, leading=18, textColor=colors.HexColor('#173a5e'),
                         spaceBefore=14, spaceAfter=8)
SMALL = ParagraphStyle('small', parent=BODY, fontSize=8, leading=13, textColor=colors.HexColor('#52606d'))


def paragraph(value, style=BODY):
    return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)


def format_value(value, field_type):
    if value is None:
        return '미입력'
    if field_type == 'amount':
        return f'{value:,}원'
    if field_type == 'boolean':
        return '예' if value else '아니요'
    return str(value)


def build_report(case):
    """Only serializes saved case data; legal conclusions are not generated here."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=19*mm, leftMargin=19*mm,
                            topMargin=22*mm, bottomMargin=20*mm, title='세무 상담 참고 보고서')
    story = [paragraph('세무 상담 참고 보고서', TITLE),
             paragraph(f"{case['kind_label']}  |  조회 기준일 {case['reference_date']}  |  상담 {case['id']}", SMALL),
             HRFlowable(width='100%', thickness=1, color=colors.HexColor('#cad7e2')),
             paragraph('상담 질문', SECTION), paragraph(case['question'])]
    facts = case.get('facts') or {}
    story.append(paragraph('확인한 입력 조건', SECTION))
    table_rows = [[paragraph('항목'), paragraph('입력값')]]
    for key, question, field_type, _ in case_kind(case['kind'])['questions']:
        table_rows.append([paragraph(question), paragraph(format_value(facts.get(key), field_type))])
    table = Table(table_rows, colWidths=[110*mm, 62*mm], repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f0f7')),
                              ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7fafc')]),
                              ('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7)]))
    story.append(table)
    story.append(paragraph('서류 확인 상태', SECTION))
    status_labels = {'attached':'문서 연결', 'needs_recheck':'재확인 필요',
                     'not_available':'자료 없음', 'pending':'확인 전'}
    for item in case['checklist']:
        story.append(paragraph(f"{item['title']}: {status_labels.get(item['status'], item['status'])}"
                               + (f" ({item['filename']})" if item.get('filename') else '')
                               + (f" - {item['note']}" if item.get('note') else '')))
    calc = case.get('calculation')
    if calc:
        result = calc['result']
        story.extend([paragraph('참고 계산 결과', SECTION),
                      paragraph(f"결과: {result['final_tax']:,}원  |  계산 시각: {calc['calculated_at']}"),
                      paragraph(f"DB 조회 기준일: {(result.get('basis') or {}).get('queried_on', '정보 없음')}"),
                      paragraph('사용한 DB 자료 시행일: ' + ', '.join((result.get('basis') or {}).get('effective_dates') or ['정보 없음']))])
        for step in result.get('steps', []):
            story.append(paragraph(f"{step['label']}: {step['amount']:,}원"))
        story.append(paragraph('계산기에 표시된 근거', SECTION))
        for source in result.get('source_articles', []):
            story.append(paragraph(source))
    else:
        story.extend([paragraph('참고 계산 결과', SECTION), paragraph('저장된 계산 결과가 없습니다.')])
    story.extend([paragraph('추가 확인이 필요한 사항', SECTION),
                  paragraph('서류의 진위, 공제 자격, 법령의 실제 적용 시점과 경과규정은 별도로 확인해야 합니다.', SMALL),
                  paragraph('이 보고서는 저장된 상담 입력과 계산 결과의 기록이며 신고서 또는 세액 확정서가 아닙니다.', SMALL)])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor('#6b7785'))
        canvas.drawString(19*mm, 12*mm, '세무 AI 어시스턴트 | 사용자 확인용 참고 자료')
        canvas.drawRightString(191*mm, 12*mm, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
