# Evaluation

Run of 2026-08-12 at commit `d1a6740` plus the uncommitted working tree that
adds agent reasoning summaries, the condensed question on the retrieval path,
and the two citation-drop counters. 40 scenarios, corpus of 16 documents.
Transcripts: [`benchmark/results/v2-eu-ai-act.json`](../benchmark/results/v2-eu-ai-act.json).
The baseline run of 2026-08-09 is [`v1-eu-ai-act.json`](../benchmark/results/v1-eu-ai-act.json).

One fix landed *after* this run and is therefore not in these transcripts: the
raw chunk ids described under **Citations** below are still visible in them.

Reproduce the mechanical numbers with:

```bash
python3 benchmark/report.py benchmark/results/v2-eu-ai-act.json
```

Content grades below come from reading each transcript against its reference
answer and the source documents. There is no LLM judge.

## Headline

| | v1 (2026-08-09) | v2 (this run) |
|---|---|---|
| Content | 31 complete · 5 partial · 4 wrong | **30 complete · 7 partial · 3 wrong** |
| `must_cite` satisfied | 36 / 38 | 36 / 38 (q08, q39) |
| Quotes verified against source | 204 / 216 (94%) | 134 / 141 (**95%**) |
| Routing vs `expected_path` | 30 / 40 | 30 / 40 |
| Latency | median 8.1 s, max 81.7 s | **median 6.3 s, max 57.2 s** |
| Tokens for the whole run | 1 347 006 in · 48 130 out | 1 396 481 in · 37 200 out |

Fewer wrong answers, more partial ones, one fewer complete. Treating that as
movement would be over-reading it: five of the ten changed grades are the same
questions arriving at a different path.

## The result that matters, and it is not the good one

| path taken | complete | partial | wrong |
|---|---:|---:|---|
| RAG (22 questions) | 14 | 6 | 2 |
| Agent (18 questions) | 16 | 1 | **1** |

**The baseline's headline claim no longer holds.** In v1 every failure was on
the retrieval path and the agent answered 20/20. In this run the agent path
produced a wrong answer, and it is the worst kind:

**q32 — "How do the AI Act's fines compare with the GDPR's?"** The agent
reported the AI Act's tiers as **EUR 1 500 000** and **EUR 750 000**, and
concluded the AI Act's fines are **lower than the GDPR's**. Both figures come
from `ai-act-en#d7e884bc2e8b9377`, which is **Article 100** — fines on Union
institutions, bodies, offices and agencies. Article 99's EUR 35 000 000 / 7% is
in the corpus and the agent never opened it, across 13 tool calls. The true
answer is the opposite of the one given: the AI Act's top tier is higher than
the GDPR's.

This is the Article 99 / Article 100 confusion that motivated building the agent
path in the first place. In v1 it appeared as q39 on the retrieval path. It has
now appeared **on the agent path**, in a comparative question, and it is worse
there: the model wrote "based on the text available here" — it knew its excerpt
was partial — and delivered a confident comparative conclusion anyway instead of
saying it had not found the operative article. Three of its five quotes failed
verification.

The lesson is not that the agent path is bad. It is that **the agent path was
never immune, and 20/20 on twenty questions was too small a sample to conclude
that it was.** The tool budget lets it look; nothing makes it look *again* when
what it found does not answer the question asked.

## The failures, named

Retrieval failures — the fact is in the corpus and never reached the model:

- **q05 / q37** (partial) — the systemic-risk compute threshold. Both retrieved
  recital 111 (`sections/19-…`), which says a threshold "should be set", and not
  Article 51(2) (`sections/48-…`), which says **10^25**. Both correctly reported
  that they could not find the number. Unchanged from v1. Note that **q38, on
  the agent path, cited the right chunk in the same run** — same corpus, same
  question family, different path.
- **q08** (wrong) — a provider's pre-market obligations. Retrieval returned the
  Cyber Resilience Act's importer and distributor duties; the answer said the
  extracts do not contain the provider rule. Article 16 is in the corpus.
- **q36** (wrong) — "and what does that mean for the company that deploys it?".
  The condensed question was good — *"What does it mean for the company that
  deploys a high-risk AI system used to screen job applications?"* — and
  retrieval still returned Article 27 (fundamental-rights impact assessment) and
  a risk-management recital instead of Article 26. The deployer duties are in the
  corpus; q21 cited them on the agent path in this same run.
