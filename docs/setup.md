# Setup

Everything here assumes Docker is running and `.env` has your `OPENAI_API_KEY`.

## The whole idea in one line

`data/raw/` is the only input. Put documents there, run `make ingest`, ask
questions. Nothing else is required.

## Your own documents

Copy PDF, HTML or DOCX files into `data/raw/`:

```
data/raw/
├── services-agreement-2024.pdf
├── security-policy.docx
└── onboarding-handbook.html
```

The filename becomes the document's identity — its id in the database, and the
name a reader sees under a citation. `services-agreement-2024.pdf` reads well
there; `scan_0004_final_FINAL.pdf` does not. Rename before you ingest.

Then:

```bash
make up
make ingest
```

`make ingest` parses each file, chunks it, embeds every chunk, writes a summary,
and publishes the result. It costs money and takes a few minutes per large
document. Run it again whenever you add files: documents already published with
identical content are skipped, so re-running is cheap and safe.

When it finishes, open <http://localhost:3000>.

## The demo corpus

```bash
make up
make example
```

`make example` copies the EU AI Act configuration into `config/`, downloads
sixteen documents into `data/raw/`, and ingests them. It is a plain script —
[`example/fetch.py`](../example/fetch.py) reading a list of filenames and URLs
from [`example/sources.txt`](../example/sources.txt) — and it exists only because
public legal texts should not live in a git repository. It is not a feature of
the system.

## Making it yours

Three optional files in `config/`. Every one of them has an engine default, so
an empty `config/` is a working system. All three are read once at startup:
after editing, run `docker compose restart api`.

### `config/identity.md` — who the assistant is

The one file that is genuinely about your documents. Plain prose, injected at the
top of every prompt the system sends:

```markdown
You are a documentation assistant for our internal engineering handbooks.
You answer questions from engineers who are looking for the current rule.

Be exact with version numbers, dates and the names of services. When a
document has been superseded, say so rather than quoting it as current.

You describe what the handbooks say. You do not invent process.
```

Write it the way you would brief a new colleague: what the corpus is, who asks,
what has to be exact, what to refuse. Ten lines is plenty.

Everything else in the prompts — how to format an answer, how to cite a passage,
how to use the tools — belongs to the engine and lives in
`engine/backend/app/prompts/`. That machinery is a contract with the code that
parses citations, so it is deliberately not yours to edit.

### `config/assistant.yaml` — what the reader sees

UI copy and the fixed replies. Drop any key and its default takes over:

```yaml
title: Engineering Handbook Assistant
locale: en

ui:
  heading: Engineering Handbook Assistant
  tagline: Ask about our handbooks — every answer cites the passage it came from.
  placeholder: Ask a question…
  suggestions:
    - What is our incident severity scale?
    - How long do we keep production logs?
```

### `config/routing.yaml` — routing shortcuts

Optional tuning. Every question goes through a small classifier that decides
between the fast path and the agent path; a regex here short-circuits that
decision when you already know the answer.

```yaml
signals:
  - name: comparison
    path: agent
    pattern: |-
      \b(compare|difference between|versus)\b
```

With no file, every question goes to the classifier and the system works fine.
Only add patterns you can justify against an evaluation set —
[`example/routing.yaml`](../example/routing.yaml) shows the ones tuned for the
demo corpus.

## Commands

| | |
|---|---|
| `make up` | Start Postgres, the API and the UI |
| `make ingest` | Turn everything in `data/raw/` into a queryable corpus |
| `make example` | Install the demo config, download its corpus, ingest it |
| `make status` | Documents by state, and how many chunks carry a bounding box |
| `make rebuild` | Repair the agent workspace from Postgres — no re-parse, no re-embed |
| `make check` | Everything CI runs |

## When something goes wrong

**A document failed to ingest.** It moves to `data/raw/_failed/` and the reason
is in the database — `make status` shows the counts. The most common cause is a
scanned PDF with no text layer; OCR is on by default but slow, and some scans are
simply unreadable.

**Answers cite the wrong document, or the agent opens the wrong thing.** Look at
`data/workspace/_index.md`. That is the list the agent chooses from, one line per
document. If two documents have glosses that do not distinguish them, the agent
cannot tell them apart either — a sentence in `config/identity.md` about how your
documents differ usually fixes it.

**The UI shows generic wording after editing config.** The files are read at
startup: `docker compose restart api`.

**Starting over.** Everything under `data/` except `raw/` is derived. To wipe the
corpus completely:

```bash
docker compose down -v          # drops the Postgres volume
rm -rf data/objects/* data/workspace/*
```

Then ingest again.
