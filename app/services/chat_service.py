"""
services/chat_service.py — 채팅 한 턴의 흐름
과거 법령 경로 → 계산기·원문·문서 도구 → 쟁점별 근거 검색과 검증된 답변 → 대화 저장.
스트리밍과 비스트리밍은 같은 `_answer_turn`을 쓴다.
"""
import asyncio
import json
import logging
import re
import time
import uuid as _uuid
from dataclasses import dataclass
from typing import AsyncGenerator

from config import MEMORY_TURNS
from app.services.calculator.engine import CALCULATORS, CalcRun, format_calculation_answer
from app.services.chat_history import history_entry
from app.services.tools.planner import run_tools_for_query
from app.services.evidence import EvidenceContext
from app.services.reliable_workflow import prepare_context, answer_context
from app.services.law.reference_parser import extract_law_references
from app.services.law.history_context import needs_history, route as history_route
from app.services.tax_laws import LAW_KEYWORDS
from app.services.law.history_answer import answer as history_answer
from app.services.answer_verification import unavailable_verification, unassessed_verification
from langsmith import trace, traceable
from app.database import get_pool
from app.services.search.hybrid_search_service import hybrid_search

logger = logging.getLogger(__name__)

# 세목 키워드 매핑은 tax_laws.LAW_KEYWORDS (후보를 제안할 뿐 제외하지 않는다)
_LAW_KW = LAW_KEYWORDS


def _match_laws_by_keyword(query: str) -> list[str]:
    """키워드 매칭으로 후보 세목을 찾는다.

    같은 위치에서 여러 세목의 키워드가 겹치면(예: '체납' vs '지방세 체납',
    '소득세' vs '지방소득세') 더 긴(구체적인) 키워드만 채택하여 불필요한
    다중 매칭 → ALL 폴백을 줄인다.
    """
    q = query.lower()
    spans: list[tuple[int, int, str]] = []
    for law, kws in _LAW_KW.items():
        for kw in kws:
            start = 0
            while (idx := q.find(kw, start)) != -1:
                spans.append((idx, idx + len(kw), law))
                start = idx + 1

    spans.sort(key=lambda s: s[0] - s[1])  # 길이 내림차순(긴 구간 우선)
    kept: list[tuple[int, int, str]] = []
    for start, end, law in spans:
        if any(start < k_end and end > k_start for k_start, k_end, _ in kept):
            continue
        kept.append((start, end, law))

    return sorted({law for _, _, law in kept})


async def _fetch_history(conversation_id: _uuid.UUID) -> list[dict]:
    """Postgres에서 최근 대화 메모리 조회."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT message FROM chat_logs
               WHERE conversation_id = $1
               ORDER BY id DESC LIMIT $2""",
            conversation_id, MEMORY_TURNS * 2,
        )
    return [history_entry(r["message"]) for r in reversed(rows)]


async def _save_history(
    conversation_id: _uuid.UUID,
    query: str,
    answer: str,
    is_first: bool = False,
    tools: list[dict] | None = None,
    verification: dict | None = None,
) -> None:
    """대화 턴을 chat_logs에 저장. 첫 메시지면 대화 제목도 자동 업데이트."""
    title = query[:28].rstrip() + ("..." if len(query) > 28 else "")
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchrow('SELECT id FROM conversations WHERE id=$1 FOR UPDATE', conversation_id)
            await conn.executemany(
                "INSERT INTO chat_logs (conversation_id, message) VALUES ($1, $2)",
                [
                    (conversation_id, json.dumps({"role": "user",      "content": query},  ensure_ascii=False)),
                    (conversation_id, json.dumps({"role": "assistant", "content": answer,
                                                  **({"tools": tools} if tools else {}),
                                                  **({"verification": verification} if verification else {})}, ensure_ascii=False)),
                ],
            )
            if is_first:
                await conn.execute(
                    "UPDATE conversations SET title = $1, updated_at = now() WHERE id = $2",
                    title, conversation_id,
                )
            else:
                await conn.execute(
                    "UPDATE conversations SET updated_at = now() WHERE id = $1",
                    conversation_id,
                )


