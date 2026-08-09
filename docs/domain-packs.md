# Domain packs

A domain pack is everything that makes this system about one subject rather
than another, kept as data. Nothing under `backend/app/` contains a domain
string — not a prompt, not a routing rule, not the title in the browser tab.

```
packs/<name>/
  pack.yaml         identity, UI copy, fixed replies, evaluation topics
  prompts/
    answer.md       grounded answering on the RAG path
    condense.md     rewriting a follow-up into a standalone question
    router.md       classifying a question as a lookup or a navigation job
    summarize.md    the gloss and summary written for each document at ingestion
    agent.md        the agent's instructions, tools and answer format
  router.yaml       regex signals that bypass the classifier
  sources.yaml      where the corpus comes from, and under what terms
  benchmark.jsonl   the evaluation scenarios
```

Point `PACK_DIR` at a directory and the whole system follows: the API title and
the UI copy (served over `GET /api/pack`), the prompts, the routing, the corpus
fetcher and the evaluation set.

## Building one

**1. Write `pack.yaml`.** `name`, `title` and `domains` are required; `domains`
is the vocabulary the evaluation scenarios classify themselves with, and a test
fails if a scenario uses a label you did not declare, or if you declare a label
no scenario exercises.

**2. Write the prompts.** Start from the ones here and change the subject
matter. Two of them carry more weight than they look:

- `summarize.md` writes the one-line gloss the agent sees for every document
  when it searches. If your corpus holds near-identical titles — translations,
  consolidated versions, annexes of one instrument — say so in this prompt and
  demand the gloss disambiguate. Without it the agent cannot tell two documents
  apart from a search result.
- `agent.md` may use `{max_tool_calls}` and `{sources_marker}`; both are filled
  in from code, so the marker the agent writes and the marker the parser looks
  for can never drift.

**3. Write `router.yaml`.** Only for signals strong enough that the classifier
should not get a say — an explicit comparison, a request for a plan, a lookup
into structured content. Everything else falls through to `prompts/router.md`.
Tune these against `expected_path` in your evaluation set, not against
intuition: they are cheap to write and easy to get subtly wrong.

**4. Write `sources.yaml`** and run `python -m corpus sync`, then
`python -m ingestion ingest`.

**5. Write `benchmark.jsonl`** — see [benchmark/README.md](../benchmark/README.md).
Do this before tuning anything, and keep both paths and both complexity levels
represented. Without it you are guessing.

## What stays fixed

The pack cannot change the shape of the system: the citation contract, the
retrieval strategy, the workspace layout, the graph. That is deliberate. A pack
that needed new code would not be a pack.

## Things that will bite you on a new corpus

Both of these came out of building the EU pack, and neither is specific to it:

**Layout tables.** Publishers use `<table>` for page furniture. In the ten HTML
documents of this corpus, 5588 elements parsed as tables and exactly one held
data — every recital was a two-cell table. Unhandled, they become table
artifacts and get routed through the table-specific citation path.
`ingestion/html_clean.py` unwraps them; if your source does something similar
but different, that is where to look.

**Missing heading structure.** EUR-Lex HTML has no `<h1>`–`<h6>` at all;
article titles are styled paragraphs. Sections then inherit the document's own
name and the agent gets a list of seventy identically-titled things to choose
between. The fallback is to title a section by its opening line — worth
checking on any new corpus, because it is invisible until you read
`sections.json`.