- **q18** (partial) — "what does NIS2 cover?" answered with the Directive's scope
  carve-outs: trust service providers, postal services, the public-administration
  exclusion. Never says what it actually does — measures for a high common level
  of cybersecurity, risk-management and reporting duties. Better than v1, where
  it returned a recital about nuclear power plants, and still not the answer.
- **q20** (partial) — "what is excluded from the scope of the AI Act?" returned
  only the military/defence/national-security exclusion. The scientific-R&D
  exclusion is in the corpus — q13 cited it in this same run — and the personal
  non-professional use exclusion is missing too.
- **q01** (partial) — the Article 3(1) definition of an 'AI system'. Retrieval
  returned recital 12 *about* the definition rather than the definition. The
  answer is faithful to what it was given and omits "may exhibit adaptiveness
  after deployment". Improved from v1, where it reproduced the pre-enactment
  "human-defined objectives" formulation; still not the enacted text.
- **q39** (partial) — the fine for a prohibited practice. Abstained, and
  correctly attributed EUR 1 500 000 to Union institutions rather than presenting
  it as the answer. **In v1 this was wrong**; abstention is the better failure.

Generation failures — the model had the passage and used the wrong part of it:

- **q32** (wrong) — above.
- **q24** (partial) — the AI Act / GDPR relation on automated decision-making.
  The overall "they stack rather than replace" answer is right, but on the GDPR
  side it cited the **Article 21 right to object**, not the **Article 22** right
  regarding decisions based solely on automated processing — which is what the
  question is about. The chunk it cited (`gdpr-en#6948bc1e`) contains Article 22:
  q10 quoted it correctly from the same chunk in this same run.

## Routing

30/40 again, but not the same ten:

| | count | items |
|---|---:|---|
| RAG → agent (over-trigger) | 4 | q02, q11, q17, q33 |
| Agent → RAG (under-trigger) | 6 | q20, q30, q35, q36, q37, q39 |

q07 and q12 now route correctly; q17 newly over-triggers and q36 newly
under-triggers. Under-triggering still costs correctness: **five of the six
under-triggered questions are partial or wrong** (all but q30). Over-triggering
still costs only money and latency — all four were answered completely.

The recommendation from v1 stands and is now better supported: if the router is
tuned, tune it to be less shy.

## Citations

- **36/38** items cited every document their reference requires. The two misses
  are q08 and q39, both of which abstained.
- **95% of quotes verified** (134/141). The unverified ones render differently in
  the UI; none passed silently as sourced.
- **q09 is fixed.** In v1 it produced the four correct NIST functions with an
  empty citations array. It now carries a verified citation. The inline-reference
  work closed it; no separate investigation was needed.
- The two new counters found **two problems in one run**: `q31` (agent) lost the
  support of one claim, and `q39` (rag) emitted a citation pointing at a chunk it
  had never been shown — which is precisely the diagnosis that was impossible to
  make in v1.
- **They also found a hole they could not see.** Two answers reached the reader
  with a raw chunk id in the prose: `q31` wrote
  `[[cyber-resilience-act#b41d4546e5762d8]]` (a 15-character digest) and `q39`
  wrote `[[d7e884bc2e8b9377]]` (no `doc_id`). A reference that is *almost*
  well-formed matched neither the numbering pattern nor the stripper's, so it
  survived both — and the counter, which used the same strict pattern, did not
  see it either. Fixed after this run: cleanup is now looser than matching, and
  the counter uses the loose form. The rule worth keeping is the general one —
  **a cleanup that shares its pattern with the matcher cannot catch what the
  matcher fails to recognise.**

## Abstention

Both `must_cite: []` items behaved correctly. q33 said the Regulation sets no
fee and cited the provisions on minimising burden for small providers; q34 said
the corpus does not identify Italy's designated authority. Neither invented a
number or a name. q39 and q08 also abstained, but there the fact *was* in the
corpus, which makes them failures rather than restraint.

## What this said to do next, and what happened

Item 4 below — fixing `tools/retrieval_eval.py` — turned out to be the whole
investigation, because the fixed tool immediately contradicted the diagnosis
above. See **v3** for the result. The original list, kept for the record:

1. **Retrieval is still the bottleneck.** Eight of the ten non-complete answers
   are retrieval failures, and the shape has not changed since v1: a question
   about an article retrieves the recital that discusses it. The experiment to
   run is still widening the best chunk to its whole section before generation —
   `sections.json` already carries the mapping. Expected targets: q01, q05, q08,
   q18, q20, q36, q37.