async def _fetch_rag_and_web_context(
    query: str,
    conversation_id: _uuid.UUID,
    user_id: str,
    on_tool_event=None,
    history_override: list[dict] | None = None,
) -> tuple[str, str, list[dict], CalcRun | None]:
    """
    세목 분류·법령 검색·웹 검색·세금 계산기를 수행하고
    (context, web_results, history, calc_run)를 반환한다.
    복합 요청은 쟁점별 작업으로 분해한다. 단순 원문/문서 조회는 별도로
    처리하고 분석에는 서버 출처 레코드를 유지하는 근거 컨텍스트를 반환한다.
    """
    t0 = time.perf_counter()

    # The calculator's pending question travels with the history; the archive context does not.
    history = [{k: m[k] for k in ("role", "content", "calculator_request") if k in m}
               for m in (history_override if history_override is not None else await _fetch_history(conversation_id))]
    laws = _match_laws_by_keyword(query)
    # Composite tasks must not be consumed by a single tool's early return.
    if len(laws) > 1 or len(extract_law_references(query)) > 1 or (
        re.search(r"원문|내 문서|업로드|계산", query) and re.search(r"그리고|함께|비교|설명", query)
    ):
        context = await prepare_context(query, laws, user_id, history, hybrid_search, on_tool_event)
        return context, "웹 검색 생략", history, None
    event_options = {"on_event": on_tool_event} if on_tool_event else {}
    tool_run = await run_tools_for_query(query, user_id=user_id, history=history, **event_options)
    if tool_run and tool_run.tool == 'formula_calculation':
        from app.services.calculator.formula_workflow import calculate_reference
        context, calc_run = await calculate_reference(query, history, user_id, hybrid_search, on_tool_event)
        return context, '웹 검색 생략', history, calc_run
    calc_run = tool_run.calculation if tool_run else None
    if tool_run and tool_run.status != "ok" and (tool_run.tool in CALCULATORS or tool_run.tool == "none"):
        return tool_run.context, "웹 검색 생략", history, None
    # 명시적 원문/문서 조회는 중복 검색과 다른 자료 혼합을 피한다.
    if tool_run and tool_run.tool in {"law_lookup", "document_search"}:
        context = tool_run.context
        return context, "웹 검색 생략", history, calc_run

    if calc_run:
        return EvidenceContext("", ()), "웹 검색 생략", history, calc_run

    context = await prepare_context(query, laws, user_id, history, hybrid_search, on_tool_event)
    return context, "웹 검색 생략", history, None


def _trace_chat_inputs(inputs: dict) -> dict:
    return {"query": inputs.get("query"), "conversation_id": inputs.get("conversation_id"),
            "regeneration": inputs.get("regeneration") is not None}


def _trace_stream_output(events: list[dict]) -> dict:
    answer = ""
    verification = None
    for event in events:
        if event.get("type") == "chunk":
            answer += event.get("text", "")
        elif event.get("type") == "replace":
            answer = event.get("text", "")
        elif event.get("type") == "verification" and event.get("data"):
            verification = event["data"]
    return {"answer": answer, **({"verification": verification} if verification is not None else {})}


def _calc_meta(calc_run: CalcRun | None) -> dict | None:
    """프론트엔드 계산기 화면 프리필용 메타데이터(도구명 + 파라미터)."""
    return {"tool": calc_run.tool, "params": calc_run.params} if calc_run and calc_run.tool != 'formula_calculation' else None



