"""Parsing the agent's last turn. This is the seam where a good answer becomes
a bad one: a missed marker shows the user raw JSON, and a dropped citation
array silently strips the evidence off a correct answer."""

from app.agent_output import SOURCES_MARKER, extract, strip_inline_chunk_refs

CITATION = '{"citations": [{"chunk_id": "ai-act-en#0f3c1a2b4d5e6f70", "quote": "shall apply from 2 February 2025"}]}'


def test_marker_format_splits_answer_and_citations():
    text = f"The prohibitions apply from **2 February 2025**.\n\n{SOURCES_MARKER}\n```json\n{CITATION}\n```"
    answer, citations, method = extract(text)
    assert method == "marker"
    assert answer == "The prohibitions apply from **2 February 2025**."
    assert citations[0]["chunk_id"] == "ai-act-en#0f3c1a2b4d5e6f70"


def test_marker_tolerates_extra_dashes_and_spacing():
    text = f"Answer text here.\n\n-----  SOURCES  -----\n```json\n{CITATION}\n```"
    answer, citations, method = extract(text)
    assert method == "marker"
    assert answer == "Answer text here."
    assert len(citations) == 1


def test_prose_about_sources_is_not_cut_in_half():
    """A marker is a line of dashes, not the word appearing in a sentence."""
    text = "The sources of the obligation are Articles 16 and 17 of the Regulation."
    answer, _, method = extract(text)
    assert method == "raw"
    assert answer == text


def test_single_json_block_is_salvaged():
    text = '```json\n{"answer": "Fines reach 7% of turnover.", "citations": []}\n```'
    answer, citations, method = extract(text)
    assert method == "single_block"
    assert answer == "Fines reach 7% of turnover."
    assert citations == []


def test_malformed_citation_block_keeps_the_answer():
    text = f"A complete answer.\n\n{SOURCES_MARKER}\n```json\n{{not valid json\n```"
    answer, citations, method = extract(text)
    assert method == "marker"
    assert answer == "A complete answer."
    assert citations == []


def test_raw_text_never_shows_stray_fences():
    answer, citations, method = extract("```\nJust prose.\n```")
    assert method == "raw"
    assert "```" not in answer
    assert answer == "Just prose."


def test_inline_chunk_refs_are_scrubbed_without_welding_words():
    text = "The deadline (ai-act-en#0f3c1a2b4d5e6f70) is firm."
    assert strip_inline_chunk_refs(text) == "The deadline is firm."


def test_inline_chunk_refs_handle_lists_and_wide_brackets():
    text = "Both apply 【ai-act-en#0f3c1a2b4d5e6f70, gdpr-en#1111111111111111】 here."
    assert strip_inline_chunk_refs(text) == "Both apply here."


def test_a_hash_that_is_not_a_chunk_id_survives():
    text = "See issue #1234 and section #overview."
    assert strip_inline_chunk_refs(text) == text
