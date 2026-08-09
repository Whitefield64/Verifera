"""Query orchestration as a graph.

                     ┌── rag ──→ retrieve → generate ──┐
    condense → route ┤                                 ├→ finalize → END
                     └── agent ──→ agent ⇄ tools ──────┘
                                     │
                                     └─(failure)→ retrieve

Everything domain-specific comes from the pack; everything provider-specific
from app.llm. This module owns only the shape of the work: what runs, in what
order, and what the caller sees while it runs.

Progress reaches the caller through the graph's custom stream, as the same
(event, payload) tuples the HTTP layer turns into SSE frames, so the transport
contract did not change when the orchestration did.
"""

import json
import logging
import os
from collections.abc import Iterator
from functools import lru_cache
from time import monotonic
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from psycopg_pool import ConnectionPool

from app import agent_output, citations, llm, pack, rag, retrieval, router, tools
from app import workspace_layout as layout
from app.config import settings

logger = logging.getLogger(__name__)

# A tool result is a message to a model, not a database dump.
TOOL_RESULT_CAP = 24_000


def _union(left: list[str], right: list[str]) -> list[str]:
    return sorted(set(left) | set(right))


def _add_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    return {key: left.get(key, 0) + right.get(key, 0) for key in set(left) | set(right)}


class ChatState(TypedDict, total=False):
    # input
    message: str
    history: list[dict[str, str]]
    # routing
    query: str
    route: dict[str, Any]
    escalate: bool
    path: str
    # rag path
    chunks: list[retrieval.RetrievedChunk]
    raw_citations: list[dict[str, Any]]
    # agent path
    messages: Annotated[list[AnyMessage], add_messages]
    seen_chunk_ids: Annotated[list[str], _union]
    tool_calls: int
    agent_error: str
    usage: Annotated[dict[str, int], _add_usage]
    # output
    answer: str
    citations: list[dict[str, Any]]
    meta: dict[str, Any]
    started: float
    model: str


