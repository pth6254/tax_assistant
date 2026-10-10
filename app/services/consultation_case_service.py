"""User-owned, deterministic consultation workflows backed by existing calculators."""
import asyncio
from datetime import date, datetime, timezone
import uuid

from fastapi import HTTPException

from app.database import get_pool
from app.services.calculator.income_tax import calculate as calculate_income_tax
from app.services.calculator import capital_gains, inheritance, gift_tax, vat, penalty_tax
from app.services.consultation_catalog import CASE_KINDS, case_kind


CALCULATORS = {
    'capital_gains': capital_gains.calculate,
    'inheritance': inheritance.calculate,
    'gift': gift_tax.calculate,
    'vat': vat.calculate,
    'penalty_tax': penalty_tax.calculate,
}
INACTIVE_DEFAULTS = {'is_minor': False, 'business_type': '소매업',
                     'is_negligent': False, 'days_late': 0,
                     'is_one_home': False, 'residence_years': 0, 'acquired_in_adjusted_area': False,
                     'multi_home_surcharge': '없음', 'expense': 0, 'sincere_business': False, 'withheld': True}


def _active_question_specs(kind, facts):
    questions = case_kind(kind)['questions']
    if kind == 'gift' and facts.get('relation') != '직계존비속':
        return tuple(q for q in questions if q[0] != 'is_minor')
    if kind == 'vat' and facts.get('is_simplified') is not True:
        return tuple(q for q in questions if q[0] != 'business_type')
    if kind == 'capital_gains':
        # Only a house has the one-home exemption, the residence table and the surcharge;
        # a one-home household is never surcharged, and residence only matters to one home.
        if facts.get('asset_type') != '주택':
            skip = {'is_one_home', 'residence_years', 'acquired_in_adjusted_area', 'multi_home_surcharge'}
        elif facts.get('is_one_home') is True:
            skip = {'multi_home_surcharge'}
        elif facts.get('is_one_home') is False:
            skip = {'residence_years', 'acquired_in_adjusted_area'}
        else:
            skip = set()
        return tuple(q for q in questions if q[0] not in skip)
    if kind == 'income_tax':
        # Expenses and the 성실사업자 credit belong to business income; a wage earner's standard
        # credit is 13만원 whatever the business; withholding matters only with interest or dividends.
        skip = set()
        if facts.get('income') == 0:
            skip |= {'expense', 'sincere_business'}
        if (facts.get('wage_income') or 0) > 0:
            skip.add('sincere_business')
        if facts.get('interest_income') == 0 and facts.get('dividend_gross_up') == 0:
            skip.add('withheld')
        return tuple(q for q in questions if q[0] not in skip)
    if kind == 'penalty_tax':
        skip = 'is_negligent' if facts.get('penalty_type') == '납부지연' else 'days_late'
        return tuple(q for q in questions if q[0] != skip)
    return questions


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


def _answered(value, options):
    # A stored choice that is no longer offered (e.g. the old '부동산') is asked again.
    return value is not None and (not options or value in options)


def _questions(facts, kind='income_tax'):
    return [{'key': key, 'question': question, 'type': field_type,
             'unit': '원' if field_type == 'amount' else '명' if key in {'personal_deduction_count', 'children_count'} else '년' if key in {'holding_years', 'residence_years'} else '일' if key == 'days_late' else None,
             'options': list(options) if options else None,
             'answered': _answered(facts.get(key), options), 'value': facts.get(key)}
            for key, question, field_type, options in _active_question_specs(kind, facts)]


def _checklist(facts, documents, available, kind='income_tax'):
    result = []
    for key, title, prompt, condition in case_kind(kind)['documents']:
        needed = (condition is None or bool(facts.get(condition)) or
                  (kind == 'income_tax' and key == 'deduction_proof' and
                   (facts.get('personal_deduction_count') or 0) > 1))
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
    questions = _questions(facts, row['kind'])
    has_chat = bool(row['conversation_id'] and await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM chat_logs WHERE conversation_id=$1 AND message->>'role'='user')",
        row['conversation_id']))
    return {'id': str(row['id']), 'title': row['title'], 'question': row['question'],
            'kind': row['kind'], 'kind_label': case_kind(row['kind'])['label'],
            'tax_year': row['tax_year'],
            'reference_date': row.get('reference_date', date(row['tax_year'], 12, 31)).isoformat(),
            'conversation_id': str(row['conversation_id']) if row['conversation_id'] else None,
            'has_chat': has_chat, 'facts': facts, 'questions': questions,
            'next_question': next((q['question'] for q in questions if not q['answered']), None),
            'checklist': _checklist(facts, docs, available, row['kind']), 'calculation': row['calculation'],
            'created_at': row['created_at'].isoformat(), 'updated_at': row['updated_at'].isoformat()}


