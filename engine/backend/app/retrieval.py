"""Hybrid retrieval: pgvector cosine + Postgres full-text, fused with Reciprocal Rank Fusion."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from pgvector import Vector

from app.config import settings

_TOKEN = re.compile(r"\w+", re.UNICODE)

_VECTOR_SQL = """
SELECT c.chunk_id
FROM chunks c JOIN documents d USING (doc_id)
WHERE d.status = 'PUBLISHED'
ORDER BY c.embedding <=> %(query_vector)s
LIMIT %(pool)s
"""

_LEXICAL_SQL = """
SELECT c.chunk_id
FROM chunks c JOIN documents d USING (doc_id)
WHERE d.status = 'PUBLISHED' AND c.tsv @@ to_tsquery('simple', %(tsquery)s)
ORDER BY ts_rank_cd(c.tsv, to_tsquery('simple', %(tsquery)s)) DESC
LIMIT %(pool)s
"""

_FETCH_SQL = """
SELECT c.chunk_id, c.doc_id, d.title, c.kind, c.text, c.page, c.bbox, c.bboxes
FROM chunks c JOIN documents d USING (doc_id)
WHERE c.chunk_id = ANY(%(chunk_ids)s)
"""

_FETCH_PUBLISHED_SQL = """
SELECT c.chunk_id, c.doc_id, d.title, c.kind, c.text, c.page, c.bbox, c.bboxes
FROM chunks c JOIN documents d USING (doc_id)
WHERE c.chunk_id = ANY(%(chunk_ids)s) AND d.status = 'PUBLISHED'
"""

# Jaccard over word tokens, above which two chunks are the same passage. 0.6
# separated the HTML/PDF pairs of the same article from genuinely different
# articles of the same act, which share vocabulary but not this much of it.
NEAR_DUPLICATE = 0.6


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    title: str | None
    kind: str
    text: str
    page: int | None
    bbox: dict[str, Any] | None
    bboxes: list[dict[str, Any]] | None
    score: float


def lexical_tsquery(query: str) -> str | None:
    """OR-query over meaningful tokens: cross-lingual questions still hit product names and numbers."""
    tokens: list[str] = []
    for token in _TOKEN.findall(query.lower()):
        if (len(token) > 2 or token.isdigit()) and token not in tokens:
            tokens.append(token)
    return " | ".join(tokens) or None


def rrf_fuse(rankings: Sequence[Sequence[str]], k0: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k0 + rank)
    return scores


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(text.lower()))


def select_top(
    scores: dict[str, float],
    k: int,
    per_doc_cap: int,
    text_of: dict[str, str] | None = None,
) -> list[str]:
    """Top-k from the fused ranking. With a cap, at most N chunks per document;
    with text_of, a passage that repeats across documents counts once and the
    best-ranked copy wins.

    Near-duplicates, not identical ones: an exact fingerprint missed the case
    that matters here, the same act ingested twice as HTML and as PDF. The
    extractions differ in hyphenation, list prefixes and whitespace, so they
    survived exact matching and took 9% of every context between them.
    """
    top: list[str] = []
    per_doc: dict[str, int] = {}
    kept: list[frozenset[str]] = []
    for chunk_id in sorted(scores, key=lambda cid: scores[cid], reverse=True):
        doc_id = chunk_id.split("#", 1)[0]
        if per_doc_cap and per_doc.get(doc_id, 0) >= per_doc_cap:
            continue
        if text_of is not None:
            signature = _tokens(text_of.get(chunk_id, chunk_id))
            if signature and any(
                len(signature & other) / len(signature | other) > NEAR_DUPLICATE
                for other in kept
            ):
                continue
            kept.append(signature)
        per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
        top.append(chunk_id)
        if len(top) == k:
            break
    return top


def fetch_by_ids(conn: psycopg.Connection, chunk_ids: list[str]) -> list[RetrievedChunk]:
    """Fetch chunks by ID (published docs only) preserving the requested order."""
    if not chunk_ids:
        return []
    rows = conn.execute(_FETCH_PUBLISHED_SQL, {"chunk_ids": chunk_ids}).fetchall()
    by_id = {
        row[0]: RetrievedChunk(
            chunk_id=row[0],
            doc_id=row[1],
            title=row[2],
            kind=row[3],
            text=row[4],
            page=row[5],
            bbox=row[6],
            bboxes=row[7],
            score=0.0,
        )
        for row in rows
    }
    return [by_id[cid] for cid in chunk_ids if cid in by_id]


def hybrid_search(
    conn: psycopg.Connection,
    query: str,
    query_vector: list[float],
    k: int | None = None,
    pool: int | None = None,
    per_doc_cap: int | None = None,
) -> list[RetrievedChunk]:
    k = k or settings.top_k
    pool = pool or settings.rrf_pool
    per_doc_cap = settings.per_doc_cap if per_doc_cap is None else per_doc_cap

    # the HNSW index returns at most ef_search candidates (default 40): without
    # this set_config a pool larger than 40 was silently truncated
    conn.execute(
        "SELECT set_config('hnsw.ef_search', %s, true)", (str(max(pool, 40)),)
    )
    vector_ids = [
        row[0]
        for row in conn.execute(
            _VECTOR_SQL, {"query_vector": Vector(query_vector), "pool": pool}
        ).fetchall()
    ]
    lexical_ids: list[str] = []
    tsquery = lexical_tsquery(query)
    if tsquery:
        lexical_ids = [
            row[0]
            for row in conn.execute(
                _LEXICAL_SQL, {"tsquery": tsquery, "pool": pool}
            ).fetchall()
        ]

    scores = rrf_fuse([vector_ids, lexical_ids])
    if not scores:
        return []

    rows = conn.execute(_FETCH_SQL, {"chunk_ids": list(scores)}).fetchall()
    by_id = {
        row[0]: RetrievedChunk(
            chunk_id=row[0],
            doc_id=row[1],
            title=row[2],
            kind=row[3],
            text=row[4],
            page=row[5],
            bbox=row[6],
            bboxes=row[7],
            score=scores[row[0]],
        )
        for row in rows
    }
    text_of = {cid: chunk.text for cid, chunk in by_id.items()}
    top_ids = select_top(scores, k, per_doc_cap, text_of)
    return [by_id[cid] for cid in top_ids if cid in by_id]
