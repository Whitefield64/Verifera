"""Folder-driven ingestion: data/raw -> parse -> chunk -> embed -> summarize -> workspace -> publish -> object storage.

data/raw is the only way documents enter the system, and one run of this takes a
folder all the way to a corpus the agent can answer from — glosses included.
There is no second command to remember.
"""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from pgvector import Vector
from psycopg.types.json import Jsonb

from app import db, llm
from app.config import settings
from ingestion import summaries, workspace
from ingestion.chunking import ChunkRecord, build_chunks
from ingestion.parsing import SUPPORTED_SUFFIXES, parse_document
from ingestion.storage import ObjectStore

_INSERT_CHUNK = """
INSERT INTO chunks
    (chunk_id, doc_id, seq, kind, text, page, bbox, bboxes, char_start, char_end, headings, embedding)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


@dataclass
class IngestOutcome:
    doc_id: str
    outcome: str  # "ok" | "skip" | "fail"
    detail: str
    chunk_count: int = 0
    table_count: int = 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunk_row(chunk: ChunkRecord, vector: list[float]) -> tuple:
    return (
        chunk.chunk_id,
        chunk.doc_id,
        chunk.seq,
        chunk.kind,
        chunk.text,
        chunk.page,
        Jsonb(chunk.bbox) if chunk.bbox else None,
        Jsonb(chunk.bboxes) if chunk.bboxes else None,
        chunk.char_start,
        chunk.char_end,
        chunk.headings,
        Vector(vector),
    )


def ingest_file(path: Path) -> IngestOutcome:
    doc_id = path.stem
    sha = _sha256(path)
    file_format = path.suffix.lower().lstrip(".")
    store = ObjectStore(settings.objects_dir)

    with db.connect() as conn:
        row = conn.execute(
            "SELECT sha256, status FROM documents WHERE doc_id = %s", (doc_id,)
        ).fetchone()
        if row and row[0] == sha and row[1] == "PUBLISHED":
            store.store(path)
            return IngestOutcome(
                doc_id, "skip", "already published with identical content"
            )
        conn.execute(
            """
            INSERT INTO documents (doc_id, filename, format, sha256, status)
            VALUES (%s, %s, %s, %s, 'RECEIVED')
            ON CONFLICT (doc_id) DO UPDATE SET
                filename = EXCLUDED.filename, format = EXCLUDED.format,
                sha256 = EXCLUDED.sha256, status = 'RECEIVED',
                error = NULL, ingested_at = now(), published_at = NULL
            """,
            (doc_id, path.name, file_format, sha),
        )
        conn.commit()

    try:
        doc = parse_document(path)
        # The name of the file is the name of the document. Titles pulled out of
        # the content read well in a contract and badly in a regulation ("2024/1689"),
        # and the reader cannot influence them; a filename they choose is honest
        # under a citation and predictable everywhere else.
        title = doc_id
        page_count = doc.num_pages() or None
        chunks = build_chunks(doc, doc_id)
        if not chunks:
            raise ValueError("no text extracted from the document")

        with db.connect() as conn:
            conn.execute(
                "UPDATE documents SET status = 'PARSED', title = %s, page_count = %s WHERE doc_id = %s",
                (title, page_count, doc_id),
            )
            conn.commit()

        vectors = llm.embed([chunk.embed_text for chunk in chunks])
        markdown = doc.export_to_markdown()
        gloss, summary = summaries.generate(title, file_format, markdown)

        table_count = workspace.materialize(
            doc,
            doc_id,
            {
                "filename": path.name,
                "format": file_format,
                "sha256": sha,
                "title": title,
                "page_count": page_count,
                "chunk_count": len(chunks),
                "gloss": gloss,
            },
            settings.workspace_dir,
            markdown,
            summary,
        )
        workspace.write_sections(
            settings.workspace_dir / doc_id,
            title,
            [
                {
                    "chunk_id": c.chunk_id,
                    "kind": c.kind,
                    "text": c.text,
                    "page": c.page,
                    "headings": c.headings,
                }
                for c in chunks
            ],
        )

        with db.connect() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
                with conn.cursor() as cursor:
                    cursor.executemany(
                        _INSERT_CHUNK,
                        [
                            _chunk_row(chunk, vector)
                            for chunk, vector in zip(chunks, vectors)
                        ],
                    )
                conn.execute(
                    """
                    UPDATE documents SET status = 'PUBLISHED', published_at = now(),
                        chunk_count = %s, table_count = %s, storage_path = %s
                    WHERE doc_id = %s
                    """,
                    (len(chunks), table_count, path.name, doc_id),
                )

        store.store(path)
        workspace.rebuild_index(settings.workspace_dir)
        return IngestOutcome(
            doc_id,
            "ok",
            f"{len(chunks)} chunks, {table_count} tables",
            len(chunks),
            table_count,
        )

    except Exception as error:  # noqa: BLE001 — one broken document must not stall the inbox
        detail = f"{type(error).__name__}: {error}"
        with db.connect() as conn:
            conn.execute(
                "UPDATE documents SET status = 'FAILED', error = %s WHERE doc_id = %s",
                (detail[:1000], doc_id),
            )
            conn.commit()
        failed_dir = path.parent / "_failed"
        failed_dir.mkdir(exist_ok=True)
        shutil.move(str(path), str(failed_dir / path.name))
        return IngestOutcome(doc_id, "fail", detail[:300])


def ingest_folder(raw_dir: Path | None = None) -> list[IngestOutcome]:
    raw_dir = raw_dir or settings.raw_dir
    # The inbox is drained by every run, so an empty one is the normal state and
    # a missing one only means nobody has put a document there yet.
    raw_dir.mkdir(parents=True, exist_ok=True)
    db.ensure_schema()

    files = sorted(
        p for p in raw_dir.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    outcomes: list[IngestOutcome] = []
    for path in files:
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            outcomes.append(IngestOutcome(path.name, "skip", "unsupported format"))
            print(f"skip {path.name}: unsupported format")
            continue
        outcome = ingest_file(path)
        outcomes.append(outcome)
        print(f"{outcome.outcome:4s} {outcome.doc_id}: {outcome.detail}")

    ok = sum(1 for o in outcomes if o.outcome == "ok")
    skipped = sum(1 for o in outcomes if o.outcome == "skip")
    failed = sum(1 for o in outcomes if o.outcome == "fail")
    print(f"\nTotal: {len(outcomes)} files — ok {ok}, skip {skipped}, fail {failed}")
    return outcomes


def print_status() -> None:
    with db.connect() as conn:
        by_status = conn.execute(
            "SELECT status, count(*) FROM documents GROUP BY status ORDER BY status"
        ).fetchall()
        totals = conn.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE c.page IS NOT NULL),
                   count(*) FILTER (WHERE c.bbox IS NOT NULL),
                   count(*) FILTER (WHERE c.kind = 'table')
            FROM chunks c JOIN documents d USING (doc_id)
            WHERE d.status = 'PUBLISHED'
            """
        ).fetchone()
        by_format = conn.execute(
            """
            SELECT d.format, count(*), count(*) FILTER (WHERE c.bbox IS NOT NULL)
            FROM chunks c JOIN documents d USING (doc_id)
            WHERE d.status = 'PUBLISHED'
            GROUP BY d.format ORDER BY d.format
            """
        ).fetchall()

    print("Documents by status:")
    for status, count in by_status:
        print(f"  {status}: {count}")
    total, with_page, with_bbox, tables = totals or (0, 0, 0, 0)
    if total:
        print(f"\nPUBLISHED chunks: {total} (tables: {tables})")
        print(f"  with page: {with_page} ({100 * with_page / total:.1f}%)")
        print(f"  with bbox: {with_bbox} ({100 * with_bbox / total:.1f}%)")
        print("\nbbox coverage by format:")
        for fmt, count, bbox_count in by_format:
            print(f"  {fmt}: {bbox_count}/{count} ({100 * bbox_count / count:.1f}%)")
    else:
        print("\nNo published chunks.")


def check_stability(doc_id: str) -> bool:
    """Re-parse the stored original and verify chunk IDs are reproduced identically."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT storage_path, status FROM documents WHERE doc_id = %s", (doc_id,)
        ).fetchone()
        if row is None or row[1] != "PUBLISHED":
            print(f"{doc_id}: not published ({row[1] if row else 'absent'})")
            return False
        stored_ids = [
            r[0]
            for r in conn.execute(
                "SELECT chunk_id FROM chunks WHERE doc_id = %s ORDER BY seq", (doc_id,)
            ).fetchall()
        ]

    source = ObjectStore(settings.objects_dir).path_for(row[0])
    recomputed = [
        chunk.chunk_id for chunk in build_chunks(parse_document(source), doc_id)
    ]

    if recomputed == stored_ids:
        print(f"{doc_id}: STABLE — {len(stored_ids)} chunk ids identical on re-parse")
        return True
    same = len(set(recomputed) & set(stored_ids))
    print(
        f"{doc_id}: UNSTABLE — {same}/{len(stored_ids)} in common "
        f"(db: {len(stored_ids)}, re-parse: {len(recomputed)})"
    )
    return False