async def list_cases(user_id):
    uid = _user_identity(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''SELECT id,title,question,kind,tax_year,reference_date,facts,calculation,updated_at
            FROM consultation_cases WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 50''', uid)
    return [{'id': str(row['id']), 'title': row['title'], 'question': row['question'],
             'kind': row['kind'], 'kind_label': case_kind(row['kind'])['label'],
             'tax_year': row['tax_year'], 'reference_date': row['reference_date'].isoformat(),
             'question_count': len(_active_question_specs(row['kind'], row['facts'])),
             'answered': sum(row['facts'].get(key) is not None for key, _, _, _ in _active_question_specs(row['kind'], row['facts'])),
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
                (user_id,conversation_id,title,question,kind,tax_year,reference_date)
                VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *''', uid, conv['id'], body.title,
                body.question, body.kind, body.tax_year, body.reference_date)
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
            allowed = {q[0] for q in case_kind(row['kind'])['questions']}
            if not changes.keys() <= allowed:
                raise HTTPException(422, '이 상담 유형에 해당하지 않는 입력 항목입니다.')
            facts = {**(row['facts'] or {}), **changes}
            updated = await conn.fetchrow('''UPDATE consultation_cases
                SET facts=$1, calculation=NULL, updated_at=now()
                WHERE id=$2 AND user_id=$3 RETURNING *''', facts, row['id'], row['user_id'])
        return await _detail(conn, dict(updated))


async def update_document(case_id, user_id, slot, body):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _owned_row(conn, case_id, user_id, lock=True)
            if slot not in {item[0] for item in case_kind(row['kind'])['documents']}:
                raise HTTPException(404, '체크리스트 항목을 찾을 수 없습니다.')
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
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _owned_row(conn, case_id, user_id, lock=True)
            if slot not in {item[0] for item in case_kind(row['kind'])['documents']}:
                raise HTTPException(404, '체크리스트 항목을 찾을 수 없습니다.')
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
    questions = _active_question_specs(row['kind'], facts)
    missing = [question for key, question, _, options in questions
               if not _answered(facts.get(key), options)]
    if missing:
        raise HTTPException(422, {'code': 'needs_input', 'message': missing[0],
                                  'missing_count': len(missing)})
    reference_date = row.get('reference_date') or date(row['tax_year'], 12, 31)
    calculator = calculate_income_tax if row['kind'] == 'income_tax' else CALCULATORS[row['kind']]
    inputs = {key: facts[key] for key, _, _, _ in questions}
    inputs.update({key: value for key, value in INACTIVE_DEFAULTS.items()
                   if key in {q[0] for q in case_kind(row['kind'])['questions']} and key not in inputs})
    result = await asyncio.wait_for(calculator(
        **inputs,
        as_of=reference_date), timeout=30)
    snapshot = {'tax_year': row['tax_year'], 'reference_date': reference_date.isoformat(),
                'kind': row['kind'], 'facts': facts,
                'result': result.model_dump(), 'calculated_at': datetime.now(timezone.utc).isoformat()}
    async with pool.acquire() as conn:
        updated = await conn.fetchrow('''UPDATE consultation_cases
            SET calculation=$1,updated_at=now()
            WHERE id=$2 AND user_id=$3 AND facts=$4::jsonb AND reference_date=$5 RETURNING *''',
            snapshot, row['id'], row['user_id'], facts, reference_date)
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


