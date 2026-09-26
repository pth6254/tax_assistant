"""User-owned, deterministic income-tax consultation workflow."""
import asyncio
from datetime import date, datetime, timezone
import uuid

from fastapi import HTTPException

from app.database import get_pool
from app.services.calculator.income_tax import calculate as calculate_income_tax


FACT_QUESTIONS = (
    ('income', '해당 귀속연도의 총수입금액은 얼마인가요?', '원'),
    ('expense', '필요경비는 얼마인가요? 없다면 0원을 입력해 주세요.', '원'),
    ('personal_deduction_count', '기본공제 대상 인원은 본인을 포함해 몇 명인가요?', '명'),
    ('other_deductions', '기타 소득공제 합계는 얼마인가요? 없다면 0원을 입력해 주세요.', '원'),
)
DOCUMENT_ITEMS = (
    ('income_proof', '수입금액 확인 자료', '수입금액을 확인할 수 있는 자료를 연결해 주세요.'),
    ('expense_proof', '필요경비 확인 자료', '입력한 필요경비를 확인할 자료를 연결해 주세요.'),
    ('deduction_proof', '공제 확인 자료', '입력한 공제 항목을 확인할 자료를 연결해 주세요.'),
)
DOCUMENT_KEYS = {item[0] for item in DOCUMENT_ITEMS}


