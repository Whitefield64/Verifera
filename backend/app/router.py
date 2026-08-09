"""Adaptive router: strong regex signals short-circuit, a small LLM classifies the rest.

Simple single-document lookups stay on the fast RAG path; comparisons,
multi-document synthesis and structured/tabular lookups go to the agent path.
Structured lookups also escalate the agent to a larger model, because that is
the class where picking the wrong row produces a confident wrong answer.

Both the signals and the classifier prompt come from the domain pack: this
module decides *how* to route, never *what* the domain looks like.
"""

from dataclasses import asdict, dataclass

from app import llm, pack
from app.config import settings

CLASSIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "enum": ["rag", "agent"]},
        "needs_deep_reasoning": {"type": "boolean"},
    },
    "required": ["path", "needs_deep_reasoning"],
    "additionalProperties": False,
}


@dataclass
class RouteDecision:
    path: str  # "rag" | "agent"
    escalate: bool  # larger model, only for structured/tabular lookups
    method: str  # what decided: "signal:…", "classifier" or "fallback:error"

    def as_meta(self) -> dict:
        return asdict(self)


def route_by_signals(query: str) -> RouteDecision | None:
    for signal in pack.routing_signals():
        if signal.pattern.search(query):
            return RouteDecision(signal.path, signal.escalate, f"signal:{signal.name}")
    return None


def route(query: str) -> RouteDecision:
    decision = route_by_signals(query)
    if decision is not None:
        return decision
    try:
        result = llm.complete_json(
            pack.prompt("router"),
            [{"role": "user", "content": query}],
            "route_decision",
            CLASSIFIER_SCHEMA,
            model=settings.utility_model,
        )
        return RouteDecision(
            path=result["path"],
            escalate=result["path"] == "agent" and result["needs_deep_reasoning"],
            method="classifier",
        )
    except Exception:  # the router must never block an answer
        return RouteDecision("rag", escalate=False, method="fallback:error")
