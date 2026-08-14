import json
import re
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from app import assistant, chat as chat_service, db, graph
from app.config import settings
from app.schemas import ChatRequest, ChatResponse

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "html": "text/html; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_DOC_ID = re.compile(r"[A-Za-z0-9_-]+")


@asynccontextmanager
async def lifespan(app: FastAPI):
    assistant.check()  # malformed config should fail at boot, not on the first query
    db.ensure_schema()
    app.state.pool = db.create_pool()
    app.state.graph = graph.build(app.state.pool)
    yield
    app.state.pool.close()


app = FastAPI(title=assistant.ui()["title"], lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/assistant")
def assistant_info() -> dict:
    """Title, locale and starter questions, so the UI carries no copy of its own."""
    return assistant.ui()


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
    return FileResponse(path, media_type=MEDIA_TYPES.get(format_, "application/octet-stream"))


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