def _failed_tool_answer(events):
    for event in reversed(events):
        if event.get("scope") == "issue" or event.get("status") == "no_tool_needed":
            continue
        if event.get("tool") in {"law_lookup", "document_search"} and event.get("status") not in {"ok", "selecting", "running"}:
            document = event.get("tool") == "document_search"
            status = event.get("status")
            if status in {"needs_input", "invalid_arguments"}:
                message = ("검색할 문서와 찾으려는 내용을 구체적으로 알려주세요." if document else
                           "법령명과 조·항·호 번호를 확인해 주세요. 과거 법령이라면 적용할 날짜나 개정 전 버전도 알려주세요.")
            elif status == "not_found":
                message = ("접근 가능한 업로드 문서에서 요청한 자료를 찾지 못했습니다. 업로드 상태와 검색 내용을 확인해 주세요." if document else
                           "저장된 법령 자료에서 요청한 조문을 확인하지 못했습니다. 법령명·조문 번호·적용 시점을 확인하거나 공식 원문을 제공해 주세요.")
            elif status == "timeout":
                message = "자료 조회 시간이 초과됐습니다. 잠시 후 다시 시도해 주세요."
            else:
                message = "자료 조회를 완료하지 못했습니다. 잠시 후 다시 시도해 주세요."
            return message + "\n\n근거를 확보하지 못해 이번 요청의 세무 판단은 유보합니다. 조회 실패가 해당 규정이나 권리가 없다는 뜻은 아닙니다."
        if event.get("tool") in {*CALCULATORS, "none"} and event.get("status") not in {"ok", "selecting", "running"}:
            if event.get("tool") == "none":
                if event.get("status") == "selection_error":
                    return "요청을 처리할 도구를 선택하는 과정에서 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
                return event.get("context") or "계산할 세목과 계산에 사용할 금액·조건을 알려주세요."
            if event.get("status") == "needs_input":
                # A question for the user, not a failure: the reply continues this calculation.
                return event.get("context", "계산에 필요한 사실을 알려주세요.") + "\n\n알려주시면 이어서 계산합니다."
            return event.get("context", "계산을 완료하지 못했습니다.") + "\n\n세액을 산출하지 않았습니다. 계산 실패는 납부세액이 0원이라는 뜻이 아닙니다."
    return None


@dataclass
class _Turn:
    """One answered chat turn before it is stored."""
    answer: str
    verification: dict
    calc_meta: dict | None
    is_first: bool
    events: list
    failed: bool = False


async def _answer_turn(query, conv_id, user_id, emit, progress=None, history_override=None) -> _Turn:
    """Archive route, tools and evidence, or the failure notice; the same for streaming and not.

    `emit` receives tool events (they are also stored with the answer), `progress` only the answer's
    verification progress.
    """
    events = []

    def record(event):
        events.append(event)
        emit(event)

    # Only a question that may refer back to an archived version needs the history before routing.
    early = (history_override if history_override is not None else await _fetch_history(conv_id)) \
        if needs_history(query) else []
    archive_query = history_route(query, early)
    if archive_query is not None:
        answer = await history_answer(archive_query, record)
        return _Turn(answer, unassessed_verification(), None, len(early) == 0, events)
    context, _, history, calc_run = await _fetch_rag_and_web_context(
        query, conv_id, user_id, on_tool_event=record,
        **({"history_override": history_override} if history_override is not None else {}))
    is_first = len(history) == 0
    failure = _failed_tool_answer(events)
    if failure:
        return _Turn(failure, unavailable_verification(events), None, is_first, events, failed=True)
    if not isinstance(context, EvidenceContext):
        # Every successful path returns server-built evidence; a bare string here is a routing bug.
        raise TypeError("chat context must be an EvidenceContext")
    answer, verification = await _answer_evidence_context(query, context, calc_run, user_id, progress)
    return _Turn(answer, verification, _calc_meta(calc_run), is_first, events)


async def _store(conv_id, query, turn, regeneration=None):
    tools = _terminal_tools(turn.events)
    if regeneration:
        from app.services.answer_version_service import commit_regeneration
        pool = await get_pool()
        async with pool.acquire() as conn:
            await commit_regeneration(conn, conv_id, regeneration, turn.answer, tools, verification=turn.verification)
    else:
        await _save_history(conv_id, query, turn.answer, is_first=turn.is_first, tools=tools,
                            verification=turn.verification)


@traceable(name="chat_request", run_type="chain", process_inputs=_trace_chat_inputs,
           tags=["tax-assistant", "chat"])
async def process_chat(query: str, conversation_id: str, user_id: str, *, tool_events: list | None = None,
                       verification_out: list | None = None) -> tuple[str, dict | None]:
    """한 턴의 (최종 답변, 계산기 메타데이터)를 반환한다 (비스트리밍)."""
    logger.info("[CHAT] 요청 수신: %d자", len(query))
    t0 = time.perf_counter()
    conv_id = _uuid.UUID(conversation_id)
    events = tool_events if tool_events is not None else []
    turn = await _answer_turn(query, conv_id, user_id, events.append)
    if verification_out is not None:
        verification_out.append(turn.verification)
    await _store(conv_id, query, turn)
    logger.info("[CHAT] 응답 완료 — 총 %.1fs | 답변 %d자", time.perf_counter() - t0, len(turn.answer))
    return turn.answer, turn.calc_meta


