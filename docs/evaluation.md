# Evaluation

Run of 2026-08-09 at commit `d16d416`, 40 scenarios, corpus of 16 documents /
2835 chunks. Transcripts: [`benchmark/results/v1-eu-ai-act.json`](../benchmark/results/v1-eu-ai-act.json).

Reproduce the mechanical numbers with:

```bash
python3 benchmark/report.py benchmark/results/v1-eu-ai-act.json
```

Content grades below come from reading each transcript against its reference
answer and the source documents. There is no LLM judge.

## Headline

| | |
|---|---|
| Content | **31 complete · 5 partial · 4 wrong** |
| `must_cite` satisfied | 36 / 38 |
| Quotes verified against source | 204 / 216 (**94%**) |
| Routing vs `expected_path` | 30 / 40 |
| Latency | median 8.1 s, max 81.7 s |
| Tokens for the whole run | 1 347 006 in · 48 130 out |

## The result that matters

Split the content grades by the path each question actually took:

| path taken | complete | partial | wrong |
|---|---:|---:|---:|
| RAG (20 questions) | 11 | 5 | 4 |
| Agent (20 questions) | **20** | 0 | 0 |

**Every failure in this run is on the retrieval path.** The agent path answered
all twenty of the questions it received completely.

That is not an argument that the agent is smarter. It is an argument about
what reaches the model. Every one of the nine RAG failures is a *retrieval*
failure: the fact is in the corpus, and the generation was faithful to the
extracts it was given.

- **q01** — asked for the Article 3(1) definition of an 'AI system', retrieval
  returned recitals *about* the definition, and the answer reproduced an older
  formulation ("human-defined objectives") that the enacted text does not use.
- **q05 / q37** — the systemic-risk compute threshold. Retrieval found the
  recital saying a threshold "should be set" but not Article 51 where it is
  10^25, and the system correctly reported that it could not find the number.
- **q08** — declined to list a provider's pre-market obligations, which are in
  Article 16.
- **q18** — asked what NIS2 covers, returned a recital about nuclear power
  plants.
- **q39** — asked for the maximum fine for a prohibited practice, answered
  **EUR 1 500 000**: that is Article 100, the same conduct for Union
  institutions, not Article 99's EUR 35 000 000 or 7%.

q39 is the same failure that motivated building the agent path in the first
place, and it reproduced under measurement. The identically-worded q02 was
routed to the agent and answered correctly. Same corpus, same model, same
question — different path.

## Routing

30/40, ten misses, and they are not symmetrical:

| | count | items | cost |
|---|---:|---|---|
| RAG → agent (over-trigger) | 5 | q02, q07, q11, q12, q33 | money and latency only — all five answered completely |
| Agent → RAG (under-trigger) | 5 | q20, q30, q35, q37, q39 | **three of the five are partial or wrong** |

Over-triggering is expensive; under-triggering is what costs correctness. If
the router is to be tuned, it should be tuned to be less shy, not less eager.

One over-trigger is worth naming: **q33** is an abstention item ("how much does
a notified body charge?"), and the classifier sent it to the agent, which spent
eight tool calls and ~50k tokens establishing that the corpus contains no fee
information. It reached the right answer the expensive way.

Of the ten misses, one came from a regex signal (`structured_lookup` on q02)
and nine from the classifier.

## Citations

- **36/38** items cited every document their reference requires. Both misses
  are informative: **q08** cited nothing because it wrongly abstained, and
  **q09** produced a completely correct answer — the four NIST functions — with
  **an empty citations array**. A right answer with no evidence still fails the
  contract this system exists to keep.
- **94% of returned quotes verified** against the stored chunk text. The 12
  unverified are flagged `verified: false` in the API and render differently in
  the UI; none of them silently passed as sourced.
- **0 citations were dropped** by the agent's citation gate across the whole
  run (`citations_dropped_unseen`), so the agent never tried to cite something
  it had not opened.

## Abstention

Both `must_cite: []` items behaved correctly: q33 and q34 stated that the
information is not in the documents rather than inventing a fee or naming a
plausible Italian authority. q34 did so on the retrieval path, q33 on the agent
path. Neither produced a number.

## What this says to do next

In priority order, and none of it done yet — these numbers are the baseline,
not a report on tuning:

1. **Retrieval is the bottleneck, not generation.** Nine of nine failures.
   Article-level questions retrieve the recitals that discuss a provision
   instead of the provision. Worth trying: retrieving whole sections rather
   than chunks for lookup questions, and weighting the enacting terms above the
   recitals.
2. **Make the router less shy.** Three wrong or partial answers came from
   questions that should have gone to the agent and did not.
3. **q09's empty citation array** is a bug-shaped result, not a tuning issue.

## Cost

Reported in tokens rather than currency, because prices change and a number in
a README rots. One full run: **1.35M input / 48k output tokens** across
`gpt-5.4-mini` and `gpt-5.5` (the latter only where the router escalates).
Retrieval-path questions cost about 5k input tokens each; agent-path questions
ran 18k–50k.
