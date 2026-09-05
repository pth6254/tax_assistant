"""LangChain composition above provider-neutral callables (no model SDKs)."""
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompt_values import ChatPromptValue
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableGenerator, RunnableLambda
from pydantic import BaseModel

Result = TypeVar("Result", bound=BaseModel)


def chat_prompt(system: str, user_template: str, *, history: bool = False) -> ChatPromptTemplate:
    # The system text is literal: JSON examples must not become template variables.
    parts = [SystemMessage(content=system)]
    if history:
        parts.append(MessagesPlaceholder("history"))
    parts.append(("human", user_template))
    return ChatPromptTemplate.from_messages(parts)


def to_provider_messages(value: ChatPromptValue) -> list[dict]:
    roles = {"system": "system", "human": "user", "ai": "assistant"}
    return [{"role": roles[m.type], "content": m.content} for m in value.messages]


def strict_json_text(raw: str | dict) -> str:
    """Reject incomplete JSON before LangChain's permissive JSON parser sees it."""
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    text = raw.split("</think>")[-1].strip()
    fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected a complete JSON object")
    return json.dumps(data, ensure_ascii=False)


def output_parser(model: type[Result]):
    return (
        RunnableLambda(strict_json_text, name="validate_complete_json")
        | PydanticOutputParser(pydantic_object=model)
    ).with_config(run_name=f"validate_{model.__name__}")


def text_chain(
    prompt: ChatPromptTemplate,
    complete: Callable[[list[dict]], Awaitable[str | dict]],
    *, name: str,
):
    return (
        prompt.with_config(run_name=f"{name}_prompt")
        | RunnableLambda(to_provider_messages, name="provider_messages")
        | RunnableLambda(complete, name=f"{name}_generate")
    ).with_config(run_name=name, tags=["tax-assistant"], metadata={"prompt_version": "1"})


def structured_chain(prompt, generate, model: type[Result], *, name: str):
    # generate may call the existing native JSON-schema API and return a dict.
    return (text_chain(prompt, generate, name=name) | output_parser(model)).with_config(
        run_name=name, tags=["tax-assistant"], metadata={"prompt_version": "1"},
    )


def streaming_chain(
    prompt: ChatPromptTemplate,
    stream: Callable[[list[dict]], AsyncIterator[str]],
    *, name: str,
):
    async def generate(inputs: AsyncIterator[list[dict]]) -> AsyncIterator[str]:
        async for messages in inputs:
            async for token in stream(messages):
                yield token

    return (
        prompt.with_config(run_name=f"{name}_prompt")
        | RunnableLambda(to_provider_messages, name="provider_messages")
        | RunnableGenerator(generate, name=f"{name}_stream")
    ).with_config(run_name=name, tags=["tax-assistant"], metadata={"prompt_version": "1"})
