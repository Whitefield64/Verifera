"""Sections materialization: grouping, markers and sections.json must stay coherent."""

import json

from ingestion.workspace import MIN_SECTION_CHARS, _group_sections, materialize, write_sections


class _DocStub:
    """Quel poco di DoclingDocument che materialize() tocca."""

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
        _chunk(2, ["B"], chars=100),  # heading cambia e la sezione è già grande
        _chunk(3, ["B"], chars=100),
    ]
    sections = _group_sections(chunks)
    assert len(sections) == 2
    assert [c["chunk_id"] for c in sections[1]] == [chunks[1]["chunk_id"], chunks[2]["chunk_id"]]


def test_grouping_keeps_small_headings_together():
    chunks = [_chunk(i, [f"H{i}"], chars=100) for i in range(5)]
    assert len(_group_sections(chunks)) == 1  # tante intestazioni piccole → una sezione


def test_materialize_preserves_summary_and_gloss(tmp_path):
    doc_dir = tmp_path / "doc-x"
    doc_dir.mkdir()
    (doc_dir / "summary.md").write_text("riassunto LLM\n", encoding="utf-8")
    (doc_dir / "meta.json").write_text(
        json.dumps({"doc_id": "doc-x", "gloss": "Prodotto Y - 250 ml"}), encoding="utf-8"
    )

    materialize(_DocStub(), "doc-x", {"title": "Nuovo titolo"}, tmp_path)

    assert (doc_dir / "summary.md").read_text() == "riassunto LLM\n"
    meta = json.loads((doc_dir / "meta.json").read_text())
    assert meta["gloss"] == "Prodotto Y - 250 ml"
    assert meta["title"] == "Nuovo titolo"


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