2. **Make the agent look twice.** q32 is a new failure mode and the only one on
   the agent path: it stopped on a passage that was adjacent to the answer, knew
   it was partial, and concluded anyway. This is the pack's prompt, not the code
   — the agent already has the budget to search again.
3. **Make the router less shy.** Unchanged from v1, still second: five of six
   under-triggers are partial or wrong. Do it after (1), because if (1) works the
   cost of under-triggering falls and the right setting changes.
4. **`tools/retrieval_eval.py` is still broken** and points at a benchmark file
   that no longer exists. It is the only way to test (1) without paying for a
   full run — a two-line fix that makes the most valuable experiment free to
   iterate on.

# v4 — the agent could not read its own map

Run of 2026-08-12, all 40 scenarios, no escalation model.
[`benchmark/results/v4-eu-ai-act.json`](../benchmark/results/v4-eu-ai-act.json).

| | v2 (baseline) | v4 |
|---|---|---|
| Content | 30 complete · 7 partial · 3 wrong | **35 complete · 5 partial · 0 wrong** |
| Routing vs `expected_path` | 30 / 40 | 30 / 40 |
| Latency | median 8.1 s | **median 5.7 s** |
| Cost of the run | $4.35 | **$1.26** |

Graded strictly. Two of the five partials (q03, q38) were called complete in v2
on substantively identical answers; on v2's own standard this run reads 37/3/0.
**35/5/0 is the honest number.**

## The section index was unreadable

The agent's map of a document is the section list `get_document_metadata`
returns. For the AI Act it looked like this:

```
In order to obtain the greatest benefits from AI systems while protecting fundam…
The fourth condition should be that the AI system is intended to perform a task…
```

74 sections named after the first sentence of a recital. **Nothing in the map
said "Article 26 — Obligations of deployers", so the agent could not go there
on purpose.** The PDF side failed differently: 140 sections, eleven of them
called `Whereas:`.

The cause is a clean split: Docling gives every PDF chunk a heading, and
EUR-Lex HTML gives none at all — 100% against 0% across the corpus. In the HTML
the number and title of a provision arrive as two ordinary short lines of body
text, which the old fallback read as prose.

`_section_title` now recognises them with a purely typographic rule — a short
line, no sentence-ending punctuation, opening like a title, two or more in a row.
Nothing in it knows what an "Article" is.

| | before | after |
|---|---|---|
| Sections whose title names a structure | 289/802 (36%) | **537/802 (67%)** |
| `ai-act-en` sections naming an article | 10/74 | **35/74** |

Repeated titles are numbered (`Whereas: (3/31)`), because eleven identical rows
are eleven rows the agent has to open at random.

Applied with `rebuild-workspace --skip-summaries`: no re-parse, no re-embed, no
chunk_id churn, so no citation already shown to anyone was invalidated.

## The escalation model was not buying quality

There is one model on the agent path now; `agent_escalation_model` and the
`needs_deep_reasoning` flag that drove it are gone rather than left set to the
small model. Measured on the nine questions that used to escalate: seven
answers equivalent, **two better** on the small
model — q26 lists the four extra Article 55 obligations that `gpt-5.5` missed,
and q38 cites `ai-act-en` rather than the PDF. Cost for those nine fell from
**$1.72 to $0.43** even though the small model uses 67% more tokens getting
there, because it is 6.7× cheaper per token.

Attribution caveat: the section titles had already been fixed when this was
measured. The claim supported is *"with a readable index, the small model does
what the large one did without one"* — not "the two models are equivalent".

## What the retrieval work has left

Parameter tuning is finished. Measured free against passage-level ground truth:
the current fusion is already right (vector alone 7/15, lexical alone 3/15,
fused 10/15, and no weighting beats 1:1), and **BM25 reranking makes it worse**
— 4/15 alone, never better than the baseline mixed in.

That negative result is informative rather than disappointing: the failure here
is vocabulary mismatch. The question says "what amount of training compute"; the
provision says "cumulative amount of computation used for its training measured
in floating point operations". BM25 scores rare-term overlap, which is exactly
what is absent.

A cross-encoder is what addresses vocabulary mismatch — published 2026 numbers
put hybrid RRF plus cross-encoder at Recall@5 0.816 against 0.695 for RRF alone.
It costs either torch in the API image (~200 MB → ~2 GB, against the deliberate
app/ingestion split) or an external reranking service with a per-query bill.
**Deferred on 2026-08-12 as an open trade, not an oversight.** It is the only
remaining lever on retrieval.

