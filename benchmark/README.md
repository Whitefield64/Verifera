# Evaluation harness

`run.py` replays the scenarios of the active domain pack through **the same HTTP
endpoint the web app uses**. There is no separate evaluation code path, so what
gets measured is what ships.

It scores nothing and calls no second model. It saves transcripts; a reviewer
compares them against the rubric below and against the source documents. An
LLM judge would introduce a second thing that can be wrong, in the one place
that has to be trustworthy.

```bash
python3 benchmark/run.py --validate-only
python3 benchmark/run.py --backend-url http://localhost:8000/api/chat
python3 benchmark/run.py --item q19 --item q22        # one or a few
```

`--item` pulls in the earlier turns of a threaded scenario automatically, so a
follow-up is never replayed without the context it depends on.

## HTTP contract

```
POST <backend-url>
{"message": "...", "history": [{"role": "user"|"assistant", "content": "..."}]}

200
{"answer": "...", "citations": [...], "path": "rag"|"agent", "meta": {...}}
```

`answer` must be a string and `citations` a list; everything else is preserved
in the transcript untouched, so adding fields to `meta` never breaks the harness.

## Scenario schema

One JSON object per line in `packs/<pack>/benchmark.jsonl`:

| field | meaning |
|---|---|
| `id` | `q01`…`qNN`, consecutive |
| `domain` | topic label, must be declared in `pack.yaml` |
| `complexity` | `simple` \| `complex` |
| `thread`, `turn` | conversation id and 1-based turn, or `null`/`1` |
| `question` | what gets sent |
| `reference_answer` | what a correct answer must contain — a rubric, not a model answer |
| `must_cite` | documents the answer must draw on; empty means the corpus cannot answer |
| `expected_path` | `rag` \| `agent`, the routing this question should get |
| `notes` | why the item exists and what it is trying to catch |

## Scoring rubric

Each item is reviewed on four axes, independently:

**Content** — `COMPLETE` (every fact in `reference_answer` present and correct),
`PARTIAL` (correct but missing something the reference requires), `WRONG` (any
incorrect fact). For a `must_cite: []` item, declining to answer is `COMPLETE`
and answering anyway is `WRONG`, however plausible the answer sounds.

**Citations** — every document in `must_cite` must appear among the cited
`doc_id`s. Where the corpus holds the same instrument in several variants —
`ai-act-en`, `ai-act-en-pdf`, `ai-act-it` are one regulation in two formats and
two languages — a citation to any variant satisfies a requirement for another.

**Quote fidelity** — the fraction of returned citations with `verified: true`.
The backend checks each quote against the stored chunk text; an unverified
citation means the model paraphrased its own source.

**Routing** — `path` against `expected_path`. Recorded even when the answer is
right: a correct answer reached the slow way still costs time and money.

## The rule that makes this worth anything

**Scenarios are never edited to make transcripts look better.** If an item is
wrong, it gets reported and fixed as an error — visibly, in its own commit,
with the numbers re-measured. A benchmark that moves toward the system it
measures is decoration.