async def stream_chat_response(
    query: str,
    conversation_id: str,
    user_id: str,
    regeneration=None,
) -> AsyncGenerator[dict, None]:
    """Trace the entire stream while forwarding close/cancel to its worker."""
    async with trace("chat_stream", run_type="chain",
                     inputs={"query": query, "conversation_id": conversation_id,
                             "regeneration": regeneration is not None},
                     tags=["tax-assistant", "chat"]) as run:
        stream = _stream_chat_response_impl(query, conversation_id, user_id, regeneration)
        observed = []
        try:
            async for event in stream:
                observed.append(event)
                yield event
            run.end(outputs=_trace_stream_output(observed))
        finally:
            await stream.aclose()


async def _stream_chat_response_impl(
    query: str,
    conversation_id: str,
    user_id: str,
    regeneration=None,
) -> AsyncGenerator[dict, None]:
    """한 턴을 이벤트로 yield한다 (스트리밍).

    {"type": "tool", ...} — 도구 진행/결과, {"type": "verification", ...} — 검증 진행과 결과
    {"type": "chunk", "text": ...} — 검증을 마친 답변(한 번), {"type": "calc", ...} — 계산기 화면 프리필(실행된 경우)
    """
    logger.info("[STREAM] 요청 수신: %d자", len(query))
    t0 = time.perf_counter()
    conv_id = _uuid.UUID(conversation_id)
    queue = asyncio.Queue()

    async def answer():
        try:
            return await _answer_turn(query, conv_id, user_id, queue.put_nowait, queue.put_nowait,
                                      regeneration.history if regeneration else None)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(answer())
    try:
        while (event := await queue.get()) is not None:
            yield event
        turn = await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    if regeneration and turn.failed and turn.verification["status"] == "withheld":
        raise ValueError(turn.answer)
    yield {"type": "chunk", "text": turn.answer}
    yield {"type": "verification", "data": turn.verification}
    if turn.calc_meta:
        yield {"type": "calc", **turn.calc_meta}
    await _store(conv_id, query, turn, regeneration)
    logger.info("[STREAM] 완료 — 총 %.1fs | 답변 %d자", time.perf_counter() - t0, len(turn.answer))


def _terminal_tools(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type", "tool") == "tool" and e["status"] not in {"selecting", "running"}]


async def _answer_evidence_context(query, context, calc_run, user_id, on_progress=None):
    if calc_run and calc_run.tool == 'formula_calculation' and calc_run.verification:
        return calc_run.context, calc_run.verification
    if context.plan is None and any(r.origin == "user_document" for r in context.records) and re.search(r"요약|설명|비교", query):
        from app.schemas.reliability import Issue, QuestionPlan
        context = EvidenceContext(str(context), context.records, plan=QuestionPlan(issues=[
            Issue(id="D1", request_quote=query, question=query, kind="document_search")]))
    if context.plan is not None:
        return await answer_context(query, context, user_id, hybrid_search, on_progress)
    # Exact tools return the actual snapshot, with no generative paraphrase.
    from app.services.evidence import is_official
    if calc_run:
        return format_calculation_answer(calc_run), {"schema_version": "2.0", "status": "checked", "citations": [],
            "checks": {"citation": "not_assessed", "calculation": "checked", "legal_application": "not_assessed"},
            "note": "사용자 입력을 대조한 계산기의 결과입니다. 법적 적용 요건은 별도 확인이 필요합니다."}
    records = [r for r in context.records if is_official(r) or r.origin == "user_document"]
    answer = "\n\n".join(f"{r.law_name or r.source} {r.reference}\n\n{r.text}" for r in records)
    return answer or "원본 정보가 확인되지 않아 조회 결과를 제공하지 못했습니다.", {
        "schema_version": "2.0", "status": "checked" if records else "withheld",
        "checks": {"citation": "checked" if records else "failed", "calculation": "not_applicable", "legal_application": "not_assessed"},
        "citations": [dict(evidence_id=r.id, law_name=r.law_name, reference=r.reference, label=r.category,
                           origin=r.origin, version_id=r.version_id, effective_from=r.effective_from,
                           content_hash=r.content_hash, text=r.text, source=r.source, location=r.location) for r in records],
        "note": "조회한 원문 발췌입니다. 사용자 문서는 거래 사실이나 공식 법령의 증명이 아닙니다.",
    }
