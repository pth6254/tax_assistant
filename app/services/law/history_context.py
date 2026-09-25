"""Deterministic intent routing and server-owned historical conversation scope."""
import re

from app.services.law.reference_parser import extract_law_reference, format_article_no

VERSION = re.compile(r'법령\s*버전\s*\d+')
DATE = re.compile(r'\d{4}(?:\s*년|[-./]\d{1,2}[-./]\d{1,2})')
LAW = re.compile(r'[가-힣]+법(?:률)?(?:\s*시행(?:령|규칙))?|법령|조문|제\s*\d+\s*조')
PAST = re.compile(r'과거\s*법|구법|종전|개정\s*전|당시')
CURRENT = re.compile(r'현행|현재|오늘|지금\s*기준')
OTHER_TASK = re.compile(r'계산|얼마|계약서|문서|서류|업로드|첨부|PDF|pdf')
FOLLOWUP = re.compile(r'그럼|그러면|해당|같은|그\s*(?:법|조|항)|제\s*\d+\s*[조항호]|[가-하]\s*목')


def temporal_request(query):
    if VERSION.search(query):
        return True
    if OTHER_TASK.search(query):
        return False
    return bool(PAST.search(query) or (DATE.search(query) and LAW.search(query)))


def needs_history(query):
    return temporal_request(query) or bool(
        not OTHER_TASK.search(query) and not CURRENT.search(query)
        and (FOLLOWUP.search(query) or DATE.search(query))
    )


def route(query, history):
    """Return an archive query or None. Never infer state from generated prose."""
    if OTHER_TASK.search(query) and not VERSION.search(query):
        return None
    if CURRENT.search(query) and not (VERSION.search(query) or DATE.search(query) or PAST.search(query)):
        return None
    if VERSION.search(query):
        return query  # Explicit input always wins; DB validates law/version identity.
    previous = next((m for m in reversed(history) if m.get('role') == 'assistant'), {})
    state = previous.get('history_context')
    if state is None:
        state = next((t.get('history_context') for t in previous.get('tools', [])
                      if t.get('tool') == 'history_lookup'), None)
    if state and (FOLLOWUP.search(query) or DATE.search(query) or temporal_request(query)):
        # A new named law/date must be resolved again, not pinned to the old ID.
        named = re.search(r'[가-힣]+법(?:률)?(?:\s*시행(?:령|규칙))?', query)
        changed_law = named and ''.join(named[0].split()) not in {
            ''.join(state['law_name'].split()), '법령', '구법'}
        if DATE.search(query) or changed_law:
            prefix = '' if DATE.search(query) else state['as_of'] + ' 기준 '
            if not named:
                prefix += state['law_name'] + ' '
        else:
            prefix = f"법령버전 {state['version_id']} {state['as_of']} 기준 "
        if not extract_law_reference(query) and re.search(r'제\s*\d+\s*[항호]|[가-하]\s*목', query):
            if state.get('article') is not None:
                reference_prefix = format_article_no(state['article'], state.get('article_branch')) + ' '
                if not re.search(r'\d+\s*항', query) and state.get('paragraph'):
                    reference_prefix += f"제{state['paragraph']}항 "
                if not re.search(r'\d+\s*[항호]', query) and state.get('item'):
                    reference_prefix += f"제{state['item']}호" + (f"의{state['item_branch']}" if state.get('item_branch') else '') + ' '
                query = re.sub(r'(?=제\s*\d+\s*[항호]|[가-하]\s*목)', lambda _: reference_prefix, query, count=1)
            else:
                return '과거 법령 ' + query  # Ask for an article, never use current-law RAG.
        return prefix + query
    if temporal_request(query):
        return query
    # Legacy/error turns without verified metadata cannot silently switch to today.
    last_user = next((m.get('content', '') for m in reversed(history) if m.get('role') == 'user'), '')
    if (FOLLOWUP.search(query) or DATE.search(query)) and temporal_request(last_user):
        return '과거 법령 ' + query
    return None
