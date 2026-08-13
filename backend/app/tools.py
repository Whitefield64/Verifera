"""Agent tools. Every result carries source metadata, because the citation
contract depends on it.

The backend owns the tool surface: the agent gets no free filesystem or database
access, only these three calls. A per-run record tracks which chunk_ids the tools
actually exposed, and the final answer may cite nothing else — an agent cannot
cite a document it never opened.

State is passed in explicitly rather than kept in a module-level registry, so a
run carries its own context and nothing is shared between concurrent requests.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from psycopg_pool import ConnectionPool

from app import llm, retrieval
from app import workspace_layout as layout
from app.config import settings

SNIPPET_CHARS = 500
SECTION_CHARS_CAP = 20_000
TABLE_CHUNK_PREVIEW = 1500

BUDGET_EXHAUSTED = (
    "Consultation budget exhausted: do NOT call any more tools. Answer now with "
    "what you have already gathered, or state that you could not find the answer."
)

_TABLE_CHUNKS_SQL = """
SELECT chunk_id, page, text FROM chunks
WHERE doc_id = %s AND kind = 'table' AND (%s::int IS NULL OR page = %s)
ORDER BY seq LIMIT 10
"""


def _function(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


# What the agent is allowed to do. Descriptions are domain-neutral on purpose:
# the pack's prompt supplies the domain, these describe the mechanism.
SCHEMAS = [
    _function(
        "semantic_search",
        "Search the knowledge base for passages related to a query. Returns "
        "matching chunks with their document, section and page. Use it to find "
        "where something is, then read the section for the full context.",
        {"query": {"type": "string", "description": "What to look for."}},
        ["query"],
    ),
    _function(
        "get_document_metadata",
        "List what a document contains: its summary, its sections and its "
        "tables, with the paths to read them.",
        {"doc_id": {"type": "string", "description": "Document identifier."}},
        ["doc_id"],
    ),
    _function(
        "read_document_section",
        "Read one section or table of a document. Sections carry inline "
        "<!-- chunk: ... --> markers giving the chunk_id you may cite for the "
        "text beneath them; for tables, cite the ids listed in citable_chunks.",
        {
            "doc_id": {"type": "string", "description": "Document identifier."},
            "path": {
                "type": "string",
                "description": "A path from get_document_metadata, e.g. 'sections/03-scope.md'.",
            },
        },
        ["doc_id", "path"],
    ),
]

TOOL_NAMES = [schema["function"]["name"] for schema in SCHEMAS]


@dataclass
class ToolRun:
    """One agent run: its database handle, what it has seen, what it has spent."""

    pool: ConnectionPool
    seen_chunk_ids: set[str] = field(default_factory=set)
    calls: int = 0

    @property
    def budget_left(self) -> int:
        return settings.agent_max_tool_calls - self.calls


def _doc_dir(doc_id: str) -> Path | None:
    if not layout.DOC_ID.fullmatch(doc_id):
        return None
    path = settings.workspace_dir / doc_id
    return path if path.is_dir() else None


def _sections_index(doc_id: str) -> list[dict[str, Any]]:
    path = settings.workspace_dir / doc_id / layout.SECTIONS_INDEX_FILE
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _section_of(doc_id: str, chunk_id: str) -> dict[str, Any] | None:
    for entry in _sections_index(doc_id):
        if chunk_id in entry["chunk_ids"]:
            return entry
    return None


def _gloss_of(doc_id: str) -> str | None:
    meta_path = settings.workspace_dir / doc_id / layout.META_FILE
    if not meta_path.is_file():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8")).get("gloss")


def call(run: ToolRun, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one tool call, enforcing the soft budget.

    The soft cap answers with an instruction rather than an error: the model
    should wind up and reply, not retry. The hard stop lives in the graph.
    """
    run.calls += 1
    if run.calls > settings.agent_max_tool_calls:
        return {"error": BUDGET_EXHAUSTED}

    if tool == "semantic_search":
        return semantic_search(run, str(args.get("query", "")))
    if tool == "get_document_metadata":
        return get_document_metadata(str(args.get("doc_id", "")))
    if tool == "read_document_section":
        return read_document_section(run, str(args.get("doc_id", "")), str(args.get("path", "")))
    return {"error": f"unknown tool: {tool}"}


