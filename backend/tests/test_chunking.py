from pathlib import Path

from ingestion.chunking import build_chunks, chunk_id_for, clean_text
from ingestion.parsing import parse_document

SAMPLE_HTML = """<!doctype html>
<html><body>
<h1>UAIT PASTE — Scheda tecnica</h1>
<p>Pasta decolorante compatta. Schiarisce fino a 6 toni.</p>
<h2>Miscelazione</h2>
<p>Rapporto di miscelazione 1:2 con developer da 10 a 30 volumi.</p>
<p>Testo ripetuto per il test delle occorrenze.</p>
<p>Testo ripetuto per il test delle occorrenze.</p>
<table>
<tr><th>Volumi</th><th>Toni di schiaritura</th></tr>
<tr><td>10</td><td>1-2</td></tr>
<tr><td>20</td><td>3-4</td></tr>
<tr><td>30</td><td>5-6</td></tr>
</table>
</body></html>
"""


def test_clean_text_strips_markdown_links():
    raw = (
        "I pigmenti di [melanina](//wiki/Melanin) si ossidano.\n[[ 21 ]](#cite_note-21)"
    )
    assert clean_text(raw) == "I pigmenti di melanina si ossidano.\n 21 ".strip()


def test_chunk_id_is_content_derived():
    first = chunk_id_for(
        "doc-1", "text", "stesso testo di prova sufficientemente lungo"
    )
    assert first == chunk_id_for(
        "doc-1", "text", "stesso testo di prova sufficientemente lungo"
    )
    assert first != chunk_id_for(
        "doc-1", "table", "stesso testo di prova sufficientemente lungo"
    )
    assert first != chunk_id_for(
        "doc-1", "text", "testo diverso di prova sufficientemente lungo"
    )
    assert first.startswith("doc-1#")


def test_reparse_produces_identical_chunk_ids(tmp_path: Path):
    sample = tmp_path / "uait-test.html"
    sample.write_text(SAMPLE_HTML, encoding="utf-8")

    first = build_chunks(parse_document(sample), "uait-test")
    second = build_chunks(parse_document(sample), "uait-test")

    assert first, "expected at least one chunk"
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert len({c.chunk_id for c in first}) == len(first), "chunk_id must be unique"

    texts = [c.text for c in first]
    repeated = [t for t in texts if "Testo ripetuto" in t]
    assert len(repeated) <= 1, "exact in-document duplicates must be dropped"
    assert all(len(c.text) >= 25 or c.kind == "table" for c in first), (
        "crumb chunks must be dropped"
    )


def test_table_chunks_are_flagged(tmp_path: Path):
    sample = tmp_path / "uait-test.html"
    sample.write_text(SAMPLE_HTML, encoding="utf-8")
    chunks = build_chunks(parse_document(sample), "uait-test")
    kinds = {c.kind for c in chunks}
    assert "table" in kinds
    assert "text" in kinds
