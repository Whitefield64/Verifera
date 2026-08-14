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

[`example/runs/v5-eu-ai-act.json`](../example/runs/v5-eu-ai-act.json), 40
scenarios against the demo corpus, measured on this layout:

| | v4 | v5 |
|---|---|---|
| Quotes verified | 105 / 116 (91%) | **133 / 141 (94%)** |
| Expected citations satisfied | 34 / 38 | **36 / 38** |
| Answers with no citation | 4 | **2** |
| Routing matched expectation | 30 / 40 | 30 / 40 |
| Path taken | 22 RAG, 18 agent | 24 RAG, 16 agent |
| Latency | 5.7 s / 37.1 s max | **5.1 s** / 48.0 s max |
| Tokens | 1.47 M in, 34 k out | **1.27 M in**, 36 k out |

v4 is kept alongside because the comparison is the point, but the two are not
strictly like for like: v5 was measured after the EU acts moved to the Cellar
endpoint, whose text is cleaner than the portal HTML v4 saw. Chunk boundaries,
and therefore chunk ids, differ between the two.

Three things worth reading off that table rather than around it.

**More citations and a higher share of them verified** — 141 against 116, at 94%
against 91%. The eight that failed verification sit on five questions and are
paraphrases rather than inventions, which is the check doing its job.

**Two answers came back with no citations at all**, down from four. The system
abstains more readily than it fabricates, which is the failure mode to prefer,
but it is still a failure mode.

**Routing is flat at 30/40, and the composition got worse where it costs.** The
misses split 3 over-triggering (RAG expected, agent taken) against 7
under-triggering. Over-triggering is cheap: those answers still come back
complete, just slower. Under-triggering is where the partial answers and the
48-second worst case live. The asymmetry says the same thing it said in v4 — a
routing bias toward the agent would buy quality at a predictable cost — and it
has not been acted on yet.

## Using it on your own corpus

Copy the shape, not the questions — they are about the EU AI Act and mean
nothing for your documents. Write the scenarios *before* you tune anything, or
you will tune toward whatever the system already does. Keep the ids consecutive
(`q01`…`qNN`), keep both paths represented, and include at least one question the
corpus genuinely cannot answer.

Point `run.py` at your own file with `--scenarios`. Grading rules for document
variants — a translation or a second format counting as the same document — live
in [`example/benchmark.yaml`](../example/benchmark.yaml).
