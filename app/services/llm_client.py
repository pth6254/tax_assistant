"""app/services/llm_client.py — LLM 호출 어댑터.

chat_service.py가 특정 LLM SDK(Ollama 전용 httpx 클라이언트)에 직접 의존하지 않도록
LangChain의 ChatOllama로 감싼다. provider를 vLLM(OpenAI 호환 서버)이나 다른 모델로
바꿀 때 이 파일의 _build_client()만 교체하면 되고, chat_service.py는 그대로 둔다.

Ollama 고유 옵션 배치 규칙(과거 실측으로 확인된 버그)을 그대로 따른다:
- think(reasoning)/keep_alive는 요청 최상위 필드 — options 안에 넣으면 무시됨
- num_ctx는 모든 호출에서 동일한 값을 사용해야 함 — 다르면 Ollama가 모델을 리로드해
  호출당 4~10초가 추가됨
"""
import json
from typing import AsyncGenerator

from langchain_ollama import ChatOllama

from config import CHAT_MODEL, OLLAMA_BASE_URL, OLLAMA_KEEP_ALIVE, OLLAMA_NUM_CTX, THINK_ENABLED


def _build_client(temperature: float, num_predict: int, schema: dict | None = None) -> ChatOllama:
    return ChatOllama(
        model=CHAT_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
        num_predict=num_predict,
        num_ctx=OLLAMA_NUM_CTX,
        keep_alive=OLLAMA_KEEP_ALIVE,
        reasoning=THINK_ENABLED,
        format=schema,
    )


async def close_llm_client() -> None:
    """앱 종료 시 LLM 클라이언트 정리 훅.

    ChatOllama는 호출마다 자체 클라이언트를 관리하므로 현재는 no-op이지만,
    provider를 교체해 명시적 정리(aclose 등)가 필요해지면 여기서 수행한다 —
    호출부(main.py lifespan, eval_rag.py)는 그대로 유지된다.
    """
    return


async def call_llm(
    messages: list[dict],
    temperature: float = 0.3,
    num_predict: int = -1,
) -> str:
    """비스트리밍 LLM 호출. messages는 {"role", "content"} dict 목록."""
    client = _build_client(temperature, num_predict)
    result = await client.ainvoke(messages)
    return result.content


async def call_llm_structured(
    messages: list[dict],
    schema: dict,
    temperature: float = 0.0,
    num_predict: int = -1,
) -> dict:
    """JSON Schema로 출력 형식을 강제하는 비스트리밍 호출 (constrained decoding).

    프롬프트 지시("JSON만 출력하라")와 달리 디코딩 단계에서 스키마를 강제하므로
    형식 이탈이 원천적으로 불가능하다. Ollama의 format 파라미터를 사용하며,
    OpenAI 호환 provider(vLLM 등)로 바꿀 때는 response_format으로 대응된다.
    """
    client = _build_client(temperature, num_predict, schema=schema)
    result = await client.ainvoke(messages)
    return json.loads(result.content)


async def stream_llm(
    messages: list[dict],
    temperature: float = 0.3,
    num_predict: int = -1,
) -> AsyncGenerator[str, None]:
    """스트리밍 LLM 호출. raw 텍스트 조각을 순서대로 yield한다 (<think> 태그 포함 여부는 provider 그대로)."""
    client = _build_client(temperature, num_predict)
    async for chunk in client.astream(messages):
        if chunk.content:
            yield chunk.content
