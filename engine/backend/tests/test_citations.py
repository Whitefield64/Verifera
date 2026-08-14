from dataclasses import dataclass

from app.citations import (
    build_citations,
    normalize,
    number_inline_refs,
    quote_is_verified,
    render_stream,
)

# Real-shaped ids: the reference pattern requires a 16-hex digest.
A = "doc-1#aaaaaaaaaaaaaaaa"
B = "doc-2#bbbbbbbbbbbbbbbb"


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
    title: str | None = None


def test_stream_never_shows_a_malformed_reference():
    """The holding rule lets a closed reference through, and a malformed one is
    never claimed by numbering. Without this it reaches the screen and only
    finalize takes it away — after the reader has watched it arrive."""
    numbers: dict[str, int] = {}
    assert render_stream("Fines follow. [[d7e884bc2e8b9377]]", numbers) == "Fines follow. "
    assert numbers == {}
    assert render_stream(f"Applies. [[{A}]]", numbers) == "Applies. [[1]]"


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


def test_citation_title_is_the_document_name():
    """The name of the file is the name of the document, all the way to the
    citation. A chunk whose document row somehow has no title still gets a
    readable label rather than an empty one."""
    named = [FakeChunk("doc-1#aaa", "doc-1", 3, None, "text", title="contract-2024")]
    citations = build_citations([{"chunk_id": "doc-1#aaa", "quote": "text"}], named)
    assert citations[0]["title"] == "contract-2024"

    unnamed = [FakeChunk("doc-1#aaa", "doc-1", 3, None, "text", title=None)]
    citations = build_citations([{"chunk_id": "doc-1#aaa", "quote": "text"}], unnamed)
    assert citations[0]["title"] == "doc-1"


def cited(*chunk_ids: str) -> list[dict]:
    return [{"chunk_id": chunk_id, "quote": "q"} for chunk_id in chunk_ids]


def test_numbers_follow_first_appearance_and_repeat_for_the_same_passage():
    answer, citations = number_inline_refs(
        f"Second source here [[{B}]]. First one [[{A}]]. And again [[{B}]].",
        cited(A, B),
    )
    assert answer == "Second source here [[1]]. First one [[2]]. And again [[1]]."
    # Ordered by the number the reader meets, not by the order the model listed.
    assert [c["chunk_id"] for c in citations] == [B, A]
    assert [c["marker"] for c in citations] == [1, 2]


def test_reference_without_a_surviving_citation_is_left_to_be_stripped():
    answer, citations = number_inline_refs(f"Real [[{A}]]. Invented [[{B}]].", cited(A))
    assert answer == f"Real [[1]]. Invented [[{B}]]."
    assert [c["marker"] for c in citations] == [1]


def test_citation_the_prose_never_referenced_keeps_its_place_unnumbered():
    answer, citations = number_inline_refs(f"Only one marker [[{B}]].", cited(A, B))
    assert answer == "Only one marker [[1]]."
    assert [(c["chunk_id"], c["marker"]) for c in citations] == [(B, 1), (A, None)]


def test_two_quotes_from_one_chunk_share_a_number():
    _, citations = number_inline_refs(f"Claim [[{A}]].", cited(A, A))
    assert [c["marker"] for c in citations] == [1, 1]


def test_numbering_is_idempotent():
    once, citations = number_inline_refs(f"Claim [[{A}]].", cited(A))
    twice, _ = number_inline_refs(once, citations)
    assert twice == once


def test_stream_holds_back_a_reference_still_being_written():
    numbers: dict[str, int] = {}
    assert render_stream(f"Applies from 2025 [[{A[:12]}", numbers) == "Applies from 2025 "
    assert render_stream(f"Applies from 2025 [[{A}]].", numbers) == "Applies from 2025 [[1]]."


def test_stream_output_only_ever_grows_at_the_end():
    full = f"One [[{A}]] and two [[{B}]] and one again [[{A}]]."
    numbers: dict[str, int] = {}
    previous = ""
    for cut in range(len(full) + 1):
        rendered = render_stream(full[:cut], numbers)
        # What the graph emits is rendered[len(previous):], so anything already
        # sent must still be a prefix of what the next frame renders.
        if len(rendered) > len(previous):
            assert rendered.startswith(previous)
            previous = rendered
    assert previous == "One [[1]] and two [[2]] and one again [[1]]."


def test_stream_does_not_swallow_prose_that_merely_opens_brackets():
    numbers: dict[str, int] = {}
    assert render_stream("The annex [[sic]] lists", numbers) == "The annex [[sic]] lists"
    long_tail = "[[" + "x" * 120
    assert render_stream(long_tail, numbers) == long_tail
