"""Citation contract: normalize LLM citations onto retrieved chunks and verify quotes."""

import re
import unicodedata
from typing import TYPE_CHECKING, Any

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
                "chunk_id": chunk_id,
                "page": chunk.page,
                "bbox": chunk.bbox,
                "bboxes": chunk.bboxes,
                "quote": quote,
                "chunk_text": chunk.text,
                "verified": quote_is_verified(quote, chunk.text),
            }
        )
    return citations