def _identity(case_id, user_id):
    try:
        return uuid.UUID(str(case_id)), uuid.UUID(str(user_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, '상담 작업을 찾을 수 없습니다.') from None


def _user_identity(user_id):
    try:
        return uuid.UUID(str(user_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(401, '로그인이 필요합니다.') from None


def _questions(facts):
    return [{'key': key, 'question': question, 'unit': unit,
             'answered': facts.get(key) is not None, 'value': facts.get(key)}
            for key, question, unit in FACT_QUESTIONS]


def _checklist(facts, documents, available):
    result = []
    for key, title, prompt in DOCUMENT_ITEMS:
        needed = (key == 'income_proof' or
                  (key == 'expense_proof' and (facts.get('expense') or 0) > 0) or
                  (key == 'deduction_proof' and ((facts.get('other_deductions') or 0) > 0 or
                                                 (facts.get('personal_deduction_count') or 0) > 1)))
        saved = documents.get(key) or {}
        status = saved.get('status', 'pending')
        if status == 'attached' and available.get(saved.get('filename')) != saved.get('uploaded_at'):
            status = 'needs_recheck'
        result.append({'key': key, 'title': title, 'prompt': prompt, 'needed': needed,
                       'status': status, 'filename': saved.get('filename'),
                       'note': saved.get('note')})
    return result


async def _owned_row(conn, case_id, user_id, *, lock=False):
    cid, uid = _identity(case_id, user_id)
    row = await conn.fetchrow('SELECT * FROM consultation_cases WHERE id=$1 AND user_id=$2'
                              + (' FOR UPDATE' if lock else ''), cid, uid)
    if row is None:
        raise HTTPException(404, '상담 작업을 찾을 수 없습니다.')
    return dict(row)


async def _detail(conn, row):
    facts = row['facts'] or {}
    docs = row['checklist'] or {}
    filenames = [item.get('filename') for item in docs.values() if item.get('filename')]
    available = {}
    if filenames:
        rows = await conn.fetch('''SELECT metadata->>'source' AS filename, MIN(created_at) AS uploaded_at
            FROM documents WHERE user_id=$1 AND metadata->>'source'=ANY($2::text[])
            GROUP BY metadata->>'source' ''', row['user_id'], filenames)
        available = {item['filename']: item['uploaded_at'].isoformat() for item in rows}
    questions = _questions(facts)
    has_chat = bool(row['conversation_id'] and await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM chat_logs WHERE conversation_id=$1 AND message->>'role'='user')",
        row['conversation_id']))
    return {'id': str(row['id']), 'title': row['title'], 'question': row['question'],
            'kind': row['kind'], 'tax_year': row['tax_year'],
            'conversation_id': str(row['conversation_id']) if row['conversation_id'] else None,
            'has_chat': has_chat, 'facts': facts, 'questions': questions,
            'next_question': next((q['question'] for q in questions if not q['answered']), None),
            'checklist': _checklist(facts, docs, available), 'calculation': row['calculation'],
            'created_at': row['created_at'].isoformat(), 'updated_at': row['updated_at'].isoformat()}


async def list_cases(user_id):
    uid = _user_identity(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''SELECT id,title,question,tax_year,facts,calculation,updated_at
            FROM consultation_cases WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 50''', uid)
    return [{'id': str(row['id']), 'title': row['title'], 'question': row['question'],
             'tax_year': row['tax_year'],
             'answered': sum(row['facts'].get(key) is not None for key, _, _ in FACT_QUESTIONS),
             'has_calculation': row['calculation'] is not None,
             'updated_at': row['updated_at'].isoformat()} for row in rows]


async def create_case(user_id, body):
    uid = _user_identity(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            conv = await conn.fetchrow('''INSERT INTO conversations (user_id,title)
                VALUES ($1,$2) RETURNING id''', uid, body.title)
            row = await conn.fetchrow('''INSERT INTO consultation_cases
                (user_id,conversation_id,title,question,tax_year)
                VALUES ($1,$2,$3,$4,$5) RETURNING *''', uid, conv['id'], body.title,
                body.question, body.tax_year)
        return await _detail(conn, dict(row))


async def get_case(case_id, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await _detail(conn, await _owned_row(conn, case_id, user_id))


async def update_facts(case_id, user_id, patch):
    changes = patch.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, '변경할 상담 정보를 입력하세요.')
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _owned_row(conn, case_id, user_id, lock=True)
            facts = {**(row['facts'] or {}), **changes}
            updated = await conn.fetchrow('''UPDATE consultation_cases
                SET facts=$1, calculation=NULL, updated_at=now()
                WHERE id=$2 AND user_id=$3 RETURNING *''', facts, row['id'], row['user_id'])
        return await _detail(conn, dict(updated))


async def update_document(case_id, user_id, slot, body):
    if slot not in DOCUMENT_KEYS:
        raise HTTPException(404, '체크리스트 항목을 찾을 수 없습니다.')
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _owned_row(conn, case_id, user_id, lock=True)
            docs = dict(row['checklist'] or {})
            if body.status == 'attached':
                uploaded_at = await conn.fetchval('''SELECT MIN(created_at) FROM documents
                    WHERE user_id=$1 AND metadata->>'source'=$2''', row['user_id'], body.filename)
                if uploaded_at is None:
                    raise HTTPException(404, '내 문서에서 해당 파일을 찾을 수 없습니다.')
                docs[slot] = {'status': 'attached', 'filename': body.filename,
                              'uploaded_at': uploaded_at.isoformat(), 'note': (body.note or '').strip()}
            else:
                docs[slot] = {'status': 'not_available', 'note': body.note.strip()}
            updated = await conn.fetchrow('''UPDATE consultation_cases SET checklist=$1,updated_at=now()
                WHERE id=$2 AND user_id=$3 RETURNING *''', docs, row['id'], row['user_id'])
        return await _detail(conn, dict(updated))


async def clear_document(case_id, user_id, slot):
    if slot not in DOCUMENT_KEYS:
        raise HTTPException(404, '체크리스트 항목을 찾을 수 없습니다.')
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _owned_row(conn, case_id, user_id, lock=True)
            docs = dict(row['checklist'] or {})
            docs.pop(slot, None)
            updated = await conn.fetchrow('''UPDATE consultation_cases SET checklist=$1,updated_at=now()
                WHERE id=$2 AND user_id=$3 RETURNING *''', docs, row['id'], row['user_id'])
        return await _detail(conn, dict(updated))


async def calculate_case(case_id, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await _owned_row(conn, case_id, user_id)
    facts = row['facts'] or {}
    missing = [question for key, question, _ in FACT_QUESTIONS if facts.get(key) is None]
    if missing:
        raise HTTPException(422, {'code': 'needs_input', 'message': missing[0],
                                  'missing_count': len(missing)})
    result = await asyncio.wait_for(calculate_income_tax(
        **{key: facts[key] for key, _, _ in FACT_QUESTIONS},
        as_of=date(row['tax_year'], 12, 31)), timeout=30)
    snapshot = {'tax_year': row['tax_year'], 'facts': facts,
                'result': result.model_dump(), 'calculated_at': datetime.now(timezone.utc).isoformat()}
    async with pool.acquire() as conn:
        updated = await conn.fetchrow('''UPDATE consultation_cases
            SET calculation=$1,updated_at=now()
            WHERE id=$2 AND user_id=$3 AND facts=$4::jsonb RETURNING *''',
            snapshot, row['id'], row['user_id'], facts)
        if updated is None:
            raise HTTPException(409, '상담 정보가 변경되었습니다. 다시 계산해 주세요.')
        return await _detail(conn, dict(updated))


async def ensure_conversation(case_id, user_id):
    """Restore a case chat if the user deleted its earlier conversation."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _owned_row(conn, case_id, user_id, lock=True)
            if row['conversation_id'] is None:
                conv = await conn.fetchrow('''INSERT INTO conversations (user_id,title)
                    VALUES ($1,$2) RETURNING id''', row['user_id'], row['title'])
                row = dict(await conn.fetchrow('''UPDATE consultation_cases
                    SET conversation_id=$1,updated_at=now() WHERE id=$2 AND user_id=$3 RETURNING *''',
                    conv['id'], row['id'], row['user_id']))
        return await _detail(conn, row)


async def delete_case(case_id, user_id):
    cid, uid = _identity(case_id, user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        removed = await conn.fetchval('''DELETE FROM consultation_cases
            WHERE id=$1 AND user_id=$2 RETURNING id''', cid, uid)
    if removed is None:
        raise HTTPException(404, '상담 작업을 찾을 수 없습니다.')
    return {'status': 'deleted'}
