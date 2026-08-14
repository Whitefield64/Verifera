"""Chat entry points over the compiled graph.

Two shapes of the same run: a generator of (event, payload) tuples for the SSE
endpoint, and a single response for the plain JSON endpoint. The JSON endpoint
consumes the generator rather than taking a separate route, so the evaluation
harness exercises the code path the web app uses.
"""

from collections.abc import Iterator
from typing import Any

from app import graph as graph_module


def chat_stream(compiled, message: str, history: list[dict[str, str]]) -> Iterator[tuple[str, dict[str, Any]]]:
    yield from graph_module.stream(compiled, message, history)


def chat(compiled, message: str, history: list[dict[str, str]]) -> dict[str, Any]:
    for event, data in chat_stream(compiled, message, history):
        if event == "done":
            return data
    raise RuntimeError("chat_stream ended without a done event")
