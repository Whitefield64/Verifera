"""Repair the agent workspace from the chunks already in Postgres.

Maintenance, not part of the normal path: `ingest` already produces a complete
workspace. This exists for when the workspace is lost or edited by hand, or when
summaries should be regenerated without paying to parse and embed again —
chunk_ids, and therefore every citation, stay intact.
"""

import json
import shutil
from typing import Any

from app import db
from app.config import settings
from ingestion import summaries, workspace

_FETCH_DOCS = """
SELECT doc_id, title, format, page_count, chunk_count, table_count
FROM documents WHERE status = 'PUBLISHED' ORDER BY doc_id
"""

_FETCH_CHUNKS = """
SELECT chunk_id, seq, kind, text, page, headings
FROM chunks WHERE doc_id = %s ORDER BY seq
"""


def _chunk_dicts(rows: list[tuple]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": row[0],
            "seq": row[1],
            "kind": row[2],
            "text": row[3],
            "page": row[4],
            "headings": row[5] or [],
        }
        for row in rows
    ]


def _summary_input(doc_dir, chunks: list[dict[str, Any]]) -> str:
    """The parsed markdown if the workspace still holds it, the chunks otherwise."""
    document_md = doc_dir / "document.md"
    if document_md.is_file():
        return document_md.read_text(encoding="utf-8")
    return "\n\n".join(chunk["text"] for chunk in chunks)


def _clean_cruft(keep_ids: set[str]) -> list[str]:
    """Remove workspace-root entries that do not belong to a published document."""
    if not keep_ids:
        # Empty or wrong database: without this guard the cleanup would raze
        # the entire workspace
        print("warn: no PUBLISHED document in the database — skipping workspace cleanup")
        return []
    removed: list[str] = []
    for entry in settings.workspace_dir.iterdir():
        if entry.name == "_index.md" or entry.name in keep_ids:
            continue
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
        removed.append(entry.name)
    return removed


def rebuild(only_doc: str | None = None, skip_summaries: bool = False, force_summaries: bool = False) -> int:
    with db.connect() as conn:
        docs = conn.execute(_FETCH_DOCS).fetchall()
        doc_ids = {row[0] for row in docs}

        if only_doc is None:
            removed = _clean_cruft(doc_ids)
            for name in removed:
                print(f"removed (not in database): {name}")

        summarized = 0
        for doc_id, title, fmt, page_count, chunk_count, table_count in docs:
            if only_doc and doc_id != only_doc:
                continue
            doc_dir = settings.workspace_dir / doc_id
            if not doc_dir.is_dir():
                print(f"warn {doc_id}: workspace directory missing, rebuilding it from chunks")
                doc_dir.mkdir(parents=True)

            chunks = _chunk_dicts(conn.execute(_FETCH_CHUNKS, (doc_id,)).fetchall())
            section_count = workspace.write_sections(doc_dir, title or doc_id, chunks)

            meta_path = doc_dir / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
            meta.update(
                doc_id=doc_id,
                title=title,
                format=fmt,
                page_count=page_count,
                chunk_count=chunk_count,
                table_count=table_count,
                section_count=section_count,
            )

            summary_path = doc_dir / "summary.md"
            wrote_summary = False
            if not skip_summaries and (force_summaries or not summary_path.is_file()):
                gloss, summary = summaries.generate(
                    title or doc_id, fmt, _summary_input(doc_dir, chunks)
                )
                if summary:
                    summary_path.write_text(summary + "\n", encoding="utf-8")
                    meta["gloss"] = gloss
                    summarized += 1
                    wrote_summary = True

            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"ok   {doc_id}: {section_count} sections" + (", summary" if wrote_summary else ""))

    workspace.rebuild_index(settings.workspace_dir)
    print(f"\nWorkspace rebuilt: {len(docs)} documents, {summarized} summaries generated.")
    return 0
