# Document Assistant

Grounded question answering over a document corpus, where **every claim points back
to the exact passage it came from** — the page and bounding box in the original PDF,
or the highlighted span in the original HTML.

Built as a reference implementation, not a library: clone it, swap the domain pack,
point it at your documents. The demo corpus is EU AI regulation.

> **Status: work in progress.** The RAG path, ingestion, citation contract and viewer
> work end to end. The agent path is being rebuilt on LangGraph, and the demo corpus
> and evaluation numbers land with it. This notice comes down when they do.

## Why this exists

Most RAG demos answer with a footnote listing which document they used. That is not
verification — it is a citation-shaped object. Two things make the difference here:

1. **The citation contract is load-bearing.** Every answer emits
   `{doc_id, page, bbox, chunk_text, quote}`. The quote is then checked against the
   stored chunk text; citations that do not survive the check are flagged `verified:
   false` in the API and rendered differently in the UI. A model that paraphrases
   its source gets caught.
2. **The viewer renders the original artifact, not a reconstruction.** PDFs are drawn
   by PDF.js with overlays on the stored bounding boxes; HTML and DOCX originals are
   served as they were captured, inside a sandboxed iframe with no script execution,
   and highlighted through the CSS Custom Highlight API.

## How it works

```
ingest ─→ parse (Docling: text + page + bbox)
       ─→ extract tables as separate artifacts
       ─→ chunk (content-derived, stable IDs across re-parses)
       ─→ embed → pgvector
       ─→ materialize a filesystem workspace (sections/, tables/, index)
       ─→ publication gate: queryable only when the whole pipeline succeeded

query  ─→ condense follow-ups into a standalone question
       ─→ route: single-document lookup, or something that needs navigation?
       ─→ RAG path: hybrid search (vector + full-text, fused with RRF) → grounded answer
       ─→ verify every quote against its chunk
       ─→ stream tokens and citations over SSE
```

Storage is split three ways on purpose: **Postgres/pgvector** holds chunks, vectors and
provenance; **object storage** holds the untouched originals the viewer renders; the
**workspace** is a regenerable filesystem projection the agent navigates. Only the first
two are sources of truth.

## Domain packs

Nothing under `backend/app/` contains a domain string. Prompts, routing signals, UI copy
and the evaluation set live in `packs/<name>/` as data:

```
packs/eu-ai-act/
  pack.yaml           title, locale, UI copy, evaluation topics
  prompts/            answer, condense, router, summarize
  router.yaml         regex short-circuits that bypass the LLM classifier
  benchmark.jsonl     evaluation scenarios
```

Point `PACK_DIR` at another directory and the whole system retargets — no Python edits.
See [docs/domain-packs.md](docs/domain-packs.md).

## Quickstart

```bash
cp .env.example .env          # add your OPENAI_API_KEY
docker compose up -d          # Postgres + pgvector, API on :8000

docker compose run --rm ingest python -m corpus sync      # fetch the demo corpus
docker compose run --rm ingest python -m ingestion ingest # parse, chunk, embed, publish

cd frontend && npm install && npm run dev                 # UI on :3000
```

Document parsing runs in a separate image on purpose: it pulls in torch and OpenCV,
which the request path never imports, and keeping them apart is the difference between
a ~200 MB API image and a ~2 GB one.

## Evaluation

`benchmark/run.py` replays scenarios through the same HTTP endpoint the web app uses,
so the evaluation exercises the real code path rather than a test harness of its own.
It scores nothing and calls no second model — it saves transcripts for review against
the rubric and the source documents.

```bash
python3 benchmark/run.py --validate-only
python3 benchmark/run.py --backend-url http://localhost:8000/api/chat
```

The scenarios are the stable verifier. They do not get edited to make transcripts look
better; a wrong scenario gets reported, not quietly adjusted.

## Stack

Python + FastAPI · Postgres + pgvector · Docling for parsing · LangGraph for
orchestration · Next.js + react-pdf for the split-view UI · OpenAI for embeddings and
generation (the model is configurable per task).

## The demo corpus

Public EU AI regulation: the AI Act and its annexes, the acts it cross-references,
Commission guidelines, and non-EU risk frameworks for contrast. Documents are **not
redistributed** in this repository — `python -m corpus sync` fetches them from their
official sources, and `packs/eu-ai-act/sources.yaml` records the reuse terms of each one.

**This is a technical demonstration, not legal advice.** The corpus is a dated snapshot;
regulation changes, which is exactly why the fetcher exists.

## License

MIT for the code. The demo corpus keeps the terms of its sources — see [LICENSE](LICENSE).