## Query condensing earns its place

Not a memory mechanism — history already travels with every request and reaches
the generator. It exists to produce something searchable: a vector index cannot
be handed "And what does that mean for the company that deploys it?".

On the three follow-up turns, gold passage in context: raw question 1/3,
**previous question concatenated with the raw one 0/3**, LLM-condensed 2/3. The
obvious cheap substitute is the worst of the three — it lengthens the text and
dilutes the embedding.

## Still open: answers that arrive with no citations

Four of forty (q11, q12, q14, q21) carried zero citations, and 41 inline
references resolved to nothing. Three were `answer_format: raw` — the agent
marked its sentences and ended in prose, never writing `---SOURCES---`, so every
citation was dropped. This is **worse than v3's one in 38**, and the likeliest
reason is that the small model honours the output format less reliably than
`gpt-5.5` did. That, rather than content, is the real price of dropping it.

The pack prompt already spells the rule out, including the consequence, so the
fix is in code: the `raw` branch now looks for the JSON block anyway, and a new
`ask_for_sources` node asks once for the block when the final turn omits it,
with `_final_text` joining it back onto the prose.

**Validated end to end, and the validation caught a bug.** Re-running the items
that had failed proved nothing — the fault is stochastic and did not recur. So it
was forced instead: with the sources contract temporarily removed from the pack
prompt, the agent must omit the block. The retry fired, the answer survived
intact, and **the citations were still lost** — because the nudge named the
format in prose rather than showing it, and the whole premise of asking is that
the model did not follow the format it was already given. With the nudge restating
the literal shape, the same forced run recovers 3 citations, all 3 verified, and
drops orphaned references from 21 to 1 — under a harder condition than production,
where the system prompt still carries the contract. On the normal path the node
stays out of the way: no retry, 6 citations, 6 verified.

What this does not establish is how often the fault occurs in a real run, or that
the retry covers every shape of it. That needs the next full run.

# v3 — the per-document cap was deleting the answer

Run of 2026-08-12, **38 of the 40 scenarios**. Transcripts:
[`benchmark/results/e3-eu-ai-act.json`](../benchmark/results/e3-eu-ai-act.json).
q23 and q28 were not run: both escalate to `gpt-5.5` and cost $2.17 of the
$3.71 the remaining scenarios would have cost. Both were complete in v2 and are
**unmeasured here** — the totals below are over 38 items, not 40.

| | v2 (same 38) | v3 |
|---|---|---|
| Content | 28 complete · 7 partial · 3 wrong | **34 complete · 4 partial · 0 wrong** |
| `must_cite` satisfied | 36 / 38 | 34 / 36 |
| Quotes verified | 95% | 92% |
| `inline_refs_unsupported` | 1 | **26** |
| Input tokens, same 14 items | 448 875 | 456 600 (1.02×) |

## What was measured, and why the earlier diagnosis was wrong

The doc-level tool, once fixed, reported **37/38** — near-perfect retrieval,
while eight of ten failures were retrieval failures. Both were true. `must_cite`
names *documents*, and the failure is "right document, wrong passage": a recital
of the AI Act satisfies `must_cite: ["ai-act-en"]` exactly as the article does.

Measured again at passage level — for 15 questions, the chunk that literally
contains the operative text of the reference answer — the baseline was **1/15**.

The ranks explain everything. The right chunks were ranked 6, 8, 10, 15, 17, 23:
**retrieved and then discarded by selection, not missed by ranking.** With
`per_doc_cap=3` the score was flat in `top_k` — 1/15 at k=12 and 1/15 at k=30.
A cliff, not a gradient.

Almost every question in the pack is about one act. The cap, sized to stop one
document starving the others, was throttling the only document that mattered,
and the first three chunks of that act are recitals. **The article was ranked
fourth or eighth and the cap deleted it before the model ever saw it.**

The corpus makes it worse: `ai-act-en`, `ai-act-en-pdf` and `ai-act-it` are the
same act three times, 46% of all chunks. Each holds its own quota. The exact-text
dedup in `select_top` never caught them because PDF extraction differs in
hyphenation and list prefixes — 9% of every context was a near-duplicate of
another slot.

## The changes kept

- `top_k` 12 → 16, `rrf_pool` 50 → 80, `per_doc_cap` 3 → **0**. Passage-level
  1/15 → 10/15. Doc-level coverage unchanged at 37/38: the starvation the cap
  guarded against does not occur at this k.
