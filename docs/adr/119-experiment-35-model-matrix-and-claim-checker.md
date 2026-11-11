# ADR-119: Experiment 35 Model Matrix and Claim Checker

- **Date:** 2026-11-10
- **Status:** Proposed (accepted at the Experiment 35 freeze, gate G7). Amended 2026-11-11 twice (A1 to A6, then A7), see the end of this record.
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-103](103-experiments-run-local-models-through-llama-cpp-gguf.md), change
  `experiment-35-full-document-rag-benchmark` (design D3, D4),
  archived change `2026-11-09-pre-exp35-harness-and-answer-fixes` (design D9, D10, D12)

## Context

Experiment 35 is the benchmark for the first fellowship paper. Its arms
change retrieval only. The answer model, the Ragas judges and the claim
checker must stay the same in every arm, so they are not variables of the
comparison. They must also be good enough that they do not hide or invent a
difference between arms.

The plan of 2026-10-27 used local Qwen3-4B answers and a DeepSeek Ragas
judge. The plan of 2026-11-08 (archived design D12) used Clef-Flash 9B as
the main claim checker, with GLM-5.3 and Granite Guardian 3.3 8B as a
confirmation panel.

The pre-freeze pod session (2026-11-10, RTX 4090, llama.cpp b11941, Q8_0)
scored each checker on the full LLM-AggreFact test split (29,320 rows) by
the leaderboard rule: balanced accuracy per dataset, then the plain mean.

| Checker | Average | RAGTruth | Published pair | Speed |
| --- | ---: | ---: | --- | --- |
| GLM-5.3, Z.AI, strategy `chat`, reasoning `low` | 76.9 | 85.1 | none | about 2.8 rows/s (hosted) |
| Granite Guardian 3.3 8B Q8_0, `granite_guardian` | 75.7 | 83.2 | 76.5 / 82.2 | 2.3 rows/s |
| Clef-Flash 9B Q8_0, `clef_flash` | 67.8 | 71.9 | 76.6 / 83.2 | 7.5 rows/s |

Granite reproduced its published pair within about 1 point. Clef-Flash did
not: it is 8.8 points below on the average and 11.3 points below on
RAGTruth. A run on the original weights checks whether the cause is the
question wording or the GGUF conversion.

## Decision

1. **Answers:** `deepseek/deepseek-v4.1-flash-1017` through OpenRouter, a
   named hosted reference (ADR-103), temperature 0, seed 20261101, one
   upstream host that honours `seed`. The freeze names the host.
2. **Ragas judge:** `openai/gpt-oss-120b` through OpenRouter, reasoning
   `low`, temperature 0, fixed seed, one pinned host. Cross-check:
   `openai/gpt-6.1-terra` on the 50 hand-checked items. No judge scores
   answers from its own model family.
3. **Selection rule, fixed before the main run:** the main claim checker is
   the candidate with the highest LLM-AggreFact average balanced accuracy on
   the full test split, by the leaderboard rule. A local checker replaces it
   only if it lands within 2 points of it on both the average and RAGTruth
   and also judges more rows per second. Both conditions must hold. The
   2-point allowance exists only to buy speed and cost. Granite Guardian is
   within 2 points (1.2 and 1.9) but slower (2.3 against about 2.8 rows per
   second), so it does not replace GLM-5.3.
4. **Main claim checker, by that rule:** GLM-5.3 through Z.AI, strategy
   `chat`, reasoning `low` set explicitly, temperature 0, seed 20261109.
   Reasoning `low` gave recall 1.0 and false rejection 0.0 on the
   Experiment 20 set of 120 triples.
5. **Second checker and fallback:** Granite Guardian 3.3 8B Q8_0. If
   GLM-5.3 calls fail, the run stops and resumes (`--resume`) when Z.AI is
   back; the runner never switches checker by itself. If GLM-5.3 is
   withdrawn for good, the operator names Granite main in a dated amendment.
   Granite has already judged every claim, so nothing is re-run.
6. **Clef-Flash as data:** Clef-Flash 9B Q8_0 is reported beside the others.
   It becomes main only by the selection rule (74.9 or higher and 83.1 or
   higher, full split, after a fix). A fix to its question goes into
   `core/answer/judges/clef_flash.py` as a new prompt-format version.
7. **No sampling:** all three checkers judge every claim in every arm and
   every run, so each has equal data. If Granite's speed strains the budget,
   the freeze adds pod time or a second pod; coverage is never cut. The
   report gives Cohen's kappa of Granite and of Clef-Flash against GLM-5.3
   on all claims.

