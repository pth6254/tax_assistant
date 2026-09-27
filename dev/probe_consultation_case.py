"""Exercise the deployed income-tax case API using disposable, isolated data."""
import uuid

import httpx
import psycopg

from app.core.security import create_access_token
from config import DATABASE_URL


BASE = 'http://localhost:3001'


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
                scenarios = {
                    'capital_gains': {'transfer_price': 500000000, 'acquisition_price': 300000000,
                                      'expenses': 10000000, 'holding_years': 5,
                                      'asset_type': '부동산', 'is_one_home': False},
                    'inheritance': {'estate_value': 1000000000, 'debts': 100000000,
                                    'spouse_inheritance': 200000000, 'children_count': 2},
                    'gift': {'gift_amount': 100000000, 'relation': '직계존비속',
                             'is_minor': False, 'prior_gifts_10y': 0},
                    'vat': {'sales': 100000000, 'purchases': 30000000,
                            'exempt_sales': 0, 'is_simplified': False, 'business_type': '소매업'},
                    'penalty_tax': {'unpaid_tax': 1000000, 'penalty_type': '무신고',
                                    'is_negligent': False, 'days_late': 0},
                }
                for kind, answers in scenarios.items():
                    created = expect(api.post('/api/consultation-cases', json={
                        'kind': kind, 'title': f'검증용 {kind}', 'question': '계산과 근거를 확인해 주세요.',
                        'tax_year': 2024, 'reference_date': '2024-12-31'}), 201)
                    other_kind_field = 'income' if kind != 'income_tax' else 'gift_amount'
                    expect(api.patch(f"/api/consultation-cases/{created['id']}/facts",
                                     json={other_kind_field: 1}), 422)
                    updated = expect(api.patch(f"/api/consultation-cases/{created['id']}/facts",
                                                   json=answers), 200)
                    assert updated['next_question'] is None, kind
                    calculated = expect(api.post(f"/api/consultation-cases/{created['id']}/calculate"), 200)
                    assert isinstance(calculated['calculation']['result']['final_tax'], int), kind
                    assert calculated['calculation']['result']['basis']['queried_on'] == '2024-12-31', kind
                    expect(api.delete(f"/api/consultation-cases/{created['id']}"), 200)
                assert not expect(api.get('/api/consultation-cases'), 200)
            print('six consultation case kinds: ownership, questions, field boundaries, '
                  'calculation date, document state and cleanup passed')
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
