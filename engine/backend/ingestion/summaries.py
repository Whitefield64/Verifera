"""The gloss and the summary the agent reads before deciding what to open.

The gloss is the one line each document gets in the workspace index, so it is
what the agent picks from: a corpus ingested without glosses is a corpus the
agent opens at random. That is why this runs as part of ingestion rather than as
a separate pass — the quality of the agent path depends on it.

Best-effort by design. A document whose summary call fails is still published;
it just carries a weaker index entry until the next `rebuild-workspace`.
"""

from app import assistant, llm

# Enough to characterise a document without paying for the whole thing: the
# opening of a document says what it is, and that is all a gloss needs.
SUMMARY_INPUT_CHARS = 15_000

SCHEMA = {
    "type": "object",
    "properties": {"gloss": {"type": "string"}, "summary": {"type": "string"}},
    "required": ["gloss", "summary"],
    "additionalProperties": False,
}


def generate(title: str, fmt: str, source_text: str) -> tuple[str, str]:
    """(gloss, summary) for a document. Returns ("", "") if the model call fails."""
    prompt = f"Document: {title} (format {fmt})\n\n{source_text[:SUMMARY_INPUT_CHARS]}"
    try:
        result = llm.complete_json(
            assistant.prompt("summarize"),
            [{"role": "user", "content": prompt}],
            "doc_summary",
            SCHEMA,
        )
    except Exception as error:  # noqa: BLE001 — a missing gloss must not fail an ingest
        print(f"warn {title}: could not summarize ({type(error).__name__}: {error})")
        return "", ""
    return result["gloss"].strip(), result["summary"].strip()
