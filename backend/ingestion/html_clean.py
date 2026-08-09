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


def _strip_noise_tags(raw: str) -> BeautifulSoup:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
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
