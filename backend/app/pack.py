"""Domain pack loader: the vertical lives in packs/<name>/ as data, not in code.

Nothing under app/ may contain a domain string. Prompts, routing signals, UI
copy and the evaluation topic list all come from the directory named by
PACK_DIR, so retargeting the system at another corpus is a config change and a
new pack directory — no Python edits.

Everything is cached: editing a pack file takes effect on restart.
"""

import functools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

REQUIRED_PROMPTS = ("answer", "condense", "router", "summarize", "agent")


class PackError(RuntimeError):
    """The pack is missing or malformed. Always fatal: there is no sane default."""


@dataclass(frozen=True)
class RoutingSignal:
    name: str
    path: str  # "rag" | "agent"
    escalate: bool
    pattern: re.Pattern[str]


def _read(path: Path) -> str:
    if not path.is_file():
        raise PackError(f"pack file missing: {path}")
    return path.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def manifest() -> dict[str, Any]:
    """Contents of pack.yaml."""
    data = yaml.safe_load(_read(settings.pack_dir / "pack.yaml"))
    if not isinstance(data, dict):
        raise PackError(f"pack.yaml must be a mapping, got {type(data).__name__}")
    for key in ("name", "title", "domains"):
        if key not in data:
            raise PackError(f"pack.yaml is missing required key: {key}")
    return data


@functools.lru_cache(maxsize=len(REQUIRED_PROMPTS) + 4)
def _prompt_text(name: str) -> str:
    return _read(settings.pack_dir / "prompts" / f"{name}.md").strip()


def prompt(name: str, **values: object) -> str:
    """System prompt `name`, with {placeholders} filled in.

    Substitution is a plain replace rather than str.format because prompts
    legitimately contain JSON braces, which format() would try to interpret.
    """
    text = _prompt_text(name)
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


@functools.lru_cache(maxsize=1)
def routing_signals() -> tuple[RoutingSignal, ...]:
    """Regex short-circuits from router.yaml, in declaration order.

    Patterns are written as folded YAML scalars for readability, so the line
    breaks they pick up have to come back out before compiling.
    """
    data = yaml.safe_load(_read(settings.pack_dir / "router.yaml")) or {}
    signals = []
    for raw in data.get("signals", []):
        try:
            pattern = re.compile(re.sub(r"\s*\n\s*", "", raw["pattern"]), re.IGNORECASE)
        except (KeyError, re.error) as error:
            raise PackError(f"invalid routing signal {raw.get('name', '?')}: {error}") from error
        signals.append(
            RoutingSignal(
                name=raw["name"],
                path=raw["path"],
                escalate=bool(raw.get("escalate", False)),
                pattern=pattern,
            )
        )
    return tuple(signals)


def message(key: str) -> str:
    """Fixed user-facing reply from pack.yaml, in the pack's locale."""
    try:
        return " ".join(manifest()["messages"][key].split())
    except KeyError as error:
        raise PackError(f"pack.yaml is missing messages.{key}") from error


def ui() -> dict[str, Any]:
    """UI copy served to the frontend by GET /api/pack."""
    data = manifest()
    return {
        "name": data["name"],
        "title": data["title"],
        "description": data.get("description", ""),
        "locale": data.get("locale", "en"),
        **data.get("ui", {}),
    }


def check() -> None:
    """Fail fast at startup rather than on the first user query."""
    manifest()
    routing_signals()
    for name in REQUIRED_PROMPTS:
        _prompt_text(name)