def semantic_search(run: ToolRun, query: str) -> dict[str, Any]:
    if not query.strip():
        return {"error": "empty query"}
    query_vector = llm.embed([query])[0]
    with run.pool.connection() as conn:
        # No per-document cap. A cap of 2 hid the operative article behind the
        # first two chunks of the act the agent was already reading: on the
        # penalties question it surfaced Article 100 and never Article 99,
        # across thirteen tool calls. k stays at 8 — measured, going higher
        # surfaced nothing more, so this costs no extra tokens per call.
        chunks = retrieval.hybrid_search(conn, query, query_vector, k=8, per_doc_cap=0)
    results = []
    for chunk in chunks:
        run.seen_chunk_ids.add(chunk.chunk_id)
        # Corpora routinely hold near-identical titles (translations, consolidated
        # versions, annexes of one act). The section title and the gloss are what
        # let the model tell them apart.
        section = _section_of(chunk.doc_id, chunk.chunk_id)
        results.append(
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "gloss": _gloss_of(chunk.doc_id),
                "page": chunk.page,
                "kind": chunk.kind,
                "section": section["file"] if section else None,
                "section_title": section["title"] if section else None,
                "text": chunk.text[:SNIPPET_CHARS],
            }
        )
    return {"results": results}


def get_document_metadata(doc_id: str) -> dict[str, Any]:
    doc_dir = _doc_dir(doc_id)
    if doc_dir is None:
        return {"error": f"unknown document: {doc_id!r}"}
    meta_path = doc_dir / layout.META_FILE
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    summary_path = doc_dir / layout.SUMMARY_FILE
    summary = summary_path.read_text(encoding="utf-8") if summary_path.is_file() else None
    sections = [
        {"path": e["file"], "title": e["title"], "pages": e["pages"]}
        for e in _sections_index(doc_id)
    ]
    tables_dir = doc_dir / layout.TABLES_DIR
    tables = sorted(p.name for p in tables_dir.glob("*.md")) if tables_dir.is_dir() else []
    return {
        "doc_id": doc_id,
        "title": meta.get("title"),
        "gloss": meta.get("gloss"),
        "format": meta.get("format"),
        "page_count": meta.get("page_count"),
        "summary": summary,
        "sections": sections,
        "tables": [f"{layout.TABLES_DIR}/{name}" for name in tables],
    }


def read_document_section(run: ToolRun, doc_id: str, path: str) -> dict[str, Any]:
    doc_dir = _doc_dir(doc_id)
    if doc_dir is None:
        return {"error": f"unknown document: {doc_id!r}"}
    if not layout.READABLE_PATH.fullmatch(path):
        return {"error": f"invalid path: {path!r} — use a path from get_document_metadata"}
    file_path = doc_dir / path
    if not file_path.is_file():
        return {"error": f"no such file: {path!r} — check get_document_metadata"}

    content = file_path.read_text(encoding="utf-8")
    truncated = len(content) > SECTION_CHARS_CAP
    if truncated:
        content = content[:SECTION_CHARS_CAP]

    result: dict[str, Any] = {"doc_id": doc_id, "path": path, "content": content}
    if truncated:
        result["note"] = "content truncated: read the smaller sections instead"

    if path.startswith(f"{layout.SECTIONS_DIR}/"):
        for entry in _sections_index(doc_id):
            if entry["file"] == path:
                run.seen_chunk_ids.update(entry["chunk_ids"])
                result["pages"] = entry["pages"]
                break
    elif path.startswith(f"{layout.TABLES_DIR}/"):
        # A markdown grid cannot be quoted verbatim. Attach the table chunks for
        # the same page: their text is what the quote verifier compares against.
        page = layout.page_of_table(content)
        with run.pool.connection() as conn:
            rows = conn.execute(_TABLE_CHUNKS_SQL, (doc_id, page, page)).fetchall()
        citable = []
        for chunk_id, chunk_page, text in rows:
            run.seen_chunk_ids.add(chunk_id)
            citable.append(
                {"chunk_id": chunk_id, "page": chunk_page, "text": text[:TABLE_CHUNK_PREVIEW]}
            )
        result["citable_chunks"] = citable
        if citable:
            result["note"] = (
                "To cite this table use the chunk_ids in citable_chunks and copy the "
                "quote verbatim from their text field."
            )
    return result
