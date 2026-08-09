from typing import Any, Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[Turn] = []


class Citation(BaseModel):
    doc_id: str
    chunk_id: str
    page: int | None
    bbox: dict[str, Any] | None
    bboxes: list[dict[str, Any]] | None = None
    quote: str
    chunk_text: str
    verified: bool


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    path: Literal["rag", "agent"]
    meta: dict[str, Any]
