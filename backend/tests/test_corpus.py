"""Corpus sync: change detection is the whole point, so it gets the tests.

The failure this guards against is real and was observed against EUR-Lex: the
server injects a per-request analytics id into every HTML response, so hashing
raw bytes reports "changed" on every single run and the signal becomes noise.
"""

import hashlib

import pytest

from corpus.sync import Source, SourceError, content_digest, load_sources
from app.config import settings

PAGE = """
<html><head>
  <script src="/rum.js" data-config="agentId={aid}|rid=RID_{aid}"></script>
  <style>.x {{ color: red }}</style>
</head><body>
  <h1>Article 5</h1>
  <p>The following AI practices shall be prohibited.</p>
</body></html>
"""


def test_html_digest_ignores_per_request_markup():
    first = content_digest(PAGE.format(aid="e7d12690").encode(), "html")
    second = content_digest(PAGE.format(aid="82da9f35").encode(), "html")
    assert first == second


def test_html_digest_ignores_reflowed_whitespace():
    compact = b"<html><body><p>Prohibited practices</p></body></html>"
    spaced = b"<html><body>\n  <p>Prohibited\n     practices</p>\n</body></html>"
    assert content_digest(compact, "html") == content_digest(spaced, "html")


def test_html_digest_follows_the_text():
    before = content_digest(b"<html><body><p>fines up to 7%</p></body></html>", "html")
    after = content_digest(b"<html><body><p>fines up to 6%</p></body></html>", "html")
    assert before != after


def test_binary_digest_is_the_raw_bytes():
    data = b"%PDF-1.7 ..."
    assert content_digest(data, "pdf") == hashlib.sha256(data).hexdigest()


def test_filename_follows_the_format():
    source = Source("ai-act-en", "t", "u", "c", "html", "en", "l")
    assert source.filename == "ai-act-en.html"


def _write_sources(tmp_path, monkeypatch, body: str):
    (tmp_path / "sources.yaml").write_text(body, encoding="utf-8")
    monkeypatch.setattr(settings, "pack_dir", tmp_path)


ENTRY = (
    "  - id: {id}\n    title: t\n    url: http://x/\n"
    "    category: c\n    format: {fmt}\n    lang: en\n    license: l\n"
)


def test_duplicate_source_ids_are_fatal(tmp_path, monkeypatch):
    _write_sources(
        tmp_path,
        monkeypatch,
        "sources:\n" + ENTRY.format(id="dup", fmt="html") + ENTRY.format(id="dup", fmt="pdf"),
    )
    with pytest.raises(SourceError, match="duplicate"):
        load_sources()


def test_unsupported_format_is_fatal(tmp_path, monkeypatch):
    _write_sources(tmp_path, monkeypatch, "sources:\n" + ENTRY.format(id="x", fmt="epub"))
    with pytest.raises(SourceError, match="unsupported format"):
        load_sources()


def test_missing_source_list_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pack_dir", tmp_path)
    with pytest.raises(SourceError, match="no source list"):
        load_sources()


def test_shipped_sources_load():
    sources = load_sources()
    assert sources
    assert all(s.license for s in sources), "every source must record its reuse terms"
    assert all(s.url.startswith("https://") for s in sources)
