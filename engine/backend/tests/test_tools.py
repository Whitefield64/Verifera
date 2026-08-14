"""Agent tools: the budget, the path sandbox, and the record of what was seen.

That record is what makes the citation gate work — an answer may only cite
chunks the tools actually handed over — so it is tested here rather than
assumed.
"""

import json

import pytest

from app import tools
from app.config import settings


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    doc = tmp_path / "ai-act-en"
    (doc / "sections").mkdir(parents=True)
    (doc / "tables").mkdir()
    (doc / "meta.json").write_text(
        json.dumps({"doc_id": "ai-act-en", "title": "AI Act", "gloss": "Regulation (EU) 2024/1689", "format": "html", "page_count": 144}),
        encoding="utf-8",
    )
    (doc / "summary.md").write_text("Harmonised rules on artificial intelligence.\n", encoding="utf-8")
    (doc / "sections.json").write_text(
        json.dumps([
            {"file": "sections/01-scope.md", "title": "Scope", "pages": [1], "chunk_ids": ["ai-act-en#aaaa", "ai-act-en#bbbb"]},
        ]),
        encoding="utf-8",
    )
    (doc / "sections" / "01-scope.md").write_text("# Scope\n\ntext\n", encoding="utf-8")
    (doc / "tables" / "table-01.md").write_text("# Table 1 — ai-act-en (page 7)\n\n| a | b |\n", encoding="utf-8")
    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    return tmp_path


def run() -> tools.ToolRun:
    return tools.ToolRun(pool=None)


def test_soft_budget_tells_the_model_to_conclude(monkeypatch, workspace):
    monkeypatch.setattr(settings, "agent_max_tool_calls", 2)
    r = run()
    for _ in range(2):
        tools.call(r, "get_document_metadata", {"doc_id": "ai-act-en"})
    result = tools.call(r, "get_document_metadata", {"doc_id": "ai-act-en"})
    assert "budget" in result["error"].lower()
    assert "do NOT call any more tools" in result["error"]


def test_unknown_tool_is_reported_not_raised(workspace):
    assert "unknown tool" in tools.call(run(), "rm_rf", {})["error"]


def test_metadata_lists_sections_and_tables(workspace):
    result = tools.get_document_metadata("ai-act-en")
    assert result["gloss"] == "Regulation (EU) 2024/1689"
    assert result["sections"][0]["path"] == "sections/01-scope.md"
    assert result["tables"] == ["tables/table-01.md"]
    assert "Harmonised rules" in result["summary"]


def test_metadata_does_not_make_anything_citable(workspace):
    """Reading the index is not reading the document."""
    r = run()
    tools.call(r, "get_document_metadata", {"doc_id": "ai-act-en"})
    assert r.seen_chunk_ids == set()


def test_reading_a_section_makes_its_chunks_citable(workspace):
    r = run()
    result = tools.read_document_section(r, "ai-act-en", "sections/01-scope.md")
    assert result["pages"] == [1]
    assert r.seen_chunk_ids == {"ai-act-en#aaaa", "ai-act-en#bbbb"}


def test_path_traversal_is_refused(workspace):
    result = tools.read_document_section(run(), "ai-act-en", "../../../etc/passwd")
    assert "invalid path" in result["error"]


def test_doc_id_traversal_is_refused(workspace):
    result = tools.read_document_section(run(), "ai-act-en/../..", "sections/01-scope.md")
    assert "unknown document" in result["error"]


def test_unknown_document_is_reported(workspace):
    assert "unknown document" in tools.get_document_metadata("nope")["error"]


def test_missing_file_points_back_at_the_index(workspace):
    result = tools.read_document_section(run(), "ai-act-en", "sections/99-absent.md")
    assert "get_document_metadata" in result["error"]


def test_schemas_and_dispatcher_agree():
    """A tool the model can call but the dispatcher cannot route is a dead end."""
    for name in tools.TOOL_NAMES:
        assert "unknown tool" not in str(tools.call(tools.ToolRun(pool=None), name, {}))
