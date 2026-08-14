# Evaluation

Optional. Skip this entirely if you just want to ask questions about your
documents — nothing in the system depends on it.

It matters for one reason: a retrieval system that is only demoed is a system
whose owner does not know whether a change made it better. Every tuning decision
in this repository — the value of `top_k`, dropping the per-document cap, using
the small model on the agent path — was made against the numbers below and would
otherwise have been a guess.

## What the set is

40 scenarios in [`example/benchmark.jsonl`](../example/benchmark.jsonl), written
against the demo corpus before any tuning. One JSON object per line:

```json
{
  "id": "q02",
  "topic": "penalties",
  "complexity": "simple",
  "thread": null,
  "turn": 1,
  "question": "What is the maximum administrative fine for engaging in a prohibited AI practice?",
  "reference_answer": "Article 99(3): up to EUR 35 000 000 or, if the offender is an undertaking, up to 7 % of its total worldwide annual turnover…",
  "must_cite": ["ai-act-en"],
  "expected_path": "rag",
  "notes": "Article 100 sets EUR 1 500 000 for Union institutions for the same conduct — answering with that figure is wrong."
}
```

The set is deliberately awkward. Six scenarios are multi-turn threads that only
work if the condenser resolves the reference. Two have an empty `must_cite`,
because the honest answer is "not in this corpus" and a system that always finds
something is not being tested. Both paths and both complexity levels are
represented, checked by `make check`.

## Running it

The harness replays each scenario through the same HTTP endpoint the browser
uses, so it measures the system, not a reimplementation of it.

```bash
# validate the set — no backend, no spend
python3 engine/benchmark/run.py --validate-only

# run it against a live backend
python3 engine/benchmark/run.py --backend-url http://localhost:8000/api/chat

# mechanical metrics from the transcript
python3 engine/benchmark/report.py data/eval-runs/<timestamp>.json
```

Transcripts land in `data/eval-runs/`, holding every request and response in
full. `--item q07` runs one scenario, pulling in the earlier turns of its thread.

## What is measured, and what is not

`report.py` computes only what needs no judgement: whether routing matched
`expected_path`, whether the expected documents were cited, how many quotes
passed verification, latency, tokens.

Whether an answer is *right* is not in the script and should not be. That is a
person reading the transcript against the reference answer and the source
documents. The `notes` field usually names the trap — the nearby article with the
different figure, the carve-out that must appear.

## The last published run

[`example/runs/v4-eu-ai-act.json`](../example/runs/v4-eu-ai-act.json), 40
scenarios against the demo corpus:

| | |
|---|---|
| Quotes verified | 105 / 116 (91%) |
| Expected citations satisfied | 34 / 38 |
| Routing matched expectation | 30 / 40 |
| Path taken | 22 RAG, 18 agent |
| Latency | 5.7 s median, 37.1 s max |
| Tokens | 1.47 M in, 34 k out |
| Cost | ~$1.26 |

Read by hand: 35 answers complete, 5 partial, 0 wrong.

Two things worth reading off that table rather than around it. Four answers came
back with no citations at all — the system abstains more readily than it
fabricates, which is the failure mode to prefer, but it is a failure mode. And
the ten routing misses split unevenly: questions sent to the agent when RAG would
have done still came back complete, while questions kept on RAG that needed the
agent are where the partial answers are. The asymmetry says a routing bias toward
the agent buys quality at a predictable cost in latency and tokens.

This run predates the current repository layout. Regenerate it before drawing
conclusions about the code as it stands today.

## Using it on your own corpus

Copy the shape, not the questions — they are about the EU AI Act and mean
nothing for your documents. Write the scenarios *before* you tune anything, or
you will tune toward whatever the system already does. Keep the ids consecutive
(`q01`…`qNN`), keep both paths represented, and include at least one question the
corpus genuinely cannot answer.

Point `run.py` at your own file with `--scenarios`. Grading rules for document
variants — a translation or a second format counting as the same document — live
in [`example/benchmark.yaml`](../example/benchmark.yaml).
