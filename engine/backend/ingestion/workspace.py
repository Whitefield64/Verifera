"""Filesystem projection of ingested documents (agent-path navigation surface).

Regenerable from the pipeline (or from Postgres via `python -m ingestion
rebuild-workspace`); never the source of truth.
"""

import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from docling_core.types.doc import DoclingDocument

from app import workspace_layout as layout

# sections are the agent's unit of reading: large enough to carry context,
# small enough not to burn the prompt budget
MIN_SECTION_CHARS = 1200
MAX_SECTION_CHARS = 7000


def materialize(
    doc: DoclingDocument,
    doc_id: str,
    meta: dict[str, Any],
    workspace_dir: Path,
    markdown: str,
    summary: str = "",
) -> int:
    """Write document.md, summary.md, tables/ artifacts and meta.json; returns the table count.

    Everything under the document's directory is derived from the file that was
    just parsed, so the directory is wiped and rewritten. Nothing survives a
    re-ingest: a summary describing the previous version of a document is worse
    than no summary, because the agent trusts it.
    """
    doc_dir = workspace_dir / doc_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir)
    doc_dir.mkdir(parents=True)

    (doc_dir / "document.md").write_text(markdown, encoding="utf-8")
    if summary:
        (doc_dir / "summary.md").write_text(summary + "\n", encoding="utf-8")

    table_count = 0
    if doc.tables:
        tables_dir = doc_dir / "tables"
        tables_dir.mkdir()
        for index, table in enumerate(doc.tables, 1):
            prov = table.prov[0] if table.prov else None
            header = layout.table_header(index, doc_id, prov.page_no if prov else None)
            markdown = table.export_to_markdown(doc)
            (tables_dir / f"table-{index:02d}.md").write_text(
                f"{header}\n\n{markdown}\n", encoding="utf-8"
            )
            try:
                table.export_to_dataframe(doc).to_csv(
                    tables_dir / f"table-{index:02d}.csv", index=False
                )
            except Exception:
                pass  # CSV is best-effort; the markdown artifact is the contract
            table_count += 1

    meta = {**meta, "doc_id": doc_id, "table_count": table_count}
    (doc_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return table_count


def rebuild_index(workspace_dir: Path) -> None:
    entries = []
    for meta_path in sorted(workspace_dir.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pages = meta.get("page_count") or "-"
        line = (
            f"- **{meta['doc_id']}** — {meta.get('title') or meta.get('filename', '?')} "
            f"({meta.get('format', '?')}, pages: {pages}, chunks: {meta.get('chunk_count', '?')}, "
            f"tables: {meta.get('table_count', 0)})"
        )
        if meta.get("gloss"):
            line += f"\n  {meta['gloss']}"
        entries.append(line)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    content = "# Document index\n\n" + "\n".join(entries) + "\n"
    (workspace_dir / "_index.md").write_text(content, encoding="utf-8")


def _slug(title: str, max_length: int = 40) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug[:max_length].rstrip("-") or "section"


def _group_sections(chunks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Consecutive chunks, split on heading change once big enough (hard cap on size)."""
    sections: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    previous_headings: tuple | None = None
    for chunk in chunks:
        headings = tuple(chunk["headings"])
        if current and (
            (headings != previous_headings and size >= MIN_SECTION_CHARS)
            or size >= MAX_SECTION_CHARS
        ):
            sections.append(current)
            current, size = [], 0
        current.append(chunk)
        size += len(chunk["text"])
        previous_headings = headings
    if current:
        sections.append(current)
    return sections


_LABEL_MAX_CHARS = 80


def _is_label(line: str) -> bool:
    """A line that names what follows instead of saying something itself.

    Purely typographic — short, no sentence-ending punctuation, opens like a
    title. Nothing here knows what an 'Article' is; the same rule finds the
    numbered clauses of a regulation and the headings of a standard.
    """
    if not (6 <= len(line) <= _LABEL_MAX_CHARS):
        return False
    if line[-1] in ".,;:":
        return False
    if not any(character.isalpha() for character in line):
        return False
    return line[0].isupper() or line[0].isdigit()


def _label_run(section: list[dict[str, Any]], max_length: int = 90) -> str:
    """The first run of consecutive label lines in the section.

    Publishers of legal texts routinely ship no heading markup at all — every
    HTML document in the demo corpus has empty `headings` on all of its chunks
    — and the number and the title of a provision then arrive as two ordinary
    short lines in the body text. Taken together they are the only usable name
    the section has.
    """
    fallback = ""
    for chunk in section:
        run: list[str] = []
        for raw in chunk["text"].splitlines():
            line = " ".join(raw.strip().lstrip("#").split())
            if not line:
                continue
            if _is_label(line):
                run.append(line)
                continue
            if len(run) >= 2:
                return " › ".join(run)[:max_length].rstrip()
            fallback = fallback or (run[0] if run else line[:max_length].rstrip())
            run = []
        if len(run) >= 2:
            return " › ".join(run)[:max_length].rstrip()
    return fallback


def _section_title(section: list[dict[str, Any]], doc_title: str) -> str:
    for chunk in section:
        if chunk["headings"]:
            return " › ".join(chunk["headings"])
    return _label_run(section) or doc_title


def write_sections(doc_dir: Path, doc_title: str, chunks: list[dict[str, Any]]) -> int:
    """Materialize sections/ with inline chunk markers + sections.json; returns section count.

    The markers give the agent citable chunk_ids next to the exact text they cover:
    quotes copied from a section verify against the chunk in the database.
    """
    sections_dir = doc_dir / "sections"
    if sections_dir.exists():
        shutil.rmtree(sections_dir)
    sections_dir.mkdir(parents=True)

    grouped = _group_sections(chunks)
    # A long run under one heading — a regulation's recitals arrive as a single
    # "Whereas:" — is split by the size cap into sections a reader cannot tell
    # apart. Eleven identical rows in the index are eleven rows the agent has to
    # open at random, so the repeats say which part they are.
    titles = [_section_title(section, doc_title) for section in grouped]
    repeated = {title: titles.count(title) for title in set(titles) if titles.count(title) > 1}
    position: dict[str, int] = {}

    index_entries = []
    for number, (section, title) in enumerate(zip(grouped, titles), 1):
        if title in repeated:
            position[title] = position.get(title, 0) + 1
            title = f"{title} ({position[title]}/{repeated[title]})"
        filename = f"{number:02d}-{_slug(title)}.md"
        parts = [f"# {title}\n"]
        for chunk in section:
            marker = layout.chunk_marker(chunk["chunk_id"], chunk["page"], chunk["kind"])
            parts.append(f"{marker}\n{chunk['text']}")
        (sections_dir / filename).write_text("\n\n".join(parts) + "\n", encoding="utf-8")

        pages = sorted({c["page"] for c in section if c["page"] is not None})
        index_entries.append(
            {
                "file": f"sections/{filename}",
                "title": title,
                "pages": pages,
                "chunk_ids": [c["chunk_id"] for c in section],
            }
        )

    (doc_dir / "sections.json").write_text(
        json.dumps(index_entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(index_entries)
