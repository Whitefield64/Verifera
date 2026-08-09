"""<base href> injection for scraped HTML docs that ship without one."""

import json

import pytest

from app.config import settings
from app.main import _DOC_ID, _source_urls, _with_base_href


@pytest.fixture(autouse=True)
def _clear_cache():
    _source_urls.cache_clear()
    yield
    _source_urls.cache_clear()


@pytest.fixture()
def manifest(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps([{"id": "reg-0001", "source_url": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "manifest_path", path)
    return path


def test_injects_base_href_when_missing(manifest):
    html = b"<!DOCTYPE html><html><head><title>x</title></head><body>hi</body></html>"
    out = _with_base_href(html, "reg-0001")
    assert b'<base href="https://eur-lex.europa.eu/eli/reg/2024/1689/oj">' in out
    assert out.index(b"<base") > out.index(b"<head")
    assert out.index(b"<base") < out.index(b"<title")


def test_leaves_existing_base_untouched(manifest):
    html = b'<html><head><base href="https://example.org/"></head><body>hi</body></html>'
    assert _with_base_href(html, "reg-0001") == html


def test_unknown_doc_id_is_a_noop(manifest):
    html = b"<html><head></head><body>hi</body></html>"
    assert _with_base_href(html, "reg-9999") == html


def test_missing_manifest_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "manifest_path", tmp_path / "absent.json")
    html = b"<html><head></head><body>hi</body></html>"
    assert _with_base_href(html, "reg-0001") == html


def test_no_head_tag_is_a_noop(manifest):
    html = b"<body>hi</body>"
    assert _with_base_href(html, "reg-0001") == html


@pytest.mark.parametrize(
    "doc_id,valid",
    [
        ("reg-0001", True),
        ("tech_prod-0001", True),
        ("../etc/passwd", False),
        ("reg-0001/../../secrets", False),
        ("mkt 0001", False),
    ],
)
def test_document_text_doc_id_pattern(doc_id: str, valid: bool):
    # stessa guardia di path traversal usata da /api/documents/{doc_id}/text
    assert bool(_DOC_ID.fullmatch(doc_id)) is valid
