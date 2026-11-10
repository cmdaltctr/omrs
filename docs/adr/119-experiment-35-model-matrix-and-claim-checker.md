# ADR-119: Experiment 35 Model Matrix and Claim Checker

- **Date:** 2026-11-10
- **Status:** Proposed (accepted at the Experiment 35 freeze, gate G7)
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

## References

- Experiment 35 protocol, section 4.4:
  `experiments/35-full-rag-benchmark-2026-11-01/protocol.md`
- Pre-freeze outputs and SHA-256 sums:
  `DATA/omrs/experiments/35-full-rag-benchmark-2026-11-01/prefreeze-glm/` and
  `.../prefreeze-pod/`
- LLM-AggreFact leaderboard (read 2026-11-08); MiniCheck, arXiv 2404.10774
