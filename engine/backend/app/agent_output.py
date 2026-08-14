"""Parsing the agent's final turn into an answer plus structured citations.

The agent writes free markdown, a marker, then a small JSON block holding only
the citations. Putting the whole answer inside a JSON string instead would make
the model hand-escape every newline of a long, structured answer — fragile
exactly where answers are richest. Only the short quotes need escaping here.

Older or confused turns are still salvaged rather than shown as raw JSON.
"""

import json
import re
from typing import Any

from app import citations
from app import workspace_layout as layout

# Shared with the agent prompt, which interpolates it: the writer and the
# reader of this marker must never drift apart.
SOURCES_MARKER = "---SOURCES---"

# Asking for the half of the format that went missing. Lives next to the marker
# for the same reason the marker does: the words that request this block and the
# code that parses it must not drift apart. Protocol, not content — it says
# nothing about what the documents contain.
# It restates the shape instead of pointing at it. The premise of asking at all
# is that the model did not follow the format it was already given, so a nudge
# that only names it repeats the failure: asked without the example, the model
# emitted the marker and then prose, and every citation was still lost.
MISSING_SOURCES_NUDGE = f"""Your answer above is complete and will be kept exactly as written. Do not repeat or revise it.

It is missing its sources block. Reply with ONLY these two things and nothing else:

{SOURCES_MARKER}
```json
{{"citations": [{{"chunk_id": "<a chunk_id you referenced above>", "quote": "<sentence copied verbatim from that chunk>"}}]}}
```

One entry for every chunk_id you referenced in the answer. Each quote must be copied word for word from that chunk's text; a paraphrase is rejected."""

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_FENCE = re.compile(r"```(?:json)?")
# Tolerant of extra dashes and spaces, but not of other wordings: an answer that
# legitimately discusses "sources" in its prose must not be cut in half.
_MARKER = re.compile(r"\n-{3,}\s*SOURCES\s*-{3,}\s*\n", re.IGNORECASE)
# Chunk references the model sometimes leaves in prose despite instructions.
# The live citations travel in the citations array; in the chat they are noise.
# Brackets are consumed on BOTH sides (ASCII, CJK and guillemets, for defence in
# depth) and replaced with a single space, so the words either side of a removed
# reference do not weld together.
_INLINE_CHUNK_REF = re.compile(
    rf"[\s\(\[\{{【〔「『《〈«]*{layout.CHUNK_REF}"
    rf"(?:,\s*{layout.CHUNK_REF})*[\s\)\]\}}】〕」』》〉»]*"
)
_DOUBLE_SPACE = re.compile(r" {2,}")


def strip_inline_chunk_refs(text: str) -> str:
    # Bracketed leftovers first, and by a looser rule than the canonical id:
    # cleanup must be more permissive than matching, or a reference the model
    # nearly got right slips between the two and lands on the reader's screen.
    text = citations.UNRESOLVED_REF.sub(" ", text)
    return _DOUBLE_SPACE.sub(" ", _INLINE_CHUNK_REF.sub(" ", text)).strip()


def balanced_json_objects(text: str) -> list[str]:
    """Top-level {...} spans found by brace scanning (string-aware)."""
    spans: list[str] = []
    depth, start, in_string, escaped = 0, -1, False, False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"' and depth > 0:
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append(text[start : index + 1])
    return spans


def _json_candidates(text: str) -> list[str]:
    fenced = [match.group(1) for match in _JSON_BLOCK.finditer(text)]
    return fenced or balanced_json_objects(text)


def _strip_code_fences(text: str) -> str:
    return _BARE_FENCE.sub("", _JSON_BLOCK.sub("", text))


def _single_block_payload(text: str) -> dict[str, Any] | None:
    """A whole turn wrapped in one ```json {"answer", "citations"}``` block."""
    for candidate in reversed(_json_candidates(text)):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("answer"), str):
            return payload
    return None


def _extract_citations(tail: str) -> list[dict[str, Any]]:
    for candidate in reversed(_json_candidates(tail)):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("citations"), list):
            return payload["citations"]
    return []


def has_sources_block(text: str) -> bool:
    """Whether the final turn carries the citations half of its contract."""
    return bool(_MARKER.search(text)) or bool(_extract_citations(text))


def extract(text: str) -> tuple[str, list[dict[str, Any]], str]:
    """Split the agent's final text into (answer_markdown, raw_citations, method).

    Falls back from the marker format to a single JSON block, then to the raw
    text stripped of stray fences — so a confused turn still reaches the user as
    prose rather than as un-rendered JSON syntax.
    """
    match = _MARKER.search(text)
    if match:
        answer = _strip_code_fences(text[: match.start()]).strip()
        if answer:
            return answer, _extract_citations(text[match.end() :]), "marker"
    single = _single_block_payload(text)
    if single is not None:
        return single["answer"].strip(), single.get("citations") or [], "single_block"
    # No marker is not the same as no citations: the model sometimes writes the
    # JSON block and drops only the line above it. Looking for the block anyway
    # costs nothing and saves every citation in the answer.
    return _strip_code_fences(text).strip(), _extract_citations(text), "raw"
