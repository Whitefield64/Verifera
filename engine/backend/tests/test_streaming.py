"""partial_answer must reconstruct the streamed "answer" field byte-for-byte at any cut point."""

import json

from app.rag import partial_answer

FULL = {
    "answer": 'Miscela 1:1 con "Oil Developer" al 3%\nPosa: 30–45 min → ok',
    "citations": [{"chunk_id": "doc#1", "quote": "posa 30-45"}],
}
SERIALIZED = json.dumps(FULL, ensure_ascii=False)
SERIALIZED_ASCII = json.dumps(FULL)  # \uXXXX escapes


def test_full_buffer_returns_full_answer():
    assert partial_answer(SERIALIZED) == FULL["answer"]
    assert partial_answer(SERIALIZED_ASCII) == FULL["answer"]


def test_prefixes_are_monotonic_prefixes_of_answer():
    for serialized in (SERIALIZED, SERIALIZED_ASCII):
        previous = ""
        for cut in range(len(serialized) + 1):
            part = partial_answer(serialized[:cut])
            assert FULL["answer"].startswith(part)
            assert part.startswith(previous)
            previous = part


def test_no_answer_field_yet():
    assert partial_answer('{"ans') == ""
    assert partial_answer("") == ""
