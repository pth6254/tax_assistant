"""Explicit adapters for production components; never call process_chat (DB writes)."""
from dataclasses import asdict
import logging
import time

from evaluation.schema import Observation

OFFLINE = {'reference', 'relation', 'graph_index', 'progressive_tax'}
MODEL_GENERATION = {'tool_selection', 'answer_fixed_context'}


def offline(case):
    if case.adapter == 'reference':
        from app.services.law.reference_parser import parse_law_reference, InvalidLawReference
        try:
            ref = parse_law_reference(case.input['text'])
            return asdict(ref) | {'canonical': ref.canonical, 'error_code': None}
        except InvalidLawReference:
            return {'error_code': 'invalid_reference'}
    if case.adapter == 'relation':
        from app.services.law.relation_extractor import extract_relations
        refs = extract_relations(case.input['text'], case.input.get('aliases'))
        return {'relations': [{'law': r['law_name'], 'reference': r['reference']} for r in refs]}
    if case.adapter == 'graph_index':
        from app.services.graph.index_service import build_graph, article_key
        rows = case.input['articles']
        names = {article_key(r): r['law_name'] + ' ' + r['article_no'] for r in rows}
        _, edges, unresolved = build_graph(rows)
        return {'relations': sorted([{'source': names[e['source']], 'target': names[e['target']],
                                      'reference': e['reference']} for e in edges], key=str), 'unresolved': unresolved}
    if case.adapter == 'progressive_tax':
        from app.services.calculator.brackets import apply_progressive_tax
        from app.services.calculator.errors import CalculationError
        try:
            amount, rate = apply_progressive_tax(case.input['taxable'], case.input['brackets'])
            return {'amount': amount, 'rate': rate, 'error_code': None}
        except CalculationError as error:
            return {'error_code': error.code}  # No fabricated zero amount on failure.
    raise ValueError('Unsupported offline adapter')


async def _documents(results):
    from app.services.graph.index_service import article_key
    from app.services.law.lookup_service import get_law_article
    documents = []
    for result in results:
        if not result.article_no:
            # Live runner uses an unused user ID; no existing user's PDF is in scope.
            continue
        article = await get_law_article(result.law_name, result.article_no)
        header = (article.article_no + (f' [{article.article_title}]' if article.article_title else '')) if article else ''
        same_text = article is not None and result.content == f'{header}\n{article.article_text}'
        documents.append(dict(law=result.law_name, reference=result.article_no,
                              kind='interpretation' if result.source_type == 'interpretation' else 'law',
                              version=article_key(article.model_dump()) if same_text else 'unverified-content',
                              source_url=result.source, quote=result.content))
    return documents


