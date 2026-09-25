"""Resume only output-length terminations of a final chat answer."""
import logging
from collections.abc import AsyncIterator
from collections.abc import Awaitable, Callable

from app.services.inference.llm.errors import LLMGenerationIncomplete
from app.services.llm_client import call_llm, stream_llm
from config import LLM_MAX_CONTINUATIONS

logger = logging.getLogger(__name__)
_CONTINUE = (
    "앞의 답변이 출력 길이 제한으로 중단되었습니다. 같은 질문과 근거를 유지하며 마지막 글자부터 "
    "남은 답변만 이어서 작성하세요. 이미 쓴 문장·표·출처를 반복하거나 새로운 근거를 만들지 마세요. "
    "근거 출처 목록까지 마무리하세요."
)
_PREFIX_BUFFER = 1024


def _next_messages(original: list[dict], answer: str) -> list[dict]:
    return [*original, {"role": "assistant", "content": answer},
            {"role": "user", "content": _CONTINUE}]


def _novel_text(previous: str, resumed: str, *, final: bool = False) -> str | None:
    """Return only new text; defer short repeated prefixes until disambiguated."""
    repeated = previous.startswith(resumed) or previous.endswith(resumed)
    if repeated and len(resumed) < min(len(previous), 4096) and not final:
        return None
    if repeated:
        raise LLMGenerationIncomplete("repeated_content")
    overlap = next((size for size in range(min(len(previous), len(resumed)), 0, -1)
                    if previous.endswith(resumed[:size])), 0)
    return resumed[overlap:]


async def complete_answer(
    messages: list[dict], temperature: float = 0.3,
    generate: Callable[..., Awaitable[str]] = call_llm,
) -> str:
    answer = ""
    for attempt in range(LLM_MAX_CONTINUATIONS + 1):
        current = messages if attempt == 0 else _next_messages(messages, answer)
        try:
            part = await generate(current, temperature=temperature)
            finished = True
        except LLMGenerationIncomplete as exc:
            if exc.reason != "length" or not exc.partial_content:
                raise
            part = exc.partial_content
            finished = False
        delta = part if attempt == 0 else _novel_text(answer, part, final=True)
        if not delta:
            raise LLMGenerationIncomplete("no_new_content")
        answer += delta
        if finished:
            return answer
        if attempt == LLM_MAX_CONTINUATIONS:
            raise LLMGenerationIncomplete("continuation_limit")
        logger.info("LLM answer continuation attempt=%d", attempt + 1)
    raise LLMGenerationIncomplete("continuation_limit")


async def stream_answer(messages: list[dict], temperature: float = 0.3) -> AsyncIterator[str]:
    answer = ""
    for attempt in range(LLM_MAX_CONTINUATIONS + 1):
        current = messages if attempt == 0 else _next_messages(messages, answer)
        prefix = ""
        prefix_checked = attempt == 0
        finished = True
        try:
            async for chunk in stream_llm(current, temperature=temperature):
                if not chunk:
                    continue
                if not prefix_checked:
                    prefix += chunk
                    if len(prefix) < _PREFIX_BUFFER:
                        continue
                    delta = _novel_text(answer, prefix)
                    if delta is None:
                        continue
                    prefix_checked = True
                    chunk = delta
                if chunk:
                    answer += chunk
                    yield chunk
        except LLMGenerationIncomplete as exc:
            if exc.reason != "length":
                raise
            finished = False
        if not prefix_checked and prefix:
            delta = _novel_text(answer, prefix, final=True)
            if delta:
                answer += delta
                yield delta
        if finished:
            if not answer:
                raise LLMGenerationIncomplete("empty_content")
            return
        if not answer:
            raise LLMGenerationIncomplete("empty_content")
        if attempt == LLM_MAX_CONTINUATIONS:
            raise LLMGenerationIncomplete("continuation_limit")
        logger.info("LLM answer continuation attempt=%d", attempt + 1)
    raise LLMGenerationIncomplete("continuation_limit")
