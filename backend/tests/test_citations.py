from dataclasses import dataclass

from app.citations import build_citations, normalize, quote_is_verified


def test_normalize_unifies_typography_and_whitespace():
    assert normalize("“COLOR  ULTIME” – 10’") == normalize('"color ultime" - 10\'')


def test_quote_verified_across_markdown_links():
    chunk = "Melanin pigments can be broken down with\n[oxidation](//en.wikipedia.org/wiki/Oxidation)\n."
    assert quote_is_verified(
        "Melanin pigments can be broken down with oxidation.", chunk
    )


def test_quote_verified_ignores_case_and_spacing():
    chunk = "La crema va miscelata 1:1 con IGORA ROYAL Oil Developer.\nTempo di posa: 30-45 minuti."
    assert quote_is_verified("miscelata 1:1 con igora royal oil developer", chunk)
    assert quote_is_verified("Tempo di posa: 30-45 minuti", chunk)


def test_quote_not_verified_when_absent_or_empty():
    chunk = "Schiarisce fino a 6 toni."
    assert not quote_is_verified("schiarisce fino a 7 toni", chunk)
    assert not quote_is_verified("", chunk)


@dataclass
class FakeChunk:
    chunk_id: str
    doc_id: str
    page: int | None
    bbox: dict | None
    text: str
    bboxes: list[dict] | None = None


def test_build_citations_drops_unknown_chunks_and_dedupes():
    retrieved = [
        FakeChunk("doc-1#aaa", "doc-1", 3, {"x": 1}, "Schiarisce fino a 6 toni.")
    ]
    raw = [
        {"chunk_id": "doc-1#aaa", "quote": "Schiarisce fino a 6 toni."},
        {"chunk_id": "doc-1#aaa", "quote": "Schiarisce fino a 6 toni."},
        {"chunk_id": "doc-9#zzz", "quote": "inventata"},
    ]
    citations = build_citations(raw, retrieved)
    assert len(citations) == 1
    assert citations[0]["doc_id"] == "doc-1"
    assert citations[0]["page"] == 3
    assert citations[0]["verified"] is True


def test_build_citations_flags_unfaithful_quote():
    retrieved = [
        FakeChunk("doc-1#aaa", "doc-1", None, None, "Schiarisce fino a 6 toni.")
    ]
    citations = build_citations(
        [{"chunk_id": "doc-1#aaa", "quote": "fino a 9 toni"}], retrieved
    )
    assert citations[0]["verified"] is False