Why 2 points: the claim checker sets the faithfulness scores. Its shortfall
against the reference checker must stay well below the protocol's minimum
detectable effect between arms (about 4 points), or it could hide or invent
a difference between arms. 2 points is half the MDE, on the full split,
where sampling noise is well under 1 point. The report calls two checkers
"on par" only at a gap of about 1 point or less, as MiniCheck (Tang, Laban
and Durrett, EMNLP 2024) does. Between 1 and 2 points it says "slightly
lower accuracy" with the numbers. It gives every checker's balanced
accuracy beside speed and cost.

## Consequences

### Positive

- The faithfulness metric uses the best-scoring checker that was measured on
  the full split, not a published number.
- A local checker can still take over by a fixed rule, set before the main run.
- Answers and judges come from different model families.

### Negative

- GLM-5.3 is hosted. Its claim checks leave the machine, and a later
  re-run depends on Z.AI keeping the same model behind the name.
- No published GLM-5.3 LLM-AggreFact figure exists to compare against. The
  figure is our own measurement, and the model may have seen LLM-AggreFact
  data in training.
- Three checkers on every claim cost more pod time than one main checker
  plus a sample. Granite is the slowest (2.3 rows per second).
- The Ragas cross-check is the same vendor family as the main judge, so the
  hand check is the only independent check of the Ragas judge.

### Neutral

- Hosted answers replace local Qwen3-4B. The answer model is the same in
  every arm, so the retrieval comparison does not change.
- The product default (`answer.verify_judge = chat`) does not change.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Clef-Flash as main checker (archived D12) | 67.8 / 71.9 on the full split, about 9 points below GLM-5.3 |
| Granite Guardian as main checker | 1.2 and 1.9 points below GLM-5.3, and slower; kept as second checker and fallback |
| Panel checkers on a sample of about 200 claims per arm | Unequal data between checkers; operator requires every claim |
| 1-point bar for Clef-Flash | Equivalent leaderboard models already differ by about 1 point |
| 3-point bar for Clef-Flash | Nears the 4-point MDE and spans a leaderboard tier (gpt-4o 75.9, gpt-4o-mini 74.0) |
| Local Qwen3-4B answers (2026-10-27 plan) | Operator chose hosted answers on 2026-11-08 |

## Amendment 2026-11-11: own-claims guard, Clef-Flash as second checker

The decisions above stay as written on 2026-11-10. This amendment replaces
decision 5, decision 6 and the Granite Guardian parts of decision 3 where it
says so. The operator accepted it on 2026-11-11, before the freeze.

**Why.** The pre-freeze smoke run (15 questions, 2 runs, all three checkers)
showed that a benchmark score does not predict how a checker behaves on our
datasets. On 143 FinanceBench claims Granite Guardian called 70% unsupported
(GLM-5.3: 22%). On 278 BioASQ claims it called 23% unsupported (GLM-5.3: 10%).
Its kappa against GLM-5.3 on these 421 claims is 0.40. The FreshStack smoke
claims do not count: the smoke pod had no FreshStack documents except the
overlay runbook, so every answer said the sources did not cover the question
(`datasets35.py` now stops when a gold document is missing). A FreshStack-only
rerun checks the guard on FreshStack before the freeze.

**A1. Own-claims guard (third condition of decision 3).** A local checker
replaces the main checker only if it also passes this guard. On the smoke-run
claims (all arms, both runs), its unsupported rate is within 15 points of the
main checker's on every dataset, and its Cohen's kappa against the main
checker is 0.4 or higher. The limits (15 points, kappa 0.4) were set after
the smoke data was seen. The main run checks the guard again on all claims,
and the report gives both results.

**A2. Result of the guard today.**

- Granite Guardian fails it on FinanceBench and on kappa. It is also slower
  (2.3 against about 2.8 rows per second).
- Clef-Flash passes it on BioASQ and FinanceBench (FinanceBench 32% against
  GLM-5.3's 22%, a 10-point gap; BioASQ 12% against 10%, a 2-point gap; kappa
  0.56). It fails the 2-point condition, so it does not replace GLM-5.3.
- The guard needs a result on every dataset. The Clef-Flash pass is
  provisional until the FreshStack rerun meets the guard. The freeze records a
  pass only after that. If the rerun fails the guard, Clef-Flash is not a
  fallback and the freeze must record a new decision on the fallback.

