"""Render a synthetic consultation report for PDF layout QA."""
from pathlib import Path

from app.services.consultation_report_service import build_report


def main():
    destination = Path('output/pdf')
    destination.mkdir(parents=True, exist_ok=True)
    sample = {
        'id': '00000000-0000-0000-0000-000000000001', 'kind': 'income_tax',
        'kind_label': '종합소득세', 'reference_date': '2024-12-31',
        'question': '2024년 귀속 사업소득에 대한 참고 세액과 확인할 서류는 무엇인가요?',
        'facts': {'income': 50_000_000, 'expense': 10_000_000,
                  'personal_deduction_count': 1, 'other_deductions': 0},
        'checklist': [
            {'title': '수입금액 확인 자료', 'status': 'attached', 'filename': 'income.pdf', 'note': ''},
            {'title': '필요경비 확인 자료', 'status': 'pending', 'filename': None, 'note': ''},
        ],
        'calculation': {'calculated_at': '2026-09-26T12:00:00Z', 'result': {
            'final_tax': 4_500_000,
            'basis': {'queried_on': '2024-12-31', 'effective_dates': ['2024-01-01']},
            'steps': [{'label': '총수입금액', 'amount': 50_000_000},
                      {'label': '필요경비', 'amount': 10_000_000}],
            'source_articles': ['소득세법 관련 조문은 원문에서 별도 확인 필요'],
        }},
    }
    output = destination / 'consultation-report-sample.pdf'
    output.write_bytes(build_report(sample))
    try:
        import pymupdf  # Optional local visual-QA dependency, not needed by the service.
    except ImportError:
        print(f'{output}: PDF written; install pymupdf to render PNG previews')
        return
    pdf = pymupdf.open(output)
    for index, page in enumerate(pdf, 1):
        page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(
            destination / f'consultation-report-page-{index}.png')
    print(f'{output}: {len(pdf)} page(s)')


if __name__ == '__main__':
    main()
