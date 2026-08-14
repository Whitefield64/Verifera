"""HTML pre-processing: strip boilerplate (nav, footer, script) before Docling.

Scraped pages are full of menus and cookie banners that would otherwise get
indexed as content, and client-rendered pages keep their text where Docling's
HTML backend does not reach. This cleans the markup and, when the yield stays
too low against the visible text, falls back to a flat text projection.
"""

import re

from bs4 import BeautifulSoup

NOISE_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "iframe",
    "svg",
    "form",
    "nav",
    "header",
    "footer",
    "aside",
    "button",
    "input",
    "select",
    "canvas",
}
_NOISE_ATTR = re.compile(
    r"menu|nav\b|navigation|footer|cookie|breadcrumb|banner|sidebar|social|share|modal|popup",
    re.I,
)
# never dropped by the class-name heuristic: some sites put feature flags like
# "main-menu-pinned-disabled" on <body> itself
_PROTECTED_TAGS = {"html", "body", "main", "article"}
# below this fraction of the visible text, the parse counts as failed
MIN_YIELD = 0.3
# if class-based cleaning keeps less than this, it was too aggressive
_MIN_KEEP = 0.25
# a single-row table this wide is a row of data, not a masthead or a caption
WIDE_ROW_CELLS = 4


def _own_rows(table) -> list:
    """Rows belonging to this table rather than to one nested inside it."""
    return [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]


def _own_cells(row) -> list:
    return [c for c in row.find_all(["td", "th"]) if c.find_parent("tr") is row]


def _is_layout_table(table) -> bool:
    """True for the <table> as page-furniture idiom, not as data.

    Two things a real data table has and a layout table does not: header cells,
    and enough structure to relate values. A headerless table whose rows never
    hold more than two cells is the classic label/content wrapper, and a
    headerless single-row table usually relates nothing to anything.

    This matters more than it sounds: EUR-Lex wraps every recital and every
    lettered point in a two-cell table, so without this 96% of the "tables"
    found in a legal corpus are paragraphs in disguise — they would be
    materialized as table artifacts and pushed through the table-specific
    citation path.

    The single-row case stops short of WIDE_ROW_CELLS because some publishers
    emit each line of a matrix as its own one-row table. Those are data, and
    dropping structure needs at least as much evidence as keeping it.
    """
    if table.find("th"):
        return False
    rows = _own_rows(table)
    widest = max((len(_own_cells(row)) for row in rows), default=0)
    if len(rows) <= 1:
        return widest <= WIDE_ROW_CELLS
    return widest <= 2


def _unwrap_layout_tables(soup: BeautifulSoup) -> None:
    # Document order puts a parent table before the tables nested in it, so
    # walking backwards flattens the innermost ones first.
    for table in reversed(soup.find_all("table")):
        if not _is_layout_table(table):
            continue
        block = soup.new_tag("div")
        for row in _own_rows(table):
            paragraph = soup.new_tag("p")
            for cell in _own_cells(row):
                for child in list(cell.contents):
                    paragraph.append(child.extract())
                paragraph.append(" ")
            block.append(paragraph)
        table.replace_with(block)


def _strip_noise_tags(raw: str) -> BeautifulSoup:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    _unwrap_layout_tables(soup)
    return soup


def clean_html(raw: str) -> str:
    soup = _strip_noise_tags(raw)
    baseline = soup.get_text(" ", strip=True)
    for tag in soup.find_all(attrs={"class": _NOISE_ATTR}) + soup.find_all(
        attrs={"id": _NOISE_ATTR}
    ):
        if tag.name not in _PROTECTED_TAGS and not tag.decomposed:
            tag.decompose()
    kept = soup.get_text(" ", strip=True)
    if len(kept) < _MIN_KEEP * len(baseline):
        return str(_strip_noise_tags(raw))
    return str(soup)


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all({"script", "style", "noscript", "template"}):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def text_projection(html: str) -> str:
    """Last resort for markup Docling cannot traverse: the visible text
    reprojected as flat HTML, one <p> per block."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    blocks: list[str] = []
    for line in soup.get_text("\n", strip=True).splitlines():
        line = line.strip()
        if len(line) >= 3:
            blocks.append(line)
    paragraphs = "\n".join(f"<p>{_escape(b)}</p>" for b in blocks)
    return f"<html><body>{paragraphs}</body></html>"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
