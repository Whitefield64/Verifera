# Document Assistant

Grounded question answering over a document corpus, where **every claim points
back to the exact passage it came from** — the page and bounding box in the
original PDF, or the highlighted span in the original HTML.

A reference implementation, not a library: clone it, swap the domain pack,
point it at your documents. The demo corpus is EU AI regulation.

## Why this exists

Most RAG demos answer with a footnote listing which document they used. That is
not verification, it is a citation-shaped object. Three things are different
here:

**The citation contract is load-bearing.** Every answer emits
`{doc_id, page, bbox, chunk_text, quote}`, and each quote is then checked
against the stored chunk text. Citations that fail come back `verified: false`
and render differently. A model that paraphrases its own source gets caught.

**The viewer shows the original artifact, not a reconstruction.** PDFs are drawn
by PDF.js with overlays on the stored bounding boxes; HTML and DOCX originals
are served exactly as captured, inside a sandboxed iframe that cannot run
scripts, and highlighted through the CSS Custom Highlight API.

**Two paths, and the routing is measured.** Simple lookups go to hybrid
retrieval. Questions that need navigation — comparing regimes, following a
cross-reference into another act, reading an annex — go to an agent that opens
documents. The evaluation set records which path each question *should* get, so
the router is a number rather than an opinion.

That third one is not theoretical. Asked for the maximum fine for a prohibited
AI practice, the retrieval path found Article 100 — the same conduct, but for
Union institutions — and answered EUR 1 500 000. The agent path opened Article
99 and answered EUR 35 000 000 or 7% of worldwide turnover. Both answers cited
faithfully. The difference was in what reached the model.

## How it works

```
ingest  → parse (Docling: text, page, bounding box)
        → tables extracted as their own artifacts
        → chunk (content-derived ids, stable across re-ingestion)
        → embed → pgvector
        → materialize a filesystem workspace (sections, tables, index)
        → publication gate: queryable only when the whole pipeline succeeded

query   → condense follow-ups into a standalone question
        → route
        → RAG:   hybrid search (vector + full-text, fused with RRF) → grounded answer
          agent: search, open sections, follow cross-references, then answer
        → verify every quote against its chunk
        → stream tokens, activity and citations over SSE
```

Orchestration is one compiled LangGraph `StateGraph`
([diagram](docs/graph.mmd)). LangGraph owns orchestration and nothing else:
retrieval, citation verification, chunking and the workspace are plain Python.
Storage is split three ways — Postgres for chunks and provenance, object storage
for untouched originals, and a regenerable filesystem workspace the agent
navigates.

More in [docs/architecture.md](docs/architecture.md).

## Quickstart

```bash
cp .env.example .env                                       # add OPENAI_API_KEY
docker compose up -d                                       # Postgres + pgvector, API on :8000

docker compose run --rm ingest python -m corpus sync       # fetch the demo corpus
docker compose run --rm ingest python -m ingestion ingest   # parse, chunk, embed, publish

cd frontend && npm install && npm run dev                  # UI on :3000
```

Parsing runs in a separate image on purpose: it pulls in torch and OpenCV, which
the request path never imports. Keeping them apart is the difference between a
~200 MB API image and a ~2 GB one.

Later, when the regulation moves:

```bash
docker compose run --rm ingest python -m corpus sync --check   # what changed upstream
```

## Domain packs

Nothing under `backend/app/` contains a domain string — not a prompt, not a
routing rule, not the title in the browser tab. All of it is data:

```
packs/eu-ai-act/
  pack.yaml         identity, UI copy, fixed replies, evaluation topics
  prompts/          answer, condense, router, summarize, agent
  router.yaml       regex signals that bypass the classifier
  sources.yaml      where the corpus comes from, and under what terms
  benchmark.jsonl   evaluation scenarios
```

Point `PACK_DIR` elsewhere and the system retargets, UI included — it reads its
copy from `GET /api/pack`. See [docs/domain-packs.md](docs/domain-packs.md).

## Evaluation

`benchmark/run.py` replays scenarios through the same HTTP endpoint the web app
uses, so what gets measured is what ships. It scores nothing and calls no second
model: it saves transcripts, and a reviewer reads them against the rubric and
the sources. An LLM judge would add a second thing that can be wrong in the one
place that has to be trustworthy.

```bash
python3 benchmark/run.py --validate-only
python3 benchmark/run.py --backend-url http://localhost:8000/api/chat
python3 benchmark/report.py benchmark/results/<file>.json
```

Measured numbers, with the date and commit they were taken at, are in
[docs/evaluation.md](docs/evaluation.md).

Scenarios are never edited to make transcripts look better. A benchmark that
moves toward the system it measures is decoration.

## The demo corpus

Public EU AI regulation: the AI Act in English and Italian and as the Official
Journal PDF, the acts it cross-references (GDPR, Data Act, DSA, Machinery
Regulation, Product Liability Directive, NIS2, Cyber Resilience Act), and NIST's
AI risk frameworks as a non-EU contrast.

Documents are **not redistributed here**. `python -m corpus sync` fetches them
from their publishers, and `packs/eu-ai-act/sources.yaml` records the reuse
terms of each — EUR-Lex under Decision 2011/833/EU, NIST as US government work.
ISO standards are deliberately excluded: they are not freely redistributable.

**This is a technical demonstration, not legal advice.** The corpus is a dated
snapshot; regulation changes, which is exactly why the fetcher exists.

## Stack

Python · FastAPI · Postgres + pgvector · Docling · LangGraph · Next.js +
react-pdf · OpenAI for embeddings and generation, configurable per task.
Tracing through Langfuse is opt-in and off by default — a public reference
implementation should not require an account with anyone to run.

## Not here yet

Persisted sessions and memory, retrieval-level permissions and multi-tenancy,
WhatsApp, CRM integration, audio. All additive. Multi-turn conversation works
today by sending history with the request.

## License

MIT for the code. The demo corpus keeps the terms of its sources — see
[LICENSE](LICENSE).
