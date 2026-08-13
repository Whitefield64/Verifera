"""Citation contract: normalize LLM citations onto retrieved chunks, verify
quotes, and turn the references the model leaves in its prose into the numbers
the reader sees."""

import re
import unicodedata
from typing import TYPE_CHECKING, Any

from app import corpus_manifest
from app import workspace_layout as layout

if TYPE_CHECKING:
    from app.retrieval import RetrievedChunk

_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_LINK = re.compile(r"\[+([^\]]*)\]+\([^)]*\)")
_CHAR_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)


def normalize(text: str) -> str:
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = unicodedata.normalize("NFKC", text).translate(_CHAR_MAP).lower()
    return _WHITESPACE.sub(" ", text).strip()


def _compact(text: str) -> str:
    """Word characters only: verification must not depend on punctuation or spacing."""
    return re.sub(r"[\W_]+", "", normalize(text))


def quote_is_verified(quote: str, chunk_text: str) -> bool:
    compacted = _compact(quote)
    return bool(compacted) and compacted in _compact(chunk_text)


def build_citations(
    raw_citations: list[dict[str, Any]], retrieved: list["RetrievedChunk"]
) -> list[dict[str, Any]]:
    """Keep only citations pointing at chunks the model actually saw; flag quote fidelity."""
    by_id = {chunk.chunk_id: chunk for chunk in retrieved}
    # The manifest name first: the title ingestion extracts from the content is
    # what the retriever needs, not what a reader wants to see cited.
    titles = corpus_manifest.titles()
    seen: set[tuple[str, str]] = set()
    citations: list[dict[str, Any]] = []
    for item in raw_citations:
        chunk_id = item.get("chunk_id", "")
        quote = (item.get("quote") or "").strip()
        chunk = by_id.get(chunk_id)
        if chunk is None or (chunk_id, quote) in seen:
            continue
        seen.add((chunk_id, quote))
        citations.append(
            {
                "doc_id": chunk.doc_id,
                "title": titles.get(chunk.doc_id) or chunk.title,
                "chunk_id": chunk_id,
                "marker": None,
                "page": chunk.page,
                "bbox": chunk.bbox,
                "bboxes": chunk.bboxes,
                "quote": quote,
                "chunk_text": chunk.text,
                "verified": quote_is_verified(quote, chunk.text),
            }
        )
    return citations


# --- inline references ------------------------------------------------------
#
# The model marks the sentence it is citing with a chunk id in double brackets;
# the reader sees a footnote number. Both halves of that trade live here so they
# cannot drift apart: INLINE_REF_FORMAT is interpolated into the pack's prompts,
# INLINE_REF parses what comes back, and marker() writes what the frontend
# renders. A number is never ambiguous with a reference — the pattern requires a
# digest — so numbering the same text twice is a no-op.

INLINE_REF_FORMAT = "[[<chunk_id>]]"
INLINE_REF = re.compile(rf"\[\[({layout.CHUNK_REF})\]\]")
# A reference the model *attempted* and got wrong: bracketed, not a footnote
# number, and carrying either a '#' or a hex run — a digest one character short,
# a digest with no doc_id. Those match neither INLINE_REF nor the stripper's
# chunk-id pattern, so before this they survived numbering, survived cleanup,
# and reached the reader as a raw id: 2 answers in 40 in the 2026-08-12 run.
# Deliberately not "any double bracket that is not a number" — prose is allowed
# to write [[sic]], and cleanup must not eat what it does not recognise.
UNRESOLVED_REF = re.compile(
    r"\[\[(?!\d+\]\])[^\]\n]*(?:#|[0-9a-f]{8})[^\]\n]*\]\]"
)
_OPEN_REF = "[["
# "[[" + doc_id + "#" + digest + "]]". Generous on the doc_id: the cost of being
# wrong is holding back a line of prose for one frame, not losing it.
_MAX_REF_CHARS = 96


def marker(number: int) -> str:
    return f"[[{number}]]"


def _number_for(numbers: dict[str, int], chunk_id: str) -> int:
    """Same passage, same number, assigned the first time it is met."""
    return numbers.setdefault(chunk_id, len(numbers) + 1)


def render_stream(text: str, numbers: dict[str, int]) -> str:
    """Answer-so-far with every closed reference replaced by its number.

    `numbers` is carried across calls and mutated. Numbering by order of first
    appearance is what makes this possible at all: the number of a reference
    depends only on the text before it, so it can be assigned while the answer
    is still arriving, long before the citation array exists.

    A reference still being written is held back along with everything after it
    — a raw chunk id on screen for one frame is exactly what the numbers exist
    to avoid. Text that merely starts with "[[" is not held hostage: once it has
    closed, or grown past any possible reference, it flows again.
    """
    cut = text.rfind(_OPEN_REF)
    if cut != -1 and INLINE_REF.match(text, cut) is None:
        tail = text[cut:]
        if "]]" not in tail and len(tail) <= _MAX_REF_CHARS:
            text = text[:cut]
    numbered = INLINE_REF.sub(lambda m: marker(_number_for(numbers, m.group(1))), text)
    # A closed reference the substitution did not claim is malformed, and the
    # holding rule above has already let it through. finalize would strip it,
    # but only after the reader had watched it arrive.
    return UNRESOLVED_REF.sub("", numbered)


def number_inline_refs(
    answer: str, citations: list[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """Number the references in the prose and order the citations to match.

    Returns the rewritten answer and the citations carrying their `marker`.
    Citations sharing a chunk share a number: the reference the model writes
    identifies the passage, and the passage is what gets highlighted, so two
    quotes from one chunk are one place in the document, not two.

    A reference whose citation did not survive verification is left untouched
    for strip_inline_chunk_refs to remove. Numbering skips it rather than
    burning a number on it, so the reader never meets a gap in the sequence or,
    worse, a number pointing at someone else's source.
    """
    citable = {citation["chunk_id"] for citation in citations}
    numbers: dict[str, int] = {}

    def replace(match: re.Match[str]) -> str:
        chunk_id = match.group(1)
        if chunk_id not in citable:
            return match.group(0)
        return marker(_number_for(numbers, chunk_id))

    numbered = INLINE_REF.sub(replace, answer)
    for citation in citations:
        citation["marker"] = numbers.get(citation["chunk_id"])
    # Cited first, in reading order; anything the prose never pointed at keeps
    # its place at the end rather than being dropped.
    unnumbered = len(numbers) + 1
    ordered = sorted(citations, key=lambda c: c["marker"] or unnumbered)
    return numbered, ordered
