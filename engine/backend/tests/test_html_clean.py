from ingestion.html_clean import clean_html, text_projection, visible_text

NOISY_HTML = """<html><body>
<nav><ul><li>Home</li><li>Docs</li></ul></nav>
<div class="sf-menu"><a href="/products">Products</a></div>
<div id="cookie-banner">Accept cookies</div>
<main><h1>Article 6</h1><p>Classification rules for high-risk AI systems.</p></main>
<footer>Privacy Policy</footer>
<script>var x = 1;</script>
</body></html>"""


def test_clean_html_strips_boilerplate_keeps_content():
    cleaned = clean_html(NOISY_HTML)
    assert "Classification rules for high-risk AI systems." in cleaned
    assert "Accept cookies" not in cleaned
    assert "Privacy Policy" not in cleaned
    assert "Products" not in cleaned  # class sf-menu
    assert "var x" not in cleaned


def test_clean_html_never_removes_structural_containers():
    wiki_like = (
        '<html><body class="vector-feature-main-menu-pinned-disabled skin-vector">'
        "<main><p>Il perossido di idrogeno ossida la melanina dei capelli.</p></main>"
        "</body></html>"
    )
    assert "perossido" in clean_html(wiki_like)


def test_clean_html_falls_back_when_class_heuristic_is_destructive():
    destructive = (
        '<html><body><div class="page-menu-wrapper">'
        "<p>Tutto il contenuto della pagina vive dentro questo wrapper con classe menu.</p>"
        "</div></body></html>"
    )
    assert "contenuto della pagina" in clean_html(destructive)


def test_visible_text_ignores_scripts():
    text = visible_text("<body><p>body copy</p><script>window.x=1</script></body>")
    assert "body copy" in text
    assert "window.x" not in text


def test_text_projection_recovers_flat_text():
    projected = text_projection(NOISY_HTML)
    assert "<p>" in projected
    assert "Classification rules for high-risk AI systems." in projected
    assert "var x" not in projected


def test_text_projection_escapes_markup():
    projected = text_projection("<body><p>2 &lt; 3 &amp; ok</p></body>")
    assert "&lt;" in projected and "&amp;" in projected


# ── layout tables ──────────────────────────────────────────────────────────────
# Legal publishers wrap every recital and lettered point in a two-cell table.
# Left alone, those paragraphs get materialized as table artifacts and pushed
# through the table-specific citation path.

RECITAL = """<html><body><table><tr>
  <td>(1)</td><td><p>The Treaty provides for an internal market.</p></td>
</tr></table></body></html>"""

NESTED = """<html><body><table><tr><td>(45)</td><td>
  &lsquo;law enforcement authority&rsquo; means:
  <table><tr><td>(a)</td><td>any public authority;</td></tr>
         <tr><td>(b)</td><td>any other body.</td></tr></table>
</td></tr></table></body></html>"""

DATA_TABLE = """<html><body><table>
  <tr><th>Risk class</th><th>Obligation</th></tr>
  <tr><td>High</td><td>Conformity assessment</td></tr>
</table></body></html>"""

WIDE_ROW = "<html><body><table><tr>" + "".join(
    f"<td>c{i}</td>" for i in range(18)
) + "</tr></table></body></html>"


def test_two_cell_table_is_unwrapped_keeping_its_text():
    cleaned = clean_html(RECITAL)
    assert "<table" not in cleaned
    assert "The Treaty provides for an internal market." in cleaned
    assert "(1)" in cleaned


def test_nested_layout_tables_are_flattened_without_losing_points():
    cleaned = clean_html(NESTED)
    assert "<table" not in cleaned
    for fragment in ("(45)", "(a)", "any public authority;", "(b)", "any other body."):
        assert fragment in cleaned


def test_table_with_header_cells_is_kept():
    cleaned = clean_html(DATA_TABLE)
    assert "<table" in cleaned
    assert "Conformity assessment" in cleaned


def test_wide_single_row_is_kept_as_data():
    """Some publishers emit each line of a matrix as its own one-row table."""
    assert "<table" in clean_html(WIDE_ROW)


def test_narrow_single_row_is_treated_as_furniture():
    masthead = "<html><body><table><tr><td>3.6.2022</td><td>EN</td><td>L 152/1</td></tr></table></body></html>"
    cleaned = clean_html(masthead)
    assert "<table" not in cleaned
    assert "L 152/1" in cleaned
