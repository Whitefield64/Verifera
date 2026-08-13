# Architecture

Ground truth for the system. If the code and this file disagree, one of them is
a bug.

## The invariants

Everything else is negotiable. These are not:

1. **The citation contract is the interface.** Every answer emits
   `{doc_id, title, marker, page, bbox, chunk_text, quote}`. If this breaks,
   nothing else matters — the product is the verifiability, not the prose.
2. **Grounding happens upstream, rendering downstream.** Retrieval and
   orchestration are responsible for citation fidelity: tools return source
   identifiers, and generation may only cite what it actually read. The
   frontend highlights; it never decides what is true.
3. **Publication gate.** A document is queryable only when its whole pipeline
   succeeded — chunks, embeddings, provenance and workspace together. A
   half-ingested document is worse than a missing one, because it answers.
4. **Stable chunk ids.** Ids are derived from content, so re-ingesting a
   document does not invalidate citations already shown to someone. Stability
   holds *within one environment*: different BLAS builds change Docling's layout
   analysis, which changes the text a chunk contains and therefore its id. So
   re-ingest in the image you ingested with, and read a `check-stability` failure
   after an environment change as that change, not as a broken chunker.
5. **Everything that touches answers goes through the evaluation set.**

## Storage, three ways

| | holds | source of truth |
|---|---|---|
| Postgres + pgvector | chunks, vectors, provenance (page, bbox, offsets), processing state | yes |
| Object storage | the untouched original files the viewer renders | yes |
| Workspace | filesystem projection: sections, tables, per-document index | no — regenerable |

The split is the point. The viewer renders the **original artifact**, not a
reconstruction of it, which is why a highlight can be trusted. The workspace is
a navigation surface for the agent and can be rebuilt from Postgres at any time
with `python -m ingestion rebuild-workspace` — no re-parse, no re-embed, so
chunk ids and citations survive.

## Ingestion

```
data/raw/ (inbox)
  → parse            Docling: markdown + structure, page and bbox per block
  → tables           extracted as separate artifacts, not flattened into prose
  → chunk            semantic split, content-derived stable ids
  → embed            → pgvector
  → materialize      sections/, tables/, meta.json, sections.json, index
  → gate             all of the above succeeded → PUBLISHED, original → object storage
```

A failure at any step leaves the document `FAILED` with the error recorded, and
the file moves to `_failed/` for retry. Nothing partial becomes queryable.

Table artifacts are the fragile, valuable part: a number without its row and
column heading is worse than no number. They are kept as their own files, and
because a markdown grid cannot be quoted verbatim, reading one also returns the
table chunks from the database whose text the quote verifier can check against.

## Query

```
                     ┌── rag ──→ retrieve → generate ──┐
    condense → route ┤                                 ├→ finalize → END
                     └── agent ──→ agent ⇄ tools ──────┘
                                     │
                                     └─(failure)→ retrieve
```

One compiled LangGraph `StateGraph` ([graph.mmd](graph.mmd) is generated from
it). LangGraph owns orchestration and nothing else: retrieval, citation
verification, chunking and the workspace are plain Python, because they are the
parts worth reading and the parts that must not change when a framework does.

- **condense** turns a follow-up into a standalone question, once, so both paths
  and the retriever see the same thing.
- **route** short-circuits on strong regex signals from the pack, otherwise asks
  a small model. It never blocks: any failure routes to RAG.
- **RAG path** — hybrid search (vector + full-text, fused with reciprocal rank
  fusion, capped per document, deduplicated across documents) into a single
  grounded generation.
- **Agent path** — a tool loop over the workspace. Search is for orientation;
  the point is that the agent *opens* things, so what it consulted is known
  rather than inferred.
- **finalize** normalizes citations, verifies every quote against the stored
  chunk text, and numbers the references the model left in its prose.

### Inline references

The model marks the sentence it is citing by writing the chunk id in double
brackets right after it. `citations.number_inline_refs` replaces each one with a
footnote number and orders the citations to match, so the reader sees `¹` where
the claim is made instead of a list of file names at the end of a long answer.

Numbering is by **order of first appearance in the prose**, which is what makes
it work while streaming: a reference's number depends only on the text before
it, so `citations.render_stream` can assign it as the reference closes, long
before the citation array exists. The frontend renders a number it cannot yet
resolve as inert and grey, and it becomes clickable when the citations land — no
reflow, no burst of numbers at the end.

Two rules make the degradation quiet. A reference whose citation did not survive
verification is left in place for `agent_output.strip_inline_chunk_refs` to
remove, and numbering skips it rather than spending a number on it: the reader
never meets a gap in the sequence or a number pointing at someone else's source.
A citation the prose never referenced keeps its place at the end of the list,
unnumbered, rather than being dropped.

Citations sharing a chunk share a number. The reference identifies the passage,
and the passage is what gets highlighted, so two quotes from one chunk are one
place in the document — the frontend renders them as one entry with two quotes.

The readable document name under a citation comes from `data/manifest.json`, not
from the database: ingestion derives its title from the document's own content,
which for a legal corpus yields `2024/1689` or the doc_id itself. Correct as an
internal label, useless under a citation. `app/corpus_manifest.py` is the
request path's read-only view of that file.

### Why the agent path exists

A worked example from this corpus. Asked for the maximum fine for a prohibited
AI practice, the RAG path retrieved Article 100 — the same conduct, but for
Union institutions — and answered EUR 1 500 000. The agent path opened Article
99 and answered EUR 35 000 000 or 7% of worldwide turnover. Both answers were
faithful to what the model had in front of it. The difference was entirely in
what got in front of it.

### Guardrails

- **Citation gating.** The set of chunk ids the tools exposed lives in graph
  state; citations outside it are dropped and counted in
  `meta.citations_dropped_unseen`. An agent cannot cite a document it never
  opened.
- **Two-tier budget.** At the soft cap tools reply with an instruction to
  conclude. Past the hard cap, or past the wall clock, the model is invoked
  with no tools bound — taking the tools away is a firmer instruction than
  asking.
- **Fallback.** Any model failure on the agent path routes to RAG, so the
  endpoint never depends on the agent's health.

## Frontend

Split view: chat left, document right. Clicking a footnote number in the answer,
or its entry in the reference list under it, opens the original
and highlights the passage — PDFs by drawing overlays on the stored bounding
boxes, HTML and DOCX by serving the captured original inside a sandboxed iframe
with no script execution and highlighting through the CSS Custom Highlight API.

The sandbox is a security boundary, not a styling choice: the corpus is
third-party HTML and it does not get to run code in the user's session.

## What is deliberately not here

Sessions and persisted memory, cross-language answering as a feature rather
than a side effect, retrieval-level permissions and multi-tenancy, WhatsApp,
CRM integration, audio. All additive; none of them require rework of the above.
Multi-turn conversation works today by sending history with the request.
