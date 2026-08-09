import functools
import html
import json
import re
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from app import chat as chat_service, db, graph, pack
from app.config import settings
from app.schemas import ChatRequest, ChatResponse

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_HEAD_TAG = re.compile(rb"<head[^>]*>", re.IGNORECASE)
_BASE_TAG = re.compile(rb"<base[\s>]", re.IGNORECASE)
_DOC_ID = re.compile(r"[A-Za-z0-9_-]+")


@functools.lru_cache(maxsize=1)
def _source_urls() -> dict[str, str]:
    """doc_id -> source_url from the corpus manifest (best-effort, never read by
    ingestion): used only so the viewer renders an HTML original the way its
    source site does, when the document carries no <base href> of its own."""
    if not settings.manifest_path.is_file():
        return {}
    entries = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
    return {entry["id"]: entry["source_url"] for entry in entries if entry.get("source_url")}


def _with_base_href(content: bytes, doc_id: str) -> bytes:
    """Inject <base href> into scraped HTML that lacks one (e.g. Next.js blog
    pages with no server-rendered <base>): without it the sandboxed iframe
    resolves the page's relative asset/link paths against our own origin
    instead of the source site, and the original renders blank/broken."""
    if _BASE_TAG.search(content, endpos=4096):
        return content
    source_url = _source_urls().get(doc_id)
    if not source_url:
        return content
    base_tag = f'<base href="{html.escape(source_url, quote=True)}">'.encode()
    match = _HEAD_TAG.search(content)
    if not match:
        return content
    return content[: match.end()] + base_tag + content[match.end() :]


@asynccontextmanager
async def lifespan(app: FastAPI):
    pack.check()  # a malformed pack should fail at boot, not on the first query
    db.ensure_schema()
    app.state.pool = db.create_pool()
    app.state.graph = graph.build(app.state.pool)
    yield
    app.state.pool.close()


app = FastAPI(title=pack.manifest()["title"], lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/pack")
def pack_info() -> dict:
    """Title, locale and starter questions, so the UI carries no domain copy."""
    return pack.ui()


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request) -> dict:
    history = [turn.model_dump() for turn in payload.history]
    return chat_service.chat(request.app.state.graph, payload.message, history)


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    history = [turn.model_dump() for turn in payload.history]

    def events() -> Iterator[str]:
        try:
            for event, data in chat_service.chat_stream(
                request.app.state.graph, payload.message, history
            ):
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 — surface the failure to the client
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/documents")
def documents(request: Request) -> list[dict]:
    with request.app.state.pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT doc_id, format, status, page_count, chunk_count, table_count, error
            FROM documents ORDER BY doc_id
            """
        ).fetchall()
    columns = [
        "doc_id",
        "format",
        "status",
        "page_count",
        "chunk_count",
        "table_count",
        "error",
    ]
    return [dict(zip(columns, row)) for row in rows]


@app.get("/api/documents/{doc_id}/file")
def document_file(doc_id: str, request: Request) -> Response:
    with request.app.state.pool.connection() as conn:
        row = conn.execute(
            "SELECT format, storage_path FROM documents WHERE doc_id = %s AND status = 'PUBLISHED'",
            (doc_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    format_, storage_path = row
    path = settings.objects_dir / storage_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="original file missing from object storage")
    media_type = MEDIA_TYPES.get(format_, "application/octet-stream")
    if format_ != "html":
        return FileResponse(path, media_type=media_type)
    content = _with_base_href(path.read_bytes(), doc_id)
    return Response(content=content, media_type=media_type)


@app.get("/api/documents/{doc_id}/text")
def document_text(doc_id: str, request: Request) -> Response:
    """The Docling extraction already in the workspace (document.md): a readable
    fallback for an HTML original the sandboxed viewer cannot render, i.e. pages
    that need client-side JavaScript to show any content (see HtmlViewer.tsx)."""
    if not _DOC_ID.fullmatch(doc_id):
        raise HTTPException(status_code=404, detail="document not found")
    with request.app.state.pool.connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM documents WHERE doc_id = %s AND status = 'PUBLISHED'", (doc_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    path = settings.workspace_dir / doc_id / "document.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="text extraction not available")
    return Response(content=path.read_bytes(), media_type="text/markdown; charset=utf-8")