async def live(case, user_id):
    if case.adapter == 'retrieval':
        import config
        from app.services.search.hybrid_search_service import hybrid_search
        from app.services.search.graph_search_service import expand_graph
        original = config.GRAPH_RAG_ENABLED
        try:
            # Local process only; no .env writes or application flag changes. Serialized execution.
            config.GRAPH_RAG_ENABLED = False
            start = time.perf_counter()
            base = await hybrid_search([case.input['query']], law_filter=case.input.get('law_filter', 'ALL'),
                                       user_id=user_id, original_query=case.input['query'])
            base_time = time.perf_counter()-start
            config.GRAPH_RAG_ENABLED = True
            start = time.perf_counter()
            class ExpansionFailures(logging.Handler):
                failed = False
                def emit(self, record):
                    if record.levelno >= logging.WARNING:
                        self.failed = True
            handler = ExpansionFailures()
            graph_logger = logging.getLogger('app.services.search.graph_search_service')
            graph_logger.addHandler(handler)
            try:
                graph = await expand_graph(base, case.input['query'])
            finally:
                graph_logger.removeHandler(handler)
            graph_time = time.perf_counter()-start
            base_docs, graph_docs = await _documents(base), await _documents(graph)
            return [('base', {'results': base_docs, 'context_chars': sum(len(r.content) for r in base)}, base_time),
                    ('graph', {'results': graph_docs, 'base_results': base_docs,
                               'context_chars': sum(len(r.content) for r in graph),
                               'expansion_seconds': graph_time,
                               'expansion_failed': handler.failed,
                               'graph_evidence': [r.graph_evidence for r in graph if r.graph_evidence]}, base_time+graph_time)]
        finally:
            config.GRAPH_RAG_ENABLED = original
    if case.adapter == 'source':
        from app.services.law.lookup_service import get_law_article
        from app.services.graph.index_service import article_key
        article = await get_law_article(case.input['law'], case.input['reference'])
        return {'exists': article is not None, 'article': article.model_dump() if article else None,
                'version': article_key(article.model_dump()) if article else None}
    if case.adapter == 'calculator':
        from app.services.calculator.engine import CALCULATORS
        from app.services.calculator.errors import CalculationError
        from pydantic import ValidationError
        schema, module = CALCULATORS[case.input['tool']]
        try:
            params = schema.model_validate(case.input['params'], strict=True, extra='forbid')
            result = await module.calculate(**params.model_dump())
            return result.model_dump() | {'error_code': None}
        except CalculationError as error:
            return {'error_code': error.code}
        except ValidationError:
            return {'error_code': 'invalid_input'}
    if case.adapter == 'tool_selection':
        from app.services.tools.planner import select_tool
        selection = await select_tool(case.input['query'], case.input.get('history'))
        return {'tool': selection[0] if selection else 'none', 'params': selection[1] if selection else {}}
    if case.adapter == 'answer_fixed_context':
        from app.services.chat_service import (_FINAL_PROMPT_TEMPLATE, _generate_answer,
                                               _final_prompt_values, _append_source_list_if_missing)
        from app.services.ai_pipeline import text_chain
        from app.services.citation_guard import apply_citation_guard, extract_citations
        # Isolate generation from retrieval, history persistence, web search and tool execution.
        context = case.input['context']
        answer = await text_chain(_FINAL_PROMPT_TEMPLATE, _generate_answer, name='evaluation_fixed_context').ainvoke(
            _final_prompt_values(case.input['query'], context, '', []))
        answer = await _append_source_list_if_missing(answer, context)
        answer = apply_citation_guard(answer, context)
        return {'answer': answer, 'citations': [dict(law=l, reference=r) for _, l, r in extract_citations(answer)]}
    raise ValueError('Recorded observations must be supplied through the score command')


async def observe(case, mode, user_id, repeat, allow_generation, timeout):
    import asyncio
    start = time.perf_counter()
    variants = ['base', 'graph'] if case.stage == 'retrieval' else ['system']
    if (case.adapter == 'recorded' or (mode == 'offline' and case.adapter not in OFFLINE)
            or (case.adapter in MODEL_GENERATION and not allow_generation)):
        return []  # Becomes incomplete, never a passing skip.
    try:
        if case.adapter in OFFLINE:
            payload = offline(case)
        else:
            payload = await asyncio.wait_for(live(case, user_id), timeout)
        if case.adapter == 'retrieval':
            return [Observation(case_id=case.id, variant=v, repeat=repeat, payload=p, elapsed_seconds=t,
                                error='GraphExpansionUnavailable' if p.get('expansion_failed') else None)
                    for v, p, t in payload]
        return [Observation(case_id=case.id, repeat=repeat, payload=payload, elapsed_seconds=time.perf_counter()-start)]
    except Exception as error:
        # Raw DB/provider exceptions can expose private values. Preserve only type.
        return [Observation(case_id=case.id, variant=v, repeat=repeat, error=type(error).__name__,
                            elapsed_seconds=time.perf_counter()-start) for v in variants]


async def close_live_clients():
    from app.database import close_pool
    from app.services.embedding_service import close_http_client
    from app.services.llm_client import close_llm_client
    await close_pool()
    await close_http_client()
    await close_llm_client()