def tool_event(name: str, args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """A structured preview of one tool call, for the activity trail.

    The UI shows people what the agent is doing; handing it raw JSON would be
    the same as showing nothing.
    """
    if error := result.get("error"):
        return {"name": name, "title": _tool_title(name, args), "summary": f"error: {error}", "items": []}
    if name == "semantic_search":
        results = result.get("results") or []
        items = [
            f"{r['doc_id']}" + (f" · p.{r['page']}" if r.get("page") else "")
            + (f" · {r['section_title']}" if r.get("section_title") else "")
            for r in results[:6]
        ]
        return {"name": name, "title": _tool_title(name, args), "summary": f"{len(results)} results", "items": items}
    if name == "get_document_metadata":
        sections = result.get("sections") or []
        return {
            "name": name,
            "title": _tool_title(name, args),
            "summary": f"{len(sections)} sections, {len(result.get('tables') or [])} tables",
            "items": [s["title"] for s in sections[:6]],
        }
    if name == "read_document_section":
        citable = result.get("citable_chunks")
        summary = (
            f"{len(citable)} citable chunks for the table"
            if citable is not None
            else f"{len(result.get('content') or '')} characters read"
        )
        return {"name": name, "title": _tool_title(name, args), "summary": summary, "items": []}
    return {"name": name, "title": _tool_title(name, args), "summary": "done", "items": []}


def _tool_title(name: str, args: dict[str, Any]) -> str:
    if name == "semantic_search":
        return f"«{args.get('query', '')}»"
    doc_id = str(args.get("doc_id", ""))
    path = args.get("path")
    return f"{doc_id} · {path}" if path else doc_id


def _agent_seed(query: str) -> str:
    index_path = settings.workspace_dir / layout.INDEX_FILE
    catalogue = index_path.read_text(encoding="utf-8") if index_path.is_file() else ""
    return f"Knowledge base index:\n\n{catalogue}\n\nQuestion: {query}"


def build(pool: ConnectionPool):
    """Compile the graph. The pool is captured here rather than carried in the
    state: it is a process resource, not part of a conversation."""

    hard_cap = settings.agent_max_tool_calls + settings.agent_hard_cap_extra

    def condense(state: ChatState) -> dict[str, Any]:
        query = (
            rag.condense_query(state["message"], state["history"])
            if state.get("history")
            else state["message"]
        )
        return {"query": query, "started": monotonic()}

    def route(state: ChatState) -> dict[str, Any]:
        decision = router.route(state["query"])
        return {"route": decision.as_meta(), "escalate": decision.escalate, "path": decision.path}

    def retrieve(state: ChatState) -> dict[str, Any]:
        query_vector = llm.embed([state["query"]])[0]
        with pool.connection() as conn:
            chunks = retrieval.hybrid_search(conn, state["query"], query_vector)
        return {"chunks": chunks}

    def generate(state: ChatState) -> dict[str, Any]:
        write = get_stream_writer()
        chunks = state.get("chunks") or []
        if not chunks:
            answer = pack.message("no_context")
            write(("delta", {"text": answer}))
            return {"answer": answer, "raw_citations": [], "model": settings.chat_model}

        user_message = (
            f"Knowledge base extracts:\n\n{rag.format_context(chunks)}\n\n"
            f"Question: {state['message']}"
        )
        buffer, emitted, usage = "", 0, {}
        for piece in llm.stream_json(
            pack.prompt("answer"),
            [*rag.trimmed_history(state.get("history") or []),
             {"role": "user", "content": user_message}],
            "rag_answer",
            rag.ANSWER_SCHEMA,
            usage=usage,
        ):
            buffer += piece
            so_far = rag.partial_answer(buffer)
            if len(so_far) > emitted:
                write(("delta", {"text": so_far[emitted:]}))
                emitted = len(so_far)
        raw = json.loads(buffer or "{}")
        return {
            "answer": raw.get("answer", "").strip() or pack.message("no_context"),
            "raw_citations": raw.get("citations") or [],
            "model": settings.chat_model,
            "usage": usage,
        }

    def agent(state: ChatState) -> dict[str, Any]:
        write = get_stream_writer()
        model_name = (
            settings.agent_escalation_model if state.get("escalate") else settings.agent_model
        )
        system = pack.prompt(
            "agent",
            max_tool_calls=settings.agent_max_tool_calls,
            sources_marker=agent_output.SOURCES_MARKER,
        )

        history = list(state.get("messages") or [])
        updates: list[AnyMessage] = []
        if not history:
            seed = HumanMessage(_agent_seed(state["query"]))
            history, updates = [seed], [seed]

        # Past the call budget or the wall clock the model answers with what it
        # has: taking the tools away is a firmer instruction than asking.
        spent = state.get("tool_calls", 0)
        out_of_time = monotonic() - state.get("started", monotonic()) > settings.agent_timeout_s
        model = llm.chat_model(model_name)
        if spent < hard_cap and not out_of_time:
            model = model.bind_tools(tools.SCHEMAS)

        try:
            response = model.invoke([SystemMessage(system), *history])
        except Exception as error:  # noqa: BLE001 — any model failure falls back to RAG
            logger.warning("agent step failed, falling back to RAG: %s", error)
            write(("thinking", {"text": pack.message("agent_failed")}))
            return {"agent_error": str(error)}

        if reasoning := _reasoning_of(response):
            write(("thinking", {"text": reasoning}))
        return {
            "messages": [*updates, response],
            "model": model_name,
            "usage": llm.add_usage({}, response),
        }

    def run_tools(state: ChatState) -> dict[str, Any]:
        write = get_stream_writer()
        requested = getattr(state["messages"][-1], "tool_calls", None) or []
        run = tools.ToolRun(
            pool=pool,
            seen_chunk_ids=set(state.get("seen_chunk_ids") or []),
            calls=state.get("tool_calls", 0),
        )
        replies: list[AnyMessage] = []
        for call in requested:
            result = tools.call(run, call["name"], call["args"] or {})
            write(("tool", tool_event(call["name"], call["args"] or {}, result)))
            replies.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False)[:TOOL_RESULT_CAP],
                    tool_call_id=call["id"],
                    name=call["name"],
                )
            )
        return {
            "messages": replies,
            "seen_chunk_ids": sorted(run.seen_chunk_ids),
            "tool_calls": run.calls,
        }

    def finalize(state: ChatState) -> dict[str, Any]:
        if state.get("path") == "agent" and not state.get("agent_error"):
            return _finalize_agent(pool, state)
        return _finalize_rag(state)

    def after_route(state: ChatState) -> str:
        return "agent" if state.get("path") == "agent" else "retrieve"

    def after_agent(state: ChatState) -> str:
        if state.get("agent_error"):
            return "retrieve"  # the endpoint never depends on the agent's health
        return "tools" if getattr(state["messages"][-1], "tool_calls", None) else "finalize"

    graph = StateGraph(ChatState)
    graph.add_node("condense", condense)
    graph.add_node("route", route)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_node("agent", agent)
    graph.add_node("tools", run_tools)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "condense")
    graph.add_edge("condense", "route")
    graph.add_conditional_edges("route", after_route, {"retrieve": "retrieve", "agent": "agent"})
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "finalize")
    graph.add_conditional_edges(
        "agent", after_agent, {"tools": "tools", "retrieve": "retrieve", "finalize": "finalize"}
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", END)
    return graph.compile(name="chat")


def _reasoning_of(response: Any) -> str:
    """Reasoning summaries, when the provider exposes them."""
    content = getattr(response, "content", None)
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("summary") or block.get("reasoning") or ""
        for block in content
        if isinstance(block, dict) and block.get("type") in {"reasoning", "thinking"}
    ]
    return "\n".join(part for part in parts if isinstance(part, str) and part).strip()


