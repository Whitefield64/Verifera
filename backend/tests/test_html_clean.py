from ingestion.html_clean import clean_html, text_projection, visible_text

NOISY_HTML = """<html><body>
<nav><ul><li>Home</li><li>Prodotti</li></ul></nav>
<div class="sf-menu"><a href="/colorazione">Colorazione</a></div>
<div id="cookie-banner">Accetta i cookie</div>
<main><h1>UAIT PASTE</h1><p>Pasta decolorante compatta, schiarisce fino a 6 toni.</p></main>
<footer>Privacy Policy</footer>
<script>var x = 1;</script>
</body></html>"""


def test_clean_html_strips_boilerplate_keeps_content():
    cleaned = clean_html(NOISY_HTML)
    assert "schiarisce fino a 6 toni" in cleaned
    assert "Accetta i cookie" not in cleaned
    assert "Privacy Policy" not in cleaned
    assert "Colorazione" not in cleaned  # class sf-menu
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
    text = visible_text("<body><p>contenuto</p><script>window.x=1</script></body>")
    assert "contenuto" in text
    assert "window.x" not in text


def test_text_projection_recovers_flat_text():
    projected = text_projection(NOISY_HTML)
    assert "<p>" in projected
    assert "schiarisce fino a 6 toni" in projected
    assert "var x" not in projected


def test_text_projection_escapes_markup():
    projected = text_projection("<body><p>2 &lt; 3 &amp; ok</p></body>")
    assert "&lt;" in projected and "&amp;" in projected
