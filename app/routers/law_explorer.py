"""Direct version-bound law reading and article comparison for the UI."""
from datetime import date
import difflib

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import verify_token
from app.database import get_pool
from app.services.law.reference_parser import parse_law_reference
from app.services.search.history_search import HistoryUnavailable, select_version, direct_article
from app.services.graph.knowledge_service import reviewed_citations

router = APIRouter(prefix='/api/law-explorer', tags=['law-explorer'])


@router.get('/laws')
async def laws(user: dict = Depends(verify_token)):
    pool = await get_pool()
    rows = await pool.fetch('''SELECT l.law_id,l.seed_name AS name,count(v.id) AS versions
        FROM law_history.laws l JOIN law_history.versions v ON v.law_id=l.law_id
        GROUP BY l.law_id,l.seed_name ORDER BY l.seed_name''')
    return [dict(row) for row in rows]


async def _version(law_id, day):
    try:
        version = await select_version(law_id, day)
    except HistoryUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    return version


def _version_info(version):
    return {'id': version['id'], 'law_id': version['law_id'], 'law_name': version['law_name'],
            'effective_date': version['effective_date'].isoformat(),
            'promulgation_date': version['promulgation_date'].isoformat() if version['promulgation_date'] else None,
            'source_url': version['source_url']}


@router.get('/resolve')
async def resolve(law_id: str, as_of: date, user: dict = Depends(verify_token)):
    return _version_info(await _version(law_id, as_of))


async def _article(version, article_no):
    try:
        reference = parse_law_reference(article_no)
        return await direct_article(version, reference)
    except (ValueError, HistoryUnavailable) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/article')
async def article(law_id: str, as_of: date, article_no: str = Query(max_length=50),
                  user: dict = Depends(verify_token)):
    version = await _version(law_id, as_of)
    item = await _article(version, article_no)
    relations, graph_status = [], 'ok'
    try:
        claims = await reviewed_citations(version, {item['article_no']})
        for claim in claims[:20]:
            assertion = claim['assertion']
            if assertion.get('quote') and assertion['quote'] in item['content']:
                relations.append({'quote': assertion['quote'], 'target_law': claim['target_law'],
                                  'target_reference': claim['target_reference'],
                                  'status': 'reviewed_text_relation'})
    except Exception:
        graph_status = 'unavailable'
    return {'version': _version_info(version), 'article': item, 'relations': relations,
            'graph_status': graph_status}


@router.get('/compare')
async def compare(law_id: str, left_date: date, right_date: date,
                  article_no: str = Query(max_length=50), user: dict = Depends(verify_token)):
    left_version, right_version = await _version(law_id, left_date), await _version(law_id, right_date)
    left, right = await _article(left_version, article_no), await _article(right_version, article_no)
    changes = list(difflib.unified_diff(left['content'].splitlines(), right['content'].splitlines(),
                                        fromfile=str(left_version['id']), tofile=str(right_version['id']),
                                        lineterm=''))
    return {'left': {'version': _version_info(left_version), 'article': left},
            'right': {'version': _version_info(right_version), 'article': right},
            'diff': changes[:2000], 'truncated': len(changes) > 2000}
