"""Configuration loading: three optional files, and a default behind each one.

The property under test throughout is that absence is never an error. A clone
with an empty config/ has to answer questions; only a file that exists and is
malformed may stop the system.
"""

import pytest

from app import assistant
from app.config import settings


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Point the loader at a throwaway config dir, clearing caches around the test."""

    def write(**files: str):
        for name, body in files.items():
            (tmp_path / name.replace("_", ".")).write_text(body, encoding="utf-8")
        return tmp_path

    monkeypatch.setattr(settings, "config_dir", tmp_path)
    assistant.reset()
    yield write
    assistant.reset()


def test_empty_config_dir_still_works(config):
    """A fresh clone has nothing in config/, and must answer anyway."""
    config()
    assistant.check()
    assert assistant.identity() == assistant.DEFAULT_IDENTITY
    assert assistant.ui()["title"] == assistant.DEFAULT_UI["title"]
    assert assistant.message("no_context") == assistant.DEFAULT_MESSAGES["no_context"]
    assert assistant.routing_signals() == ()


def test_identity_reaches_every_prompt(config):
    config(identity_md="You are an assistant for widget manuals.")
    for name in assistant.PROMPT_NAMES:
        assert "You are an assistant for widget manuals." in assistant.prompt(name)
        assert "{identity}" not in assistant.prompt(name)


def test_shipped_example_identity_loads(config):
    """The example configuration is what `make example` copies into config/."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[3] / "example"
    config(
        identity_md=(example / "identity.md").read_text(encoding="utf-8"),
        assistant_yaml=(example / "assistant.yaml").read_text(encoding="utf-8"),
        routing_yaml=(example / "routing.yaml").read_text(encoding="utf-8"),
    )
    assistant.check()
    assert "EU AI regulation" in assistant.identity()
    assert assistant.ui()["title"] == "EU AI Regulation Assistant"
    assert assistant.routing_signals()


def test_partial_yaml_falls_back_key_by_key(config):
    config(assistant_yaml="title: Contract Assistant\n")
    ui = assistant.ui()
    assert ui["title"] == "Contract Assistant"
    assert ui["placeholder"] == assistant.DEFAULT_UI["placeholder"]
    assert assistant.message("no_answer") == assistant.DEFAULT_MESSAGES["no_answer"]


def test_multiline_pattern_is_rejoined(config):
    """Patterns are literal blocks split across lines for readability. Neither
    the newline nor the YAML indentation may survive into the regex: a stray
    space would make every alternative after a line break need a leading space
    to match."""
    config(
        routing_yaml=(
            "signals:\n"
            "  - name: comparison\n"
            "    path: agent\n"
            "    pattern: |-\n"
            "      \\b(compare\n"
            "      |difference between)\\b\n"
        )
    )
    (signal,) = assistant.routing_signals()
    assert signal.name == "comparison"
    assert signal.path == "agent"
    assert signal.pattern.search("please Compare these two")
    # the alternative that followed the line break, with nothing before it
    assert signal.pattern.match("difference between A and B")
    assert not signal.pattern.search("what is an AI system")


def test_invalid_pattern_is_fatal(config):
    config(routing_yaml="signals:\n  - name: broken\n    path: agent\n    pattern: '([unclosed'\n")
    with pytest.raises(assistant.ConfigError, match="broken"):
        assistant.routing_signals()


def test_malformed_yaml_is_fatal(config):
    config(assistant_yaml="- not\n- a mapping\n")
    with pytest.raises(assistant.ConfigError, match="must be a mapping"):
        assistant.ui()


def test_message_collapses_folded_whitespace(config):
    config(assistant_yaml="messages:\n  no_answer: >-\n    one\n    two\n")
    assert assistant.message("no_answer") == "one two"


def test_engine_prompts_are_all_present():
    """check() is what runs at API startup; the prompts ship with the engine."""
    assistant.check()
    for name in assistant.PROMPT_NAMES:
        assert assistant.prompt(name).strip()