async def list_scenarios(case_id, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _owned_row(conn, case_id, user_id)
        cid, uid = _identity(case_id, user_id)
        rows = await conn.fetch('''SELECT id,name,kind,reference_date,facts,result,created_at
            FROM consultation_scenarios WHERE case_id=$1 AND user_id=$2
            ORDER BY created_at DESC,id DESC LIMIT 30''', cid, uid)
    return [{**dict(row), 'id': str(row['id']), 'reference_date': row['reference_date'].isoformat(),
             'created_at': row['created_at'].isoformat()} for row in rows]


async def save_scenario(case_id, user_id, name):
    if not name:
        raise HTTPException(422, '시나리오 이름을 입력하세요.')
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _owned_row(conn, case_id, user_id, lock=True)
            calc = row['calculation']
            if not calc or calc.get('facts') != row['facts'] or calc.get('reference_date') != row['reference_date'].isoformat():
                raise HTTPException(409, '현재 입력으로 다시 계산한 후 저장해 주세요.')
            count = await conn.fetchval('SELECT count(*) FROM consultation_scenarios WHERE case_id=$1', row['id'])
            if count >= 30:
                raise HTTPException(409, '상담당 최대 30개까지 저장할 수 있습니다.')
            saved = await conn.fetchrow('''INSERT INTO consultation_scenarios
                (user_id,case_id,name,kind,reference_date,facts,result)
                VALUES($1,$2,$3,$4,$5,$6,$7)
                RETURNING id,name,kind,reference_date,facts,result,created_at''',
                row['user_id'], row['id'], name, row['kind'], row['reference_date'],
                row['facts'], calc['result'])
    return {**dict(saved), 'id': str(saved['id']),
            'reference_date': saved['reference_date'].isoformat(),
            'created_at': saved['created_at'].isoformat()}


async def delete_scenario(case_id, scenario_id, user_id):
    cid, uid = _identity(case_id, user_id)
    try:
        sid = uuid.UUID(str(scenario_id))
    except (ValueError, TypeError):
        raise HTTPException(404, '시나리오를 찾을 수 없습니다.') from None
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _owned_row(conn, case_id, user_id)
        deleted = await conn.fetchval('''DELETE FROM consultation_scenarios
            WHERE id=$1 AND case_id=$2 AND user_id=$3 RETURNING id''', sid, cid, uid)
    if not deleted:
        raise HTTPException(404, '시나리오를 찾을 수 없습니다.')
    return {'status': 'deleted'}


async def apply_reviewed_field(case_id, user_id, filename, field_key):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await _owned_row(conn, case_id, user_id, lock=True)
            amount_keys = {key for key, _, kind, _ in case_kind(row['kind'])['questions'] if kind == 'amount'}
            if field_key not in amount_keys:
                raise HTTPException(422, '이 상담에서 사용할 수 없는 금액 항목입니다.')
            linked = [item for item in (row['checklist'] or {}).values()
                      if item.get('status') == 'attached' and item.get('filename') == filename]
            if not linked:
                raise HTTPException(409, '먼저 이 상담의 서류 항목에 문서를 연결하세요.')
            uploaded_at = await conn.fetchval('''SELECT MIN(created_at) FROM documents
                WHERE user_id=$1 AND metadata->>'source'=$2''', row['user_id'], filename)
            if not uploaded_at or not any(item.get('uploaded_at') == uploaded_at.isoformat()
                                          for item in linked):
                raise HTTPException(409, '문서가 교체되었습니다. 원본을 다시 확인하고 상담에 다시 연결하세요.')
            review = await conn.fetchrow('''SELECT r.fields,r.document_sha256,f.sha256
                FROM user_document_reviews r JOIN user_document_files f
                  ON f.user_id=r.user_id AND f.filename=r.filename
                WHERE r.user_id=$1 AND r.filename=$2''', row['user_id'], filename)
            if not review or review['document_sha256'] != review['sha256']:
                raise HTTPException(409, '현재 문서에 대한 확인된 검토값이 없습니다.')
            selected = review['fields'].get(field_key)
            if not selected or type(selected.get('value')) is not int or selected['value'] < 0:
                raise HTTPException(409, '해당 계산 항목의 확인된 검토값이 없습니다.')
            facts = {**(row['facts'] or {}), field_key: selected['value']}
            updated = await conn.fetchrow('''UPDATE consultation_cases
                SET facts=$1,calculation=NULL,updated_at=now()
                WHERE id=$2 AND user_id=$3 RETURNING *''', facts, row['id'], row['user_id'])
        return await _detail(conn, dict(updated))
