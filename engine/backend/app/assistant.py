"""How the assistant presents itself. Three optional files, engine defaults for the rest.

    config/identity.md      who the assistant is and what it is careful about
    config/assistant.yaml   UI copy and the fixed replies
    config/routing.yaml     regex short-circuits for the router

None of them is required. Absent or empty, the defaults below apply and the
system answers over whatever was ingested from data/raw.

The prompts themselves are not configurable. They live in app/prompts/ and carry
the citation protocol, which is a contract with citations.py and
agent_output.py — a domain that could rewrite it could break provenance without
anything failing. What a domain legitimately changes is the identity, and that
is injected into every prompt at {identity}.

Everything is cached: editing a file takes effect on restart.
"""

import functools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_NAMES = ("answer", "condense", "router", "summarize", "agent")

DEFAULT_IDENTITY = (
    "You are a documentation assistant for the documents in this knowledge base.\n"
    "You answer questions about them for the people who work with them, using\n"
    "exclusively what those documents say."
)

# Shown in the browser. The frontend carries no copy of its own: everything a
# reader sees around the answer comes from here or from config/assistant.yaml.
DEFAULT_UI = {
    "name": "verifera",
    "title": "Document Assistant",
    "description": (
        "Grounded question answering over your documents. Every claim points "
        "back to the exact passage it came from."
    ),
    "locale": "en",
    "heading": "Document Assistant",
    "tagline": "Ask about your documents — every answer cites the passage it came from.",
    "placeholder": "Ask a question…",
    "suggestions": [],
}

# Emitted by the system in its own voice, so they follow the assistant's locale.
DEFAULT_MESSAGES = {
    "no_context": (
        "The available documentation does not contain information to answer this question."
    ),
    "agent_failed": "The in-depth path did not complete; falling back to a quick search.",
    "no_answer": "I could not produce a useful answer from the documents I consulted.",
}


class ConfigError(RuntimeError):
    """A configuration file exists but is malformed. Absence is never an error."""


@dataclass(frozen=True)
class RoutingSignal:
    name: str
    path: str  # "rag" | "agent"
    pattern: re.Pattern[str]


def _read(name: str) -> str | None:
    """Contents of an optional config file, or None when it is absent or empty."""
    path = settings.config_dir / name
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


@functools.lru_cache(maxsize=1)
def identity() -> str:
    return _read("identity.md") or DEFAULT_IDENTITY


@functools.lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    raw = _read("assistant.yaml")
    if raw is None:
        return {}
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ConfigError(f"assistant.yaml must be a mapping, got {type(data).__name__}")
    return data


@functools.lru_cache(maxsize=len(PROMPT_NAMES))
def _prompt_text(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def prompt(name: str, **values: object) -> str:
    """System prompt `name`, with {identity} and any {placeholders} filled in.

    Substitution is a plain replace rather than str.format because prompts
    legitimately contain JSON braces, which format() would try to interpret.
    """
    text = _prompt_text(name)
    for key, value in {"identity": identity(), **values}.items():
        text = text.replace("{" + key + "}", str(value))
    return text


@functools.lru_cache(maxsize=1)
def routing_signals() -> tuple[RoutingSignal, ...]:
    """Regex short-circuits from config/routing.yaml, in declaration order.

    Pure optimisation: with no file every question goes to prompts/router.md.
    Patterns are written as folded YAML scalars for readability, so the line
    breaks they pick up have to come back out before compiling.
    """
    raw = _read("routing.yaml")
    if raw is None:
        return ()
    data = yaml.safe_load(raw) or {}
    signals = []
    for entry in data.get("signals", []):
        try:
            pattern = re.compile(re.sub(r"\s*\n\s*", "", entry["pattern"]), re.IGNORECASE)
        except (KeyError, TypeError, re.error) as error:
            raise ConfigError(
                f"invalid routing signal {entry.get('name', '?')}: {error}"
            ) from error
        signals.append(RoutingSignal(name=entry["name"], path=entry["path"], pattern=pattern))
    return tuple(signals)


def message(key: str) -> str:
    """Fixed user-facing reply, in the assistant's locale."""
    text = _config().get("messages", {}).get(key) or DEFAULT_MESSAGES[key]
    return " ".join(text.split())


def ui() -> dict[str, Any]:
    """UI copy served to the frontend by GET /api/assistant."""
    data = _config()
    return {
        **DEFAULT_UI,
        **{key: data[key] for key in ("name", "title", "description", "locale") if key in data},
        **(data.get("ui") or {}),
    }


def check() -> None:
    """Fail at startup rather than on the first query. Missing files are fine."""
    _config()
    routing_signals()
    identity()
    for name in PROMPT_NAMES:
        _prompt_text(name)


def reset() -> None:
    """Drop every cached view together — for tests, which move config_dir."""
    for cached in (identity, _config, _prompt_text, routing_signals):
        cached.cache_clear()