**A3. Second checker and fallback: Clef-Flash 9B Q8_0 (replaces decision 5).**
It agrees best with GLM-5.3 on our own claims (kappa 0.56, 88% same verdict).
Its unsupported rate stays within 10 points of GLM-5.3 on the two datasets
measured. If GLM-5.3 calls fail, the run stops and resumes (`--resume`) when
Z.AI is back. The runner never switches checker by itself.

**A4. Withdrawal of GLM-5.3 for good.**

- *After every arm and run has finished.* The operator names Clef-Flash main
  in a dated amendment. Clef-Flash has already judged every claim, so nothing
  is re-run. The report states its LLM-AggreFact gap (67.8 and 71.9 against
  76.9 and 85.1).
- *Before every arm and run has finished.* The operator names Clef-Flash main
  in a dated amendment. The runner then judges the remaining arms and runs, and
  the arm that stopped, with `--judges clef_flash,granite_guardian` (no
  `chat`). Every arm's faithfulness is then computed from Clef-Flash, so the
  arms stay comparable. The report lists each arm and run that has no GLM-5.3
  verdict. Any comparison with GLM-5.3 (kappa, unsupported rate) uses only the
  claims that both checkers judged.
- A fix to the Clef-Flash question goes into `core/answer/judges/clef_flash.py`
  as a new prompt-format version. It becomes main by the selection rule only
  after such a fix (74.9 or higher and 83.1 or higher, full split).

**A5. Granite Guardian as data (replaces decision 6).** It is reported beside
the others. It is never fallback or main in Experiment 35, because it fails
the guard.

**A6. Report (adds to decision 7).** The report gives Cohen's kappa of
Clef-Flash and of Granite against GLM-5.3 on all claims, and each checker's
unsupported rate per dataset.

**Consequences added.**

- The fallback scores about 9 points below GLM-5.3 on LLM-AggreFact. If
  GLM-5.3 is withdrawn, the faithfulness scores come from a checker with a
  lower benchmark score. Its agreement on our own claims is the reason it was
  chosen.
- The guard limits were set on 15 questions and 2 runs, after the data was
  seen.

**Alternatives added.**

| Option | Rejected Because |
|--------|-----------------|
| Granite Guardian as main checker | Also fails the own-claims guard (decision 3 rejected it on speed) |
| Granite Guardian as fallback (plan of 2026-11-10) | Rejects 70% of FinanceBench smoke claims (GLM-5.3: 22%); kappa 0.40 against GLM-5.3 |

## Amendment 2026-11-11 (later): FreshStack rerun result

This amendment completes A2. The text above stays as written.

**A7. Guard result on FreshStack.** A FreshStack-only smoke rerun ran on
2026-11-11 (pod `2elh5ji2og6d74`, commit `215835e2`). Each arm index held
66 FreshStack files. It used 5 questions, 6 arms and 2 runs. All three
checkers judged 383 claims (363 content claims, 20 abstentions).

| Claims | n | GLM-5.3 | Clef-Flash | Granite | Clef-Flash gap, kappa | Granite gap, kappa |
|--------|--:|--------:|-----------:|--------:|-----------------------|--------------------|
| All | 383 | 39.4% | 34.7% | 58.7% | -4.7 points, 0.62 | +19.3 points, 0.52 |
| Content only | 363 | 40.8% | 35.5% | 57.0% | -5.2 points, 0.62 | +16.3 points, 0.56 |

- Clef-Flash passes the guard on FreshStack. It now passes on all three
  datasets, so the pass in A2 is no longer provisional. Clef-Flash is the
  second checker and fallback (A3).
- Granite Guardian fails the guard on FreshStack too (gap above 15 points).
  A5 stays as written.
- The guard values are point estimates on 5 questions. Claims from one
  question repeat across arms and runs, so they are not independent. The
  main run checks the guard again on all claims (A1).
- One question (`77536364`) failed in 5 of 12 arm-runs. The answer step
  gave the question and the draft answer no room in a refine round. The
  fix is in `core/answer/synthesis.py` (PR #207). It does not change the
  evidence that each round receives.

Data: `DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/fs-rerun/`
(`fs_analyse.py`, `results/`).

## References

- Experiment 35 protocol, section 4.4:
  `experiments/35-full-rag-benchmark-2026-11-01/protocol.md`
- Pre-freeze outputs and SHA-256 sums:
  `DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/prefreeze-glm/` and
  `.../prefreeze-pod/`
- LLM-AggreFact leaderboard (read 2026-11-08); MiniCheck, arXiv 2404.10774
