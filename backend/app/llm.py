"""Thin wrapper around the OpenAI API (embeddings + chat).

Callers pass the model explicitly or fall back to settings.chat_model, so
utility calls (routing, condensing) can run on a cheaper model than answers.
"""

import json
import time
from collections.abc import Callable
from typing import Any

import tiktoken
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
    response = _with_retry(
        lambda: client().chat.completions.create(
            model=model or settings.chat_model,
            messages=[{"role": "system", "content": system}, *messages],
        )
    )
    return (response.choices[0].message.content or "").strip()


def complete_json(
    system: str,
    messages: list[dict[str, str]],
    schema_name: str,
    schema: dict,
    model: str | None = None,
) -> dict:
    response = _with_retry(
        lambda: client().chat.completions.create(
            model=model or settings.chat_model,
            messages=[{"role": "system", "content": system}, *messages],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        )
    )
    return json.loads(response.choices[0].message.content or "{}")


def stream_json(
    system: str, messages: list[dict[str, str]], schema_name: str, schema: dict
):
    """Yield raw content deltas of a structured-output completion (retry covers only the connect)."""
    stream = _with_retry(
        lambda: client().chat.completions.create(
            model=settings.chat_model,
            messages=[{"role": "system", "content": system}, *messages],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            stream=True,
        )
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
