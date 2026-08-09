"""Chunking with stable content-derived chunk IDs and page/bbox provenance."""

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import tiktoken
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.doc import DocItemLabel, DoclingDocument

from app.config import settings


@dataclass
class ChunkRecord:
    chunk_id: str
    doc_id: str
    seq: int
    kind: str  # "text" | "table"
    text: str  # displayed / quoted / highlighted text
    embed_text: str  # heading-contextualized text used for the embedding
    page: int | None
    bbox: dict[str, Any] | None
    bboxes: list[dict[str, Any]]
    char_start: int
    char_end: int
    headings: list[str]


@lru_cache(maxsize=1)
def _chunker() -> HybridChunker:
    tokenizer = OpenAITokenizer(
        tokenizer=tiktoken.get_encoding("cl100k_base"),
        max_tokens=settings.max_chunk_tokens,
    )
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)


_MARKDOWN_LINK = re.compile(r"\[+([^\]]*)\]+\([^)]*\)")
_BLANK_LINES = re.compile(r"\n{3,}")

# below this threshold a text chunk is a crumb (menu entry, price, breadcrumb)
MIN_CHUNK_CHARS = 25


def clean_text(text: str) -> str:
    """Drop markdown link targets kept by the HTML parser: they pollute embeddings,
    full-text search and quote verification (the LLM quotes the rendered text)."""
    text = _MARKDOWN_LINK.sub(r"\1", text)
    return _BLANK_LINES.sub("\n\n", text).strip()


def chunk_id_for(doc_id: str, kind: str, text: str) -> str:
    """Content-derived ID: survives re-ingestion and insertion of unrelated chunks."""
    digest = hashlib.sha256(f"{kind}\x1f{text}".encode()).hexdigest()[:16]
    return f"{doc_id}#{digest}"


def _is_table(chunk: Any) -> bool:
    return any(
        getattr(item, "label", None) == DocItemLabel.TABLE
        for item in (chunk.meta.doc_items or [])
    )


def _provenance(
    chunk: Any, doc: DoclingDocument
) -> tuple[int | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """Collect page rectangles (top-left origin, PDF points); union on the primary page."""
    rects: list[dict[str, Any]] = []
    for item in chunk.meta.doc_items or []:
        for prov in getattr(item, "prov", None) or []:
            page = doc.pages.get(prov.page_no)
            if page is None or prov.bbox is None or page.size is None:
                continue
            box = prov.bbox.to_top_left_origin(page_height=page.size.height)
            width, height = box.r - box.l, box.b - box.t
            if width <= 0 or height <= 0:
                continue
            rects.append(
                {
                    "page": prov.page_no,
                    "x": round(box.l, 2),
                    "y": round(box.t, 2),
                    "w": round(width, 2),
                    "h": round(height, 2),
                    "page_w": round(page.size.width, 2),
                    "page_h": round(page.size.height, 2),
                }
            )
    if not rects:
        return None, None, []

    primary_page = rects[0]["page"]
    on_page = [r for r in rects if r["page"] == primary_page]
    x0 = min(r["x"] for r in on_page)
    y0 = min(r["y"] for r in on_page)
    x1 = max(r["x"] + r["w"] for r in on_page)
    y1 = max(r["y"] + r["h"] for r in on_page)
    bbox = {
        "x": round(x0, 2),
        "y": round(y0, 2),
        "w": round(x1 - x0, 2),
        "h": round(y1 - y0, 2),
        "page_w": on_page[0]["page_w"],
        "page_h": on_page[0]["page_h"],
    }
    return primary_page, bbox, rects


def build_chunks(doc: DoclingDocument, doc_id: str) -> list[ChunkRecord]:
    chunker = _chunker()
    records: list[ChunkRecord] = []
    seen: set[tuple[str, str]] = set()
    cursor = 0

    for chunk in chunker.chunk(doc):
        text = clean_text(chunk.text)
        if not text:
            continue
        kind = "table" if _is_table(chunk) else "text"
        if kind != "table" and len(text) < MIN_CHUNK_CHARS:
            continue
        key = (kind, text)
        # page headers and boilerplate repeat verbatim hundreds of times within
        # the same document: keep the first occurrence only
        if key in seen:
            continue
        seen.add(key)

        page, bbox, bboxes = _provenance(chunk, doc)
        char_start, char_end = cursor, cursor + len(text)
        cursor = char_end + 2

        records.append(
            ChunkRecord(
                chunk_id=chunk_id_for(doc_id, kind, text),
                doc_id=doc_id,
                seq=len(records),
                kind=kind,
                text=text,
                embed_text=clean_text(chunker.contextualize(chunk=chunk)),
                page=page,
                bbox=bbox,
                bboxes=bboxes,
                char_start=char_start,
                char_end=char_end,
                headings=list(chunk.meta.headings or []),
            )
        )
    return records
