"""Sections materialization: grouping, markers and sections.json must stay coherent."""

import json

from ingestion.workspace import MIN_SECTION_CHARS, _group_sections, materialize, write_sections


class _DocStub:
    """The little of DoclingDocument that materialize() touches."""

    tables = []

    def export_to_markdown(self) -> str:
        return "# Documento\n\ntesto"


def _chunk(i: int, headings: list[str], chars: int = 400, kind: str = "text", page=None):
    return {
        "chunk_id": f"doc-x#{i:016d}",
        "kind": kind,
        "text": f"chunk {i} " + "x" * chars,
        "page": page,
        "headings": headings,
    }


def test_grouping_splits_on_heading_change_once_big_enough():
    chunks = [
        _chunk(1, ["A"], chars=MIN_SECTION_CHARS),
        _chunk(2, ["B"], chars=100),  # heading changes and the section is already big
        _chunk(3, ["B"], chars=100),
    ]
    sections = _group_sections(chunks)
    assert len(sections) == 2
    assert [c["chunk_id"] for c in sections[1]] == [chunks[1]["chunk_id"], chunks[2]["chunk_id"]]


def test_grouping_keeps_small_headings_together():
    chunks = [_chunk(i, [f"H{i}"], chars=100) for i in range(5)]
    assert len(_group_sections(chunks)) == 1  # many small headings collapse into one section


def test_materialize_writes_the_summary_it_is_given(tmp_path):
    materialize(
        _DocStub(),
        "doc-x",
        {"title": "Product sheet", "gloss": "Product Y - 250 ml"},
        tmp_path,
        "# Document\n\ntext",
        "an LLM summary",
    )
    doc_dir = tmp_path / "doc-x"
    assert (doc_dir / "summary.md").read_text() == "an LLM summary\n"
    assert (doc_dir / "document.md").read_text() == "# Document\n\ntext"
    meta = json.loads((doc_dir / "meta.json").read_text())
    assert meta["gloss"] == "Product Y - 250 ml"
    assert meta["title"] == "Product sheet"


def test_materialize_leaves_nothing_of_the_previous_version(tmp_path):
    """A summary describing the document as it used to be is worse than none:
    the agent reads the index and trusts it."""
    doc_dir = tmp_path / "doc-x"
    doc_dir.mkdir()
    (doc_dir / "summary.md").write_text("summary of the old version\n", encoding="utf-8")
    (doc_dir / "meta.json").write_text(
        json.dumps({"doc_id": "doc-x", "gloss": "the old gloss"}), encoding="utf-8"
    )
    (doc_dir / "stale.md").write_text("left over by hand\n", encoding="utf-8")

    materialize(_DocStub(), "doc-x", {"title": "New title"}, tmp_path, "# New\n")

    assert not (doc_dir / "stale.md").exists()
    assert not (doc_dir / "summary.md").exists()  # nothing was passed in, nothing is kept
    meta = json.loads((doc_dir / "meta.json").read_text())
    assert "gloss" not in meta
    assert meta["title"] == "New title"


def test_write_sections_markers_and_index(tmp_path):
    chunks = [
        _chunk(1, ["Uso"], chars=200, page=2),
        _chunk(2, ["Uso"], chars=200, kind="table", page=3),
    ]
    count = write_sections(tmp_path, "Scheda prodotto", chunks)
    assert count == 1

    index = json.loads((tmp_path / "sections.json").read_text())
    assert index[0]["chunk_ids"] == [chunks[0]["chunk_id"], chunks[1]["chunk_id"]]
    assert index[0]["pages"] == [2, 3]

    content = (tmp_path / index[0]["file"]).read_text()
    assert f"<!-- chunk: {chunks[0]['chunk_id']} | page: 2 -->" in content
    assert f"<!-- chunk: {chunks[1]['chunk_id']} | page: 3 | kind: table -->" in content