def _finalize_rag(state: ChatState) -> dict[str, Any]:
    chunks = state.get("chunks") or []
    built = citations.build_citations(state.get("raw_citations") or [], chunks)
    meta = {
        "model": state.get("model", settings.chat_model),
        "query_used": state.get("query", ""),
        "retrieved_chunk_ids": [chunk.chunk_id for chunk in chunks],
        "elapsed_ms": _elapsed_ms(state),
        "router": state.get("route", {}),
        "usage": state.get("usage", {}),
    }
    if error := state.get("agent_error"):
        meta["agent_fallback_error"] = error
    return {"citations": built, "path": "rag", "meta": meta}


def _finalize_agent(pool: ConnectionPool, state: ChatState) -> dict[str, Any]:
    text = llm.text_of(state["messages"][-1]) if state.get("messages") else ""
    answer, raw, method = agent_output.extract(text)

    # The anti-hallucination rule: an answer may only cite what the tools
    # actually exposed during this run.
    seen = set(state.get("seen_chunk_ids") or [])
    kept = [c for c in raw if isinstance(c, dict) and c.get("chunk_id") in seen]
    answer = agent_output.strip_inline_chunk_refs(answer) or pack.message("no_answer")

    ordered = list(dict.fromkeys(c["chunk_id"] for c in kept))
    with pool.connection() as conn:
        chunks = retrieval.fetch_by_ids(conn, ordered)
    return {
        "answer": answer,
        "citations": citations.build_citations(kept, chunks),
        "path": "agent",
        "meta": {
            "model": state.get("model", settings.agent_model),
            "query_used": state.get("query", ""),
            "elapsed_ms": _elapsed_ms(state),
            "router": state.get("route", {}),
            "tool_calls": state.get("tool_calls", 0),
            "citations_dropped_unseen": len(raw) - len(kept),
            "answer_format": method,
            "usage": state.get("usage", {}),
        },
    }


def _elapsed_ms(state: ChatState) -> int:
    return round((monotonic() - state.get("started", monotonic())) * 1000)


@lru_cache(maxsize=1)
def _callbacks() -> tuple:
    """Langfuse tracing, only when it is configured.

    Off by default and opt-in through the environment: a public reference
    implementation should not require an account with anyone to run. Langfuse
    is self-hostable, so this stays open-source all the way down.
    """
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return ()
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        logger.warning(
            "LANGFUSE_* is set but the tracing extra is not installed "
            "(pip install -r backend/requirements-tracing.txt)"
        )
        return ()
    return (CallbackHandler(),)


def stream(compiled, message: str, history: list[dict[str, str]]) -> Iterator[tuple[str, dict]]:
    """Yield the same (event, payload) tuples the HTTP layer has always emitted."""
    final: dict[str, Any] = {}
    # Every tool call costs two graph steps (agent + tools), plus the fixed
    # nodes and one spare turn to wind up after the budget runs out.
    hard_cap = settings.agent_max_tool_calls + settings.agent_hard_cap_extra
    for mode, payload in compiled.stream(
        {"message": message, "history": history},
        stream_mode=["custom", "values"],
        config={"recursion_limit": 2 * hard_cap + 10, "callbacks": list(_callbacks())},
    ):
        if mode == "custom":
            yield payload
        else:
            final = payload
    yield (
        "done",
        {
            "answer": final.get("answer", ""),
            "citations": final.get("citations", []),
            "path": final.get("path", "rag"),
            "meta": final.get("meta", {}),
        },
    )
