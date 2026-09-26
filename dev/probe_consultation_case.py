"""Exercise the deployed income-tax case API using disposable, isolated data."""
import uuid

import httpx
import psycopg

from app.core.security import create_access_token
from config import DATABASE_URL


BASE = 'http://localhost:3002'


def expect(response, status):
    if response.status_code != status:
        raise AssertionError(f'{response.request.method} {response.request.url.path}: '
                             f'expected {status}, got {response.status_code} '
                             f'({response.text[:400]})')
    return response.json()


def main():
    email = f'case-probe-{uuid.uuid4().hex}@example.invalid'
    filename = f'case-probe-{uuid.uuid4().hex}.pdf'
    with psycopg.connect(DATABASE_URL) as database:
        with database.cursor() as cursor:
            cursor.execute('INSERT INTO users (email,password) VALUES (%s,%s) RETURNING id',
                           (email, 'probe-account-no-login'))
            user_id = cursor.fetchone()[0]
        database.commit()
        try:
            token = create_access_token(str(user_id), email)
            with httpx.Client(base_url=BASE, cookies={'access_token': token},
                              timeout=20, trust_env=False) as api:
                created = expect(api.post('/api/consultation-cases', json={
                    'title': '검증용 종합소득세 상담', 'question': '소득세 계산과 근거를 확인해 주세요.',
                    'tax_year': 2024}), 201)
                case_id = created['id']
                assert len(created['questions']) == 4 and created['conversation_id']
                assert created['next_question']
                foreign_token = create_access_token(str(uuid.uuid4()), 'other@example.invalid')
                with httpx.Client(base_url=BASE, cookies={'access_token': foreign_token},
                                  timeout=20, trust_env=False) as other:
                    expect(other.get(f'/api/consultation-cases/{case_id}'), 404)
                expect(api.post(f'/api/consultation-cases/{case_id}/calculate'), 422)
                updated = expect(api.patch(f'/api/consultation-cases/{case_id}/facts', json={
                    'income': 50000000, 'expense': 10000000,
                    'personal_deduction_count': 1, 'other_deductions': 0}), 200)
                assert updated['next_question'] is None
                with database.cursor() as cursor:
                    cursor.execute('''INSERT INTO documents (content,metadata,user_id)
                        VALUES (%s,%s::jsonb,%s)''',
                        ('검증용 수입 확인 텍스트', '{"source":"' + filename + '","category":"기타"}', user_id))
                database.commit()
                linked = expect(api.put(f'/api/consultation-cases/{case_id}/documents/income_proof',
                                        json={'status': 'attached', 'filename': filename}), 200)
                assert linked['checklist'][0]['status'] == 'attached'
                calculated = expect(api.post(f'/api/consultation-cases/{case_id}/calculate'), 200)
                result = calculated['calculation']['result']
                assert result['basis']['queried_on'] == '2024-12-31'
                assert result['basis']['effective_dates']
                assert isinstance(result['final_tax'], int)
                with database.cursor() as cursor:
                    cursor.execute("DELETE FROM documents WHERE user_id=%s AND metadata->>'source'=%s",
                                   (user_id, filename))
                database.commit()
                refreshed = expect(api.get(f'/api/consultation-cases/{case_id}'), 200)
                assert refreshed['checklist'][0]['status'] == 'needs_recheck'
                expect(api.delete(f'/api/consultation-cases/{case_id}'), 200)
                assert not expect(api.get('/api/consultation-cases'), 200)
            print('consultation case API: create, ownership, clarification, document, '
                  'calculation basis, stale document and deletion passed')
        finally:
            with database.cursor() as cursor:
                cursor.execute('DELETE FROM consultation_cases WHERE user_id=%s', (user_id,))
                cursor.execute('DELETE FROM documents WHERE user_id=%s', (user_id,))
                cursor.execute('DELETE FROM chat_logs WHERE conversation_id IN '
                               '(SELECT id FROM conversations WHERE user_id=%s)', (user_id,))
                cursor.execute('DELETE FROM conversations WHERE user_id=%s', (user_id,))
                cursor.execute('DELETE FROM users WHERE id=%s', (user_id,))
            database.commit()


if __name__ == '__main__':
    main()
