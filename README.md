<p align="center">
  <img src="docs/images/verifera-logo.webp" alt="Verifera" width="120">
</p>

<h1 align="center">Verifera</h1>

<p align="center">
  Ask questions about your documents and get answers you can check —
  every claim carries a quote, and every quote opens the original at the exact passage.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="docs/setup.md">Setup</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/evaluation.md">Evaluation</a>
</p>

![An answer with numbered citations next to the source PDF, highlighted at the cited passage](docs/images/citation-highlight.png)

## What it does differently

Most "chat with your PDF" projects stop at an answer. The work here is in what
comes after it.

- **Stable provenance.** Every chunk gets an id derived from its own text, plus
  the page and bounding box it came from. Re-parse the document and the ids come
  back identical — so a citation keeps pointing at the same passage.
- **Hybrid retrieval.** Vector search and Postgres full-text, fused with
  reciprocal rank fusion. Exact terms — an article number, a product code — matter
  as much as semantic similarity in technical corpora.
- **Verified quotes.** The model must copy the sentence it is relying on. The
  backend checks that sentence really appears in the chunk it cited, and marks
  the ones that do. In the last run, 105 of 116 quotes checked out.
- **Measured, not demoed.** 40 scenarios with reference answers, expected
  citations and expected routing, replayed through the same HTTP endpoint the
  browser uses. [The numbers are published](docs/evaluation.md).

## Quickstart

You need Docker and an OpenAI API key. Both paths below cost money — embeddings
for every chunk, and one summary per document.

```bash
git clone https://github.com/<you>/verifera && cd verifera
cp .env.example .env      # then put your key in OPENAI_API_KEY
```

**Your own documents** — copy PDFs, HTML or DOCX files into `data/raw/`, then:

```bash
make up          # Postgres, the API and the UI
make ingest      # data/raw/ → a corpus the assistant can answer from
```

**The demo corpus** — the EU AI Act and fourteen acts and frameworks around it,
the corpus the published benchmark was measured on:

```bash
make up
make example     # downloads the documents, installs the demo config, ingests
```

Either way the UI is on <http://localhost:3000>. Ask it something.

`data/raw/` is the only way documents get in. There is no other input, no
connector and no crawler — `make example` is just a download script that puts
files there, so that a corpus of public legal texts does not have to live in this
repository.

To change how the assistant introduces itself, write `config/identity.md`.
That is the one file that is genuinely about *your* documents;
[the setup guide](docs/setup.md) covers it and the two other optional files.

## How it answers

![Ingestion, storage and the two query paths](docs/diagrams/architecture.png)

A question is condensed against the conversation, then routed. Simple lookups
take the RAG path — hybrid search, then an answer from the retrieved chunks. A
question that needs several documents, a table or a cross-reference takes the
agent path, where the model navigates a filesystem projection of the corpus with
three tools until it can answer. Both paths end at the same citation contract.
[The architecture guide](docs/architecture.md) walks through it.

## Measured

The last published run, 40 scenarios against the demo corpus:

| | |
|---|---|
| Quotes verified | 105 / 116 (91%) |
| Expected citations satisfied | 34 / 38 |
| Routing matched expectation | 30 / 40 |
| Latency | 5.7 s median, 37.1 s max |
| Cost | ~$1.26 for the run |

[What the numbers mean, and how to run it yourself](docs/evaluation.md).

## What it is not

Verifera is a local-first reference application, not a hosted product. It has no
authentication, no rate limiting and no isolation between users. Do not put the
API on the public internet without putting those in front of it.

Two claims worth stating precisely:

- **"Verified" means the quote is really in the cited passage** — not that the
  passage proves the claim. It catches invented quotes, not faulty reasoning.
- **Not every sentence gets a citation.** The system is built to answer from the
  sources or abstain, and it mostly does; in the last run four answers came back
  with no citations at all.

DOCX files are converted in the browser for display, so what you see is a
faithful rendering rather than the original bytes. PDF and HTML are shown as they
are.

## License

[MIT](LICENSE). The documents `make example` downloads are not redistributed
here — they are fetched from their publishers, and `example/sources.txt` records
the reuse terms of each one.
