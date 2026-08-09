"""RAG-path pieces: query condensing, context formatting, incremental answer decoding.

The orchestration that strings them together lives in app/graph.py."""

import re

from app import llm, pack, retrieval
from app.config import settings

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["chunk_id", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "citations"],
    "additionalProperties": False,
}

MAX_HISTORY_TURNS = 6
MAX_HISTORY_CHARS = 700


def trimmed_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"role": turn["role"], "content": turn["content"][:MAX_HISTORY_CHARS]}
        for turn in history[-MAX_HISTORY_TURNS:]
    ]


def condense_query(message: str, history: list[dict[str, str]]) -> str:
    conversation = "\n".join(
        f"{turn['role']}: {turn['content'][:MAX_HISTORY_CHARS]}"
        for turn in history[-MAX_HISTORY_TURNS:]
    )
    prompt = (
        f"Previous conversation:\n{conversation}\n\n"
        f"User's last message: {message}\n\nStandalone question:"
    )
    condensed = llm.complete_text(
        pack.prompt("condense"),
        [{"role": "user", "content": prompt}],
        model=settings.utility_model,
    )
    return condensed or message


def format_context(chunks: list[retrieval.RetrievedChunk]) -> str:
    parts = []
    for chunk in chunks:
        header = f"[{chunk.chunk_id}] document: {chunk.doc_id}"
        if chunk.title:
            header += f" — {chunk.title}"
        if chunk.page is not None:
            header += f", page {chunk.page}"
        if chunk.kind == "table":
            header += " (table)"
        parts.append(f"{header}\n{chunk.text}")
    return "\n\n---\n\n".join(parts)


_ANSWER_FIELD = re.compile(r'"answer"\s*:\s*"')
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/"}


def partial_answer(buf: str) -> str:
    """Unescaped value-so-far of the top-level "answer" string in a partial JSON buffer."""
    match = _ANSWER_FIELD.search(buf)
    if not match:
        return ""
    out: list[str] = []
    i = match.end()
    while i < len(buf):
        char = buf[i]
        if char == '"':
            break
        if char == "\\":
            if buf[i + 1 : i + 2] == "u":
                if i + 6 > len(buf):
                    break  # incomplete \uXXXX, wait for more input
                out.append(chr(int(buf[i + 2 : i + 6], 16)))
                i += 6
            elif i + 1 < len(buf):
                out.append(_ESCAPES.get(buf[i + 1], buf[i + 1]))
                i += 2
            else:
                break
        else:
            out.append(char)
            i += 1
    return "".join(out)
