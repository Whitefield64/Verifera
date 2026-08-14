"""The doc_id guard on /api/documents/{doc_id}/text."""

import pytest

from app.main import _DOC_ID


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
    # the path-traversal guard used by /api/documents/{doc_id}/text
    assert bool(_DOC_ID.fullmatch(doc_id)) is valid
