"""Activity previews and the state reducers.

The trail is what the user watches for the minute an agent run takes. Handing
the UI raw tool JSON would be the same as showing nothing.
"""

from types import SimpleNamespace

from app.agent_output import MISSING_SOURCES_NUDGE, SOURCES_MARKER
from app.graph import (
    _dropped_unseen,
    _final_text,
    needs_sources,
    _thought_of,
    _union,
    _unsupported_refs,
    tool_event,
)

CITATIONS = '{"citations": [{"chunk_id": "ai-act-en#0f3c1a2b4d5e6f70", "quote": "q"}]}'


def test_search_preview_names_the_documents_found():
    event = tool_event(
        "semantic_search",
        {"query": "annex III"},
        {"results": [
            {"doc_id": "ai-act-en", "page": None, "section_title": "Scope"},
            {"doc_id": "ai-act-en-pdf", "page": 127, "section_title": "High-risk"},
        ]},
    )
    assert event["title"] == "«annex III»"
    assert event["summary"] == "2 results"
    assert event["items"] == ["ai-act-en · Scope", "ai-act-en-pdf · p.127 · High-risk"]


def test_metadata_preview_counts_what_can_be_opened():
    event = tool_event(
        "get_document_metadata",
        {"doc_id": "ai-act-en"},
        {"sections": [{"title": "Scope"}, {"title": "Penalties"}], "tables": ["tables/table-01.md"]},
    )
    assert event["title"] == "ai-act-en"
    assert event["summary"] == "2 sections, 1 tables"
    assert event["items"] == ["Scope", "Penalties"]


def test_section_read_preview_reports_size():
    event = tool_event(
        "read_document_section",
        {"doc_id": "ai-act-en", "path": "sections/01-scope.md"},
        {"content": "x" * 1200},
    )
    assert event["title"] == "ai-act-en · sections/01-scope.md"
    assert event["summary"] == "1200 characters read"


def test_table_read_preview_reports_citable_chunks():
    event = tool_event(
        "read_document_section",
        {"doc_id": "cra", "path": "tables/table-01.md"},
        {"content": "grid", "citable_chunks": [{"chunk_id": "cra#1"}, {"chunk_id": "cra#2"}]},
    )
    assert event["summary"] == "2 citable chunks for the table"


def test_errors_surface_in_the_trail():
    event = tool_event("read_document_section", {"doc_id": "x", "path": "sections/y.md"}, {"error": "no such file"})
    assert event["summary"] == "error: no such file"
    assert event["items"] == []


def _turn(content, tool_calls=()):
    return SimpleNamespace(content=content, tool_calls=list(tool_calls))


def test_reasoning_summary_is_read_out_of_responses_blocks():
    """The Responses API nests the summary in a list, not a string."""
    response = _turn([
        {"type": "reasoning", "summary": [
            {"type": "summary_text", "text": "Annex III lists the high-risk uses."},
            {"type": "summary_text", "text": "Reading the section itself."},
        ]},
        {"type": "text", "text": "Let me look that up."},
    ])
    assert _thought_of(response) == (
        "Annex III lists the high-risk uses.\nReading the section itself."
    )


def test_prose_before_a_tool_call_stands_in_for_a_missing_summary():
    response = _turn("Searching for the penalty tiers first.", [{"name": "semantic_search"}])
    assert _thought_of(response) == "Searching for the penalty tiers first."


def test_the_final_turn_never_enters_the_trail():
    """Without tool calls the prose is the answer; showing it twice is a bug."""
    assert _thought_of(_turn("The prohibitions apply from 2 February 2025.")) == ""


def test_dropped_citations_are_counted_not_just_discarded():
    """A right answer with no citations has two causes: the model emitted none,
    or every id it emitted was wrong and silently dropped. The count separates
    them — without it q09 could only be guessed at."""
    raw = [
        {"chunk_id": "doc-1#aaaaaaaaaaaaaaaa", "quote": "seen"},
        {"chunk_id": "doc-9#ffffffffffffffff", "quote": "never retrieved"},
        "not even a dict",
    ]
    assert _dropped_unseen(raw, {"doc-1#aaaaaaaaaaaaaaaa"}) == 1
    assert _dropped_unseen(raw, set()) == 2
    assert _dropped_unseen([], {"doc-1#aaaaaaaaaaaaaaaa"}) == 0


def test_claims_that_lose_their_support_are_counted():
    """A reference numbering left alone is a sentence whose citation did not
    survive: the stripper is about to remove it and the claim reaches the reader
    looking unsourced. Numbers are already-resolved references, not losses."""
    assert _unsupported_refs("Applies from 2025. [[1]] Fines reach 7%. [[2]]") == 0
    assert _unsupported_refs("Fines reach 7%. [[doc-1#aaaaaaaaaaaaaaaa]]") == 1
    assert _unsupported_refs("Applies from 2025. [[1]] Fines. [[doc-2#bbbbbbbbbbbbbbbb]]") == 1


def test_seen_chunks_merge_across_steps_without_duplicates():
    """Every tool call adds to the same record; order must be stable for tests."""
    assert _union(["b", "a"], ["a", "c"]) == ["a", "b", "c"]


def test_a_retried_sources_block_is_joined_back_to_its_answer():
    """The retry is asked for the block alone, so the prose it belongs to is
    the turn before the nudge. Reading only the last message would publish the
    citations and throw the answer away."""
    messages = [
        SimpleNamespace(content="The prohibitions apply from 2 February 2025."),
        SimpleNamespace(content=MISSING_SOURCES_NUDGE),
        SimpleNamespace(content=f"{SOURCES_MARKER}\n```json\n{CITATIONS}\n```"),
    ]
    text = _final_text({"messages": messages, "sources_retried": True})
    assert "The prohibitions apply from 2 February 2025." in text
    assert SOURCES_MARKER in text


def test_without_a_retry_the_last_turn_is_the_whole_answer():
    messages = [SimpleNamespace(content="Only this.")]
    assert _final_text({"messages": messages}) == "Only this."


def test_an_answer_without_its_sources_is_sent_back_once():
    """The whole point of the retry: prose carrying inline references and no
    citations array would otherwise publish claims with nothing behind them."""
    unsupported = [
        SimpleNamespace(content="Fines reach EUR 35 000 000 [[ai-act-en#0f3c1a2b4d5e6f70]].")
    ]
    assert needs_sources({"messages": unsupported})
    # asked once and no more, whatever came back
    assert not needs_sources({"messages": unsupported, "sources_retried": True})


def test_a_turn_that_carries_its_sources_goes_straight_out():
    complete = [SimpleNamespace(content=f"Fines reach EUR 35 000 000.\n\n{SOURCES_MARKER}\n```json\n{CITATIONS}\n```")]
    assert not needs_sources({"messages": complete})
    assert not needs_sources({"messages": []})
