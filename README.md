<p align="center">
  <img src="docs/images/verifera-logo.png" alt="Verifera" width="200">
</p>
<h1 align="center">Verifera</h1>

<p align="center">
  <b>A verifiable document agent for your knowledge base.</b><br>
  Every claim carries a quote, and every quote opens the original at the exact passage.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="docs/setup.md">Setup</a> ·
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/evaluation.md">Evaluation</a>
</p>

![An answer with numbered citations next to the source PDF, highlighted at the cited passage](docs/images/citation-highlight.png)

## What it does differently

At the core of the engine is a ReAct agent, not a retrieval pipeline with a chat
window on top. Adding tools extends it past question answering.

- **Navigation, not just retrieval.** Simple lookups take the classic RAG route,
  which is faster and sufficient. Anything that spans documents, reads a table or
  follows a cross-reference goes to the agent, which works the corpus the way a
  person would: scan the index, open a document, read the section, search again.
- **Stable provenance.** Every chunk gets an id derived from its own text, plus
  the page and bounding box it came from. Re-parse the document and the ids come
  back identical, so a citation keeps pointing at the same passage.
- **Verified quotes.** The model must copy the sentence it is relying on. The
  backend checks that the sentence really appears in the chunk it cited, and
  marks the ones that do.

## How it works

![Ingestion, storage and the two query paths](docs/diagrams/architecture.png)

Classic RAG is fast but shallow; an agent left alone with a search tool is slow
and expensive. Verifera runs both behind a single citation contract.

**Ingestion.** Documents enter through `data/raw/` and are parsed with their
layout preserved: headings, tables, and for PDFs the page and bounding box of
every element. They are then chunked, embedded and summarized. The result is
stored three ways: chunks and vectors in Postgres, the original file untouched
for the viewer, and a workspace materialized on disk, one directory per document
holding its summary, its tables, and its text split into readable sections with
chunk ids inlined. The workspace is what makes the agent path possible: the
corpus becomes something to navigate by reading rather than a bag of vectors.

**Query.** A lookup whose answer sits in one passage takes the RAG path: hybrid
search, then an answer from the retrieved chunks. A question that needs several
documents, a table or a cross-reference takes the agent path, which works through
the workspace with three tools (search, document metadata, read a section). Both
paths end at the same citation contract: every claim carries a chunk id and a
quote, and the backend drops whatever it cannot verify against the text the model
was actually shown.

**Example domain.** The engine is domain agnostic. Development and evaluation
used the EU AI Act together with fifteen related acts and frameworks, and a
benchmark of 40 scenarios with reference answers and expected citations, against
which chunking, routing and prompts were tuned. The
[published results](docs/evaluation.md) refer to that corpus.

[The architecture guide](docs/architecture.md) covers all of this in detail.

## Quickstart

Requires Docker and an OpenAI API key. Both paths below cost money: embeddings
for every chunk, and one summary per document.

```bash
git clone https://github.com/<you>/verifera && cd verifera
cp .env.example .env      # then put your key in OPENAI_API_KEY
```

**Demo corpus.** The EU AI Act documents, their configuration, and the setup the
published benchmark was run on:

```bash
make up          # Postgres, the API and the UI
make example     # downloads the documents, installs the demo config, ingests
```

**Your own documents.** Copy PDF, HTML or DOCX files into `data/raw/`, named the
way a reader should see them under a citation, then:

```bash
make up
make ingest      # turns data/raw/ into a corpus the assistant can answer from
```

Either way, the UI is on <http://localhost:3000>.

`data/raw/` is the only way documents get in. There is no other input, no
connector and no crawler; `make example` is a download script that puts files
there, so that a corpus of public legal texts does not have to live in this
repository.

On a new corpus the one file worth writing is `config/identity.md`: a few lines
of prose describing what the documents are and who asks about them.
[The setup guide](docs/setup.md) covers it and the two other optional files.

## License

[MIT](LICENSE). The documents `make example` downloads are not redistributed
here. They are fetched from their publishers, and `example/sources.txt` records
the reuse terms of each one.
