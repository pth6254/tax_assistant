"""Exercise deployed workspace APIs with disposable user-owned data."""
from hashlib import sha256
from io import BytesIO
import uuid

import httpx
import psycopg
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.core.security import create_access_token
from config import DATABASE_URL


BASE = 'http://localhost:3002'


def expect(response, status):
    if response.status_code != status:
        raise AssertionError(f'{response.request.method} {response.request.url.path}: '
                             f'expected {status}, got {response.status_code}: {response.text[:500]}')
    return response.json()


def sample_pdf():
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(50, 750, 'Income 50,000,000 KRW on 2024-12-31')
    pdf.save()
    return buffer.getvalue()


def main():
    email = f'workspace-probe-{uuid.uuid4().hex}@example.invalid'
    filename = f'workspace-probe-{uuid.uuid4().hex}.pdf'
    raw = sample_pdf()
    with psycopg.connect(DATABASE_URL) as database:
        with database.cursor() as cursor:
            cursor.execute('INSERT INTO users(email,password) VALUES(%s,%s) RETURNING id',
                           (email, 'probe-account-no-login'))
            user_id = cursor.fetchone()[0]
        database.commit()
        try:
            token = create_access_token(str(user_id), email)
            with httpx.Client(base_url=BASE, cookies={'access_token': token},
                              timeout=30, trust_env=False) as api:
                created = expect(api.post('/api/consultation-cases', json={
                    'title': 'Workspace integration probe', 'question': 'Calculate',
                    'tax_year': 2024, 'reference_date': '2024-12-31'}), 201)
                case_id = created['id']
                expect(api.patch(f'/api/consultation-cases/{case_id}/facts', json={
                    'income': 50_000_000, 'expense': 10_000_000,
                    'personal_deduction_count': 1, 'other_deductions': 0}), 200)
                expect(api.post(f'/api/consultation-cases/{case_id}/calculate'), 200)
                first = expect(api.post(f'/api/consultation-cases/{case_id}/scenarios',
                                        json={'name': 'base'}), 201)
                expect(api.patch(f'/api/consultation-cases/{case_id}/facts',
                                 json={'expense': 15_000_000}), 200)
                expect(api.post(f'/api/consultation-cases/{case_id}/calculate'), 200)
                second = expect(api.post(f'/api/consultation-cases/{case_id}/scenarios',
                                         json={'name': 'higher expenses'}), 201)
                scenarios = expect(api.get(f'/api/consultation-cases/{case_id}/scenarios'), 200)
                assert len(scenarios) == 2 and first['result']['final_tax'] != second['result']['final_tax']

                report = api.get(f'/api/consultation-cases/{case_id}/report.pdf')
                assert report.status_code == 200 and report.content.startswith(b'%PDF-')
                assert len(PdfReader(BytesIO(report.content)).pages) >= 1
                with database.cursor() as cursor:
                    cursor.execute('''INSERT INTO documents(content,metadata,user_id)
                        VALUES(%s,%s::jsonb,%s)''',
                        ('Income 50,000,000 KRW', '{"source":"' + filename + '"}', user_id))
                    cursor.execute('''INSERT INTO user_document_files(user_id,filename,content,sha256)
                        VALUES(%s,%s,%s,%s)''', (user_id, filename, raw, sha256(raw).hexdigest()))
                database.commit()
                docs = expect(api.get('/api/documents'), 200)
                assert any(doc['filename'] == filename and doc['original_available'] for doc in docs)
                assert api.get(f'/api/documents/{filename}/file').content == raw
                review = expect(api.get(f'/api/documents/{filename}/review'), 200)
                assert review['sha256'] == sha256(raw).hexdigest()
                saved_review = expect(api.put(f'/api/documents/{filename}/review', json={'fields': {
                    'income': {'value': 50_000_000, 'page': 1, 'note': 'verified original'}},
                    'dates': [{'value': '2024-12-31', 'page': 1, 'note': 'verified original'}]}), 200)
                assert saved_review['dates'][0]['value'] == '2024-12-31'
                expect(api.put(f'/api/consultation-cases/{case_id}/documents/income_proof',
                               json={'status': 'attached', 'filename': filename}), 200)
                applied = expect(api.post(f'/api/consultation-cases/{case_id}/apply-reviewed-field',
                                          json={'filename': filename, 'field_key': 'income'}), 200)
                assert applied['facts']['income'] == 50_000_000 and applied['calculation'] is None
                with database.cursor() as cursor:
                    cursor.execute('''UPDATE documents SET created_at=created_at+interval '1 second'
                        WHERE user_id=%s AND metadata->>'source'=%s''', (user_id, filename))
                database.commit()
                expect(api.post(f'/api/consultation-cases/{case_id}/apply-reviewed-field',
                                json={'filename': filename, 'field_key': 'income'}), 409)
                foreign = create_access_token(str(uuid.uuid4()), 'foreign@example.invalid')
                with httpx.Client(base_url=BASE, cookies={'access_token': foreign},
                                  timeout=15, trust_env=False) as other:
                    expect(other.get(f'/api/documents/{filename}/review'), 404)
                    expect(other.get(f'/api/consultation-cases/{case_id}/scenarios'), 404)

                with database.cursor() as cursor:
                    cursor.execute('''INSERT INTO personal_tax_events(user_id,due_date,title,source_url)
                        VALUES(%s,current_date,'Probe deadline','https://example.invalid') RETURNING id''',
                        (user_id,))
                    event_id = cursor.fetchone()[0]
                database.commit()
                upcoming = expect(api.get('/api/tax-schedule/personal/upcoming'), 200)
                assert any(item['id'] == str(event_id) for item in upcoming)
                updated = expect(api.patch(f'/api/tax-schedule/personal/{event_id}',
                                           json={'status': 'preparing'}), 200)
                assert updated['status'] == 'preparing'
                expect(api.delete(f'/api/tax-schedule/personal/{event_id}'), 200)

                laws = expect(api.get('/api/law-explorer/laws'), 200)
                assert laws and 'law_id' in laws[0]
                with database.cursor() as cursor:
                    cursor.execute('''SELECT v.law_id, max(v.effective_date)
                        FROM law_history.versions v
                        WHERE v.fetch_status='complete' AND EXISTS (
                            SELECT 1 FROM law_history.snapshots s WHERE s.version_id=v.id)
                        GROUP BY v.law_id HAVING count(DISTINCT v.effective_date) >= 2
                        ORDER BY v.law_id LIMIT 1''')
                    law_id, comparison_day = cursor.fetchone()
                params = {'law_id': law_id, 'as_of': comparison_day.isoformat(),
                          'article_no': '제1조'}
                resolved = expect(api.get('/api/law-explorer/resolve', params={
                    'law_id': law_id, 'as_of': comparison_day.isoformat()}), 200)
                assert resolved['law_id'] == law_id
                article = expect(api.get('/api/law-explorer/article', params=params), 200)
                assert article['article']['content'] and article['version']['id'] == resolved['id']
                compared = expect(api.get('/api/law-explorer/compare', params={
                    'law_id': law_id, 'left_date': comparison_day.isoformat(),
                    'right_date': comparison_day.isoformat(), 'article_no': '제1조'}), 200)
                assert compared['diff'] == []
                expect(api.delete(f'/api/consultation-cases/{case_id}/scenarios/{first["id"]}'), 200)
                print('workspace probe: PDF, scenarios, document review, ownership, calendar, law article passed')
        finally:
            with database.cursor() as cursor:
                cursor.execute('DELETE FROM users WHERE id=%s', (user_id,))
            database.commit()


if __name__ == '__main__':
    main()
