"""Activity previews and the state reducers.

The trail is what the user watches for the minute an agent run takes. Handing
the UI raw tool JSON would be the same as showing nothing.
"""

from app.graph import _union, tool_event


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


def test_seen_chunks_merge_across_steps_without_duplicates():
    """Every tool call adds to the same record; order must be stable for tests."""
    assert _union(["b", "a"], ["a", "c"]) == ["a", "b", "c"]
