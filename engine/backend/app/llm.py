"""Provider layer: chat models and embeddings.

Chat goes through LangChain, so the graph, the router and the ingestion
summariser share one interface and structured output does not depend on a
single vendor's JSON-schema extension.

Embeddings stay on the OpenAI client. They are batched and token-truncated
against an index whose width is fixed at schema-creation time; wrapping that in
another abstraction buys nothing and risks the index.
"""

import json
import time
from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Any

import tiktoken
from langchain_openai import ChatOpenAI
from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None
_encoding = tiktoken.get_encoding("cl100k_base")

EMBED_TOKEN_LIMIT = 8000


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key, timeout=60.0)
    return _client


@lru_cache(maxsize=8)
def chat_model(model: str | None = None, reasoning: bool = False) -> ChatOpenAI:
    # Passing `reasoning` switches langchain to the Responses API, the only one
    # that returns the model's reasoning at all. The effort has to be explicit:
    # with `summary` alone the default is off, 0 reasoning tokens and no summary
    # block ever comes back. `low` because effort is bought by the second: one
    # agent query measured 12.8s/1.3k output tokens with no reasoning, 17.6s/1.7k
    # at low, 54s/7.1k at medium — for the same answer and the same 7 citations.
    extra: dict[str, Any] = (
        {
            "reasoning": {"effort": "low", "summary": "auto"},
            "output_version": "responses/v1",
        }
        if reasoning
        else {}
    )
    return ChatOpenAI(
        model=model or settings.chat_model,
        api_key=settings.openai_api_key,
        timeout=60.0,
        max_retries=2,
        stream_usage=True,  # token counts arrive on the final streamed chunk
        **extra,
    )


def add_usage(total: dict[str, int], message: Any) -> dict[str, int]:
    """Accumulate a response's token usage. Reporting cost per query is only
    possible if every call on the path contributes."""
    usage = getattr(message, "usage_metadata", None) or {}
    for key in ("input_tokens", "output_tokens"):
        if value := usage.get(key):
            total[key] = total.get(key, 0) + value
    return total


def _json_format(schema_name: str, schema: dict) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {"name": schema_name, "strict": True, "schema": schema},
    }


def _with_retry(call: Callable[[], Any], attempts: int = 3) -> Any:
    for attempt in range(attempts):
        try:
            return call()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2**attempt)


def _truncate(text: str, limit: int = EMBED_TOKEN_LIMIT) -> str:
    tokens = _encoding.encode(text)
    if len(tokens) <= limit:
        return text
    return _encoding.decode(tokens[:limit])


def embed(texts: list[str], batch_size: int = 96) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = [_truncate(t) for t in texts[start : start + batch_size]]
        response = _with_retry(
            lambda batch=batch: client().embeddings.create(
                model=settings.embed_model, input=batch
            )
        )
        vectors.extend(item.embedding for item in response.data)
    return vectors


def complete_text(
    system: str, messages: list[dict[str, str]], model: str | None = None
) -> str:
    response = chat_model(model).invoke([{"role": "system", "content": system}, *messages])
    return (text_of(response) or "").strip()


def complete_json(
    system: str,
    messages: list[dict[str, str]],
    schema_name: str,
    schema: dict,
    model: str | None = None,
) -> dict:
    response = chat_model(model).bind(response_format=_json_format(schema_name, schema)).invoke(
        [{"role": "system", "content": system}, *messages]
    )
    return json.loads(text_of(response) or "{}")


def stream_json(
    system: str,
    messages: list[dict[str, str]],
    schema_name: str,
    schema: dict,
    model: str | None = None,
    usage: dict[str, int] | None = None,
) -> Iterator[str]:
    """Yield raw content deltas of a structured completion.

    Deliberately not with_structured_output: that hands back the parsed object
    once it is complete, and the answer has to reach the user token by token.
    Callers reassemble the field they care about from the partial JSON.
    """
    stream = chat_model(model).bind(response_format=_json_format(schema_name, schema)).stream(
        [{"role": "system", "content": system}, *messages]
    )
    for chunk in stream:
        if usage is not None:
            add_usage(usage, chunk)
        text = text_of(chunk)
        if text:
            yield text


def text_of(message: Any) -> str:
    """Plain text of a message, whether the provider returned a string or blocks."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return ""