- `select_top` dedups **near**-duplicates (token Jaccard > 0.6), not identical
  text. Worth +2/15 on its own, and it lets k=16 reach what otherwise needed
  k=20 — four fewer chunks of context for the same result.
- The agent's `semantic_search` drops its `per_doc_cap=2`; k stays 8, so this
  costs nothing per call.

**Cost did not rise**: 1.02× input tokens on the same 14 items. The fast path
costs ~30% more per question, and the agent costs *less* on hard ones because it
finds the answer sooner — q24 went from 161k tokens over 13 tool calls to 45k
over 8.

## The wrong answers are gone

All three. **q32** is the one that matters: it was v2's new failure, the agent
reporting Article 100's figures as the AI Act's tiers and concluding the AI Act
fines lower than the GDPR. The cause was not the agent's judgement — it was
`per_doc_cap=2` on its search tool, which made Article 99 unreachable behind the
first two chunks of the act it was already reading. Thirteen tool calls and it
never saw Article 99 because it could not. The prompt fix proposed as item 2
above was never needed.

q08 also moved, but only from wrong to partial, and the failure changed kind:
Article 16 now arrives at rank 8 and the model answers from Article 9 instead.
**That one is a generation failure now, not a retrieval failure.**

## What got worse

- **q35: complete → partial**, the only content regression. Its good v2 answer
  leaned on the *Italian* copy for the Annex III employment case, and with the
  cap gone that chunk falls out of a context now full of English ones. The next
  turn of the same thread, q36, went from wrong to complete.
- **The citation contract regressed.** `inline_refs_unsupported` went 1 → 26 —
  sentences that reach the reader marked as cited with the citation gone, which
  is the more damaging of the two drop counters. 16 of the 26 are q12 alone: the
  agent ended in prose without writing `---SOURCES---`, so `extract` fell back to
  `raw` and lost every citation. q12 also changed path since v2, so part of this
  is router drift rather than retrieval.

  **This is not fixed.** A once-in-38 failure cannot be validated by re-running
  it once, and the budget for repetitions was not there. The blocker is
  diagnostic: `raw_citations` are not recorded in transcripts, so for q08, q29
  and q31 there is no way to tell a mistyped id from an omitted array entry.

- `must_cite` is 34/36 rather than 36/38, and both misses (q08, q12) are the
  zero-citation answers. Citing `ai-act-en-pdf` instead of `ai-act-en` costs
  nothing: `report.py` already groups the renditions of one act.

## What this says to do next

1. **Record `raw_citations` in the transcripts.** Everything else about the
   citation regression is guesswork until this exists. Free.
2. **Fix the `raw` fallback losing every citation.** When the agent omits the
   marker, all its citations are dropped in silence. Needs repeated runs to
   validate, not one.
3. **q08 and q20 are generation failures now, not retrieval ones.** Both have
   the right passage in context and answer from the wrong part of it. This is
   where the pack's prompt is worth working on — the target that item 2 of the
   v2 list was aiming at, now correctly located.
4. **Router: leave it alone for the moment.** Four of the six v2 under-triggers
   (q20, q35, q37, q39) are no longer failing on content, which is exactly the
   reason v1 and v2 both gave for tuning it after retrieval.
5. **Re-measure q23 and q28**, and re-grade q38: v2 called it complete, but its
   answer then and now gives Article 52's notification duty rather than Article
   55's obligations. The v2 grade looks generous.

## Cost, and a correction to the v2 figure

`gpt-5.4-mini` is $0.75/1M in and $4.50/1M out; `gpt-5.5` is $5.00/1M in and
$30.00/1M out. **A full 40-scenario run costs $4.43**, not the ~$1.5 the token
count alone suggests: `gpt-5.5` carries 46% of the input tokens at 6.7× the
price. That is what put a full run out of reach here, and it is the number to
plan against.

This investigation cost **$2.82**: $0.92 for 14 targeted scenarios and $1.89 for
24 more. Estimating from `evaluation.md`'s stated 18k–50k band for agent
questions under-predicted the first run by 3.4× — the hard agent questions run to
136k.

## Cost

One full run: **1.40M input / 37k output tokens** across `gpt-5.4-mini` and
`gpt-5.5`. Input rose ~4% against v1 and output fell ~23%, which is mostly
composition: two fewer questions took the agent path. Reasoning summaries are
billed as output and are included. Retrieval-path questions cost about 5k input
tokens each; agent-path questions ran 18k–50k.
