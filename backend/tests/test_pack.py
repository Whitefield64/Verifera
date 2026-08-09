"""Domain pack loading: the seam that keeps the vertical out of the code."""

import pytest

from app import pack
from app.config import settings


@pytest.fixture
def temp_pack(tmp_path, monkeypatch):
    """Point the loader at a throwaway pack and clear its caches around the test."""

    def build(pack_yaml: str, router_yaml: str = "signals: []", prompts=("answer",)):
        (tmp_path / "prompts").mkdir(exist_ok=True)
        (tmp_path / "pack.yaml").write_text(pack_yaml, encoding="utf-8")
        (tmp_path / "router.yaml").write_text(router_yaml, encoding="utf-8")
        for name in prompts:
            (tmp_path / "prompts" / f"{name}.md").write_text(f"{name} body\n", encoding="utf-8")
        return tmp_path

    monkeypatch.setattr(settings, "pack_dir", tmp_path)
    for cached in (pack.manifest, pack._prompt_text, pack.routing_signals):
        cached.cache_clear()
    yield build
    for cached in (pack.manifest, pack._prompt_text, pack.routing_signals):
        cached.cache_clear()


MINIMAL = 'name: t\ntitle: T\ndomains: [a]\nmessages:\n  hello: "hi"\n'


def test_shipped_pack_is_complete():
    """The pack in the repo must load: check() is what runs at API startup."""
    pack.check()
    assert pack.manifest()["domains"]


def test_multiline_pattern_is_rejoined(temp_pack):
    """Patterns are literal blocks split across lines for readability. Neither
    the newline nor the YAML indentation may survive into the regex: a stray
    space would make every alternative after a line break need a leading space
    to match."""
    temp_pack(
        MINIMAL,
        router_yaml=(
            "signals:\n"
            "  - name: comparison\n"
            "    path: agent\n"
            "    escalate: true\n"
            "    pattern: |-\n"
            "      \\b(compare\n"
            "      |difference between)\\b\n"
        ),
    )
    (signal,) = pack.routing_signals()
    assert signal.name == "comparison"
    assert signal.escalate is True
    assert signal.pattern.search("please Compare these two")
    # the alternative that followed the line break, with nothing before it
    assert signal.pattern.match("difference between A and B")
    assert not signal.pattern.search("what is an AI system")


def test_missing_prompt_is_fatal(temp_pack):
    temp_pack(MINIMAL)
    with pytest.raises(pack.PackError, match="pack file missing"):
        pack.prompt("router")


def test_missing_required_key_is_fatal(temp_pack):
    temp_pack("name: t\ntitle: T\n")
    with pytest.raises(pack.PackError, match="domains"):
        pack.manifest()


def test_invalid_pattern_is_fatal(temp_pack):
    temp_pack(
        MINIMAL,
        router_yaml="signals:\n  - name: broken\n    path: agent\n    pattern: '([unclosed'\n",
    )
    with pytest.raises(pack.PackError, match="broken"):
        pack.routing_signals()


def test_message_collapses_folded_whitespace(temp_pack):
    temp_pack('name: t\ntitle: T\ndomains: [a]\nmessages:\n  hello: >-\n    one\n    two\n')
    assert pack.message("hello") == "one two"


def test_unknown_message_is_fatal(temp_pack):
    temp_pack(MINIMAL)
    with pytest.raises(pack.PackError, match="messages.nope"):
        pack.message("nope")
