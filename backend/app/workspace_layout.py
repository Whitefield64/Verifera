"""The on-disk shape of the agent workspace, written down once.

Ingestion produces this layout and the agent tools consume it. Before this
module the two sides agreed through string literals sitting in different files
— a table header formatted in one place and parsed by a regex in another — so
rewording either half silently broke the other. Anything both sides need to
agree on belongs here.

Deliberately free of heavy imports: the API image has no document-parsing stack,
so this cannot reach into ingestion.

    <workspace>/
      _index.md                catalogue of every published document
      <doc_id>/
        document.md            full extraction
        summary.md             LLM summary, kept across re-ingestion
        meta.json              title, format, counts, gloss
        sections.json          section file -> title, pages, chunk_ids
        sections/NN-slug.md    reading unit, with inline chunk markers
        tables/table-NN.md     one table artifact, plus a best-effort .csv
"""

import re

INDEX_FILE = "_index.md"
DOCUMENT_FILE = "document.md"
SUMMARY_FILE = "summary.md"
META_FILE = "meta.json"
SECTIONS_INDEX_FILE = "sections.json"
SECTIONS_DIR = "sections"
TABLES_DIR = "tables"

# Paths the agent may read. An allowlist rather than a traversal check: the
# agent has no business anywhere else in the workspace.
READABLE_PATH = re.compile(
    rf"^({DOCUMENT_FILE}|{SUMMARY_FILE}|({SECTIONS_DIR}|{TABLES_DIR})/[A-Za-z0-9._-]+\.md)$"
)

DOC_ID = re.compile(r"[A-Za-z0-9_-]+")

# Table artifacts carry their page in the header. A markdown grid cannot be
# quoted verbatim, so the reader resolves the page back to the table chunks in
# Postgres, whose text is what the quote verifier compares against.
TABLE_PAGE = " (page {page})"
TABLE_PAGE_RE = re.compile(r"\(page (\d+)\)")


def table_header(index: int, doc_id: str, page: int | None) -> str:
    header = f"# Table {index} — {doc_id}"
    if page is not None:
        header += TABLE_PAGE.format(page=page)
    return header


def page_of_table(content: str) -> int | None:
    match = TABLE_PAGE_RE.search(content.split("\n", 1)[0])
    return int(match.group(1)) if match else None


# Markers put a citable chunk_id next to the exact text it covers, so a quote
# copied out of a section verifies against the chunk in the database.
def chunk_marker(chunk_id: str, page: int | None, kind: str) -> str:
    marker = f"<!-- chunk: {chunk_id}"
    if page is not None:
        marker += f" | page: {page}"
    if kind == "table":
        marker += " | kind: table"
    return marker + " -->"
