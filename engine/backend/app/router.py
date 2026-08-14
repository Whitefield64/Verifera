"""Adaptive router: strong regex signals short-circuit, a small LLM classifies the rest.

Simple single-document lookups stay on the fast RAG path; comparisons,
multi-document synthesis and structured/tabular lookups go to the agent path.

The router chooses a path and nothing else. It used to also escalate structured
lookups to a larger model; measured against the same questions the larger model
answered no better, so the whole notion is gone rather than left dormant.

The signals are optional configuration and the classifier prompt belongs to
the engine: this module decides *how* to route, never what the corpus is about.
"""

from dataclasses import asdict, dataclass

from app import assistant, llm
from app.config import settings

CLASSIFIER_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string", "enum": ["rag", "agent"]}},
    "required": ["path"],
    "additionalProperties": False,
}


@dataclass
class RouteDecision:
    path: str  # "rag" | "agent"
    method: str  # what decided: "signal:…", "classifier" or "fallback:error"

    def as_meta(self) -> dict:
        return asdict(self)


def route_by_signals(query: str) -> RouteDecision | None:
    for signal in assistant.routing_signals():
        if signal.pattern.search(query):
            return RouteDecision(signal.path, f"signal:{signal.name}")
    return None


def route(query: str) -> RouteDecision:
    decision = route_by_signals(query)
    if decision is not None:
        return decision
    try:
        result = llm.complete_json(
            assistant.prompt("router"),
            [{"role": "user", "content": query}],
            "route_decision",
            CLASSIFIER_SCHEMA,
            model=settings.utility_model,
        )
        return RouteDecision(path=result["path"], method="classifier")
    except Exception:  # the router must never block an answer
        return RouteDecision("rag", method="fallback:error")
