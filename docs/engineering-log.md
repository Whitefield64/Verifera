# Engineering log

What was built, in what order, what went wrong, and what the numbers actually
were. Written as it happened, including the parts that did not work.

## How the work was split

Few phases, not many small steps, and each phase ends with something you can
actually evaluate. That is why ingestion is not a phase of its own: on its own
there is nothing to judge. You need retrieval and an endpoint before you can
look at a citation and say whether it is right.

The evaluation set is the stable verifier. It gets written before tuning, and
it never gets edited to make a transcript look better.

## Layout tables, or: 5588 tables and one of them was real

The first ingestion of the EU corpus reported 228 tables in a single
regulation. That is not a corpus with a lot of tables; that is a parser being
told paragraphs are tables.

EUR-Lex wraps every recital and every lettered point in a two-cell `<table>` —
`| (1) | The Treaty provides for… |` — purely for indentation. Measured across
the ten HTML documents: **5588 elements parsed as tables**. In one document, 76
of 86 chunks came out classified as `kind='table'`.

This matters beyond tidiness. Table chunks travel a different path: they are
materialized as separate artifacts, they are flagged to the model as tabular,
and reading one triggers the citable-chunk lookup that exists because a
markdown grid cannot be quoted verbatim. All of that was firing on prose.

The first attempt at a rule used `<th>` as the discriminator. Measurement
killed it: **not one** of the 5588 had a header cell. The second used column
count — but nested layout tables inflated it, because counting `<td>`
descendants counts the cells of tables inside tables. Counting only a row's own
cells gave the real distribution: 5383 with at most two cells per row, 198 with
three, 6 with four, and exactly one with eighteen.

The rule that shipped: no header cells, and never more than two cells in a row,
or a single row narrower than five cells. It unwraps 5584 of 5588 and preserves
**100% of the visible text** in every document. The single-row exemption stops
at five cells because that eighteen-cell row was a real matrix line — some
publishers emit each line of a table as its own one-row table, and dropping
structure should need at least as much evidence as keeping it.

## The change detector that always said "changed"

`corpus sync` re-fetches sources and compares. The obvious implementation —
hash the bytes — reported every document as changed on every run.

EUR-Lex injects a per-request Dynatrace analytics id into every HTML response.
Two fetches of the AI Act, seconds apart, differ by two bytes, both inside a
`<script>` tag. The legal text is identical.

So the digest is taken over the visible text, not the response: strip scripts
and styles, collapse whitespace, hash that. PDFs were checked and are
byte-stable, so they keep the plain hash. "Changed" now means the document
changed.

## EUR-Lex has no headings

Every HTML document in the corpus produced chunks with an empty `headings`
list. Not a parsing failure — the source has no `<h1>`–`<h6>` at all. Article
titles are paragraphs with CSS classes.

The consequence only showed up in the agent's activity trail, which was
printing `ai-act-en · ai-act-en` for every result. Sections had inherited the
document's own name, so `get_document_metadata` returned 74 identically-titled
sections for the agent to choose between. It coped by working from the PDF
version, where Docling's layout analysis does produce headings.

The fix is generic: when a document carries no heading structure, title a
section by its opening line, preferring a line that starts like a sentence
rather than mid-clause. It is the kind of defect that is invisible until you
read `sections.json`.

## Chunk counts differ by language, and that is correct

The AI Act in English produced 262 chunks; the same act in Italian produced
429. The extraction was complete in both cases — 595k characters against 582k
of visible text in the source.

The cause is the tokenizer. Chunks are capped at 512 tokens with `cl100k_base`,
which encodes Italian less efficiently than English, so the same character
count crosses the budget sooner: 2271 characters per chunk in English, 1526 in
Italian. Worth knowing before reading anything into per-document chunk counts
on a multilingual corpus.

## Replacing the agent runtime

The system this grew out of ran its agent path on an external coding-agent CLI
driven as a subprocess, with the tools exposed back to it over HTTP. The idea
was sound and the spike proved the interesting half: project documents onto a
filesystem as sections and tables, and an agent that navigates code will
navigate documents.

What the spike did not justify was keeping the runtime. Its costs were real:
node and a pinned global npm package inside a Python image; a parser bound to
an unversioned event schema; POSIX-only process-group kills, added after an
orphaned child held a pipe open and stalled a run for eighteen minutes; and
every tool existing twice, once in Python and once as a hand-written TypeScript
shim.

Moving to LangGraph deleted a category of problem rather than solving it. The
unauthenticated `/internal/tools` endpoint is gone, because there is no
callback. The module-level session registry is gone — it would have broken the
moment the API ran with more than one worker — because the run's state is graph
state. The shims are gone.

What the runtime enforced, the graph enforces: citation gating through a state
reducer, a two-tier budget, and a fallback to the RAG path on any failure. The
one genuinely nice trick is the hard cap: instead of refusing the call, the
model is simply invoked with no tools bound. Taking the tools away is a firmer
instruction than asking it to stop.

## Why the agent path earns its cost

The clearest example from this corpus. *What is the maximum fine for a
prohibited AI practice?*

The RAG path retrieved Article 100 — the same conduct, but as it applies to
Union institutions — and answered **EUR 1 500 000**. The agent path opened
Article 99 and answered **EUR 35 000 000 or 7% of worldwide annual turnover**.

Both answers were faithful to what the model had in front of it. Every citation
verified. The difference was entirely in what got in front of it, which is the
argument for routing rather than for a better prompt.

## Results

See [evaluation.md](evaluation.md) for the measured numbers, the date and the
commit they were taken at.
