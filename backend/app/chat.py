"""Query orchestration: condense follow-ups once, route, dispatch.

The router classifies every query and its decision is always reported in the
response meta. The agent path is not wired yet, so agent-classified queries are
answered on the RAG path — which means the routing accuracy can already be
measured against the evaluation set independently of the agent.
"""

from collections.abc import Iterator
from typing import Any

from psycopg_pool import ConnectionPool

from app import rag, router


def _with_router_meta(
    events: Iterator[tuple[str, dict[str, Any]]], decision: router.RouteDecision
) -> Iterator[tuple[str, dict[str, Any]]]:
    for event, data in events:
        if event == "done":
            data["meta"]["router"] = decision.as_meta()
        yield event, data


def chat_stream(
    pool: ConnectionPool, message: str, history: list[dict[str, str]]
) -> Iterator[tuple[str, dict[str, Any]]]:
    query = rag.condense_query(message, history) if history else message
    decision = router.route(query)
    yield from _with_router_meta(rag.chat_stream(pool, message, history, query=query), decision)


def chat(pool: ConnectionPool, message: str, history: list[dict[str, str]]) -> dict[str, Any]:
    for event, data in chat_stream(pool, message, history):
        if event == "done":
            return data
    raise RuntimeError("chat_stream ended without a done event")
