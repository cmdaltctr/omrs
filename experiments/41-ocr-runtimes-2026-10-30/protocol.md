# Experiment 41: OCR runtimes, GGUF against MLX

- **ID**: `41-ocr-runtimes-2026-10-30`
- **Date planned**: 2026-10-30
- **Status**: PLANNED. No install, download or OCR run has started.
- **Replaces the plan**: `41-mlx-ocr-backends-2026-10-06`, which exists only on branch `feat/experiment-41-mlx-ocr-backends`. Its page lists, gates and open decisions carry forward. Its scope does not.
- **Relation**: OpenSpec change `experiment-41-ocr-runtimes`; Experiment 37 findings F4 and F5; ADR-074 and ADR-103 (llama.cpp GGUF for local models)
- **Plan**: [`plan.json`](plan.json) (arms, page lists, gates, approvals, open decisions and items)
- **Number**: 41. Number 40 is reserved in NiftyPM for AIE-101.

## Question

Which runtime can serve each OCR engine without losing output quality?

The two engines are dots.mocr and PaddleOCR-VL. Each engine has a shipped backend. Experiment 37 measured both backends.

The first choice is llama.cpp, because ADR-103 names llama.cpp GGUF as the runtime for local models in experiments. MLX is a second option. MLX runs only on Apple silicon, and ADR-103 withdrew the MLX 8-bit fallback for decision models. MLX arms in this experiment are comparison arms. They show what MLX does. They cannot choose a runtime.

## Why this experiment exists

Experiment 37 accepted dots.mocr as the primary OCR engine and left two costs open.

1. PaddleOCR-VL on CPU timed out on 34 of 257 pages (finding F4).
2. dots.mocr peaked at 22.2 GiB of memory on PyTorch MPS (finding F5).

A two-page MLX test on 2026-10-05 ran PaddleOCR-VL in 6.6 s and 9.4 s per page, against 87 s and 133 s on CPU. That test was a scratch session. Its environment is gone, and it covered two pages of one paper. It supports no decision.

The operator decided on 2026-10-30 (option 1) that a runtime decision needs a llama.cpp arm. This plan follows that decision.

## Hypothesis, null and decision rule

**H1 (primary).** At least one llama.cpp GGUF arm of an engine meets gates C1 to C5 against that engine's shipped backend.

**Null.** For each engine, no llama.cpp GGUF arm meets all of C1 to C5 against the shipped backend.

**Decision rule.**

1. If a GGUF arm of dots.mocr passes, open a follow-up OpenSpec change for a llama.cpp path for dots.mocr. Use the passing arm with the better C4 and C5 results.
2. If a GGUF arm of PaddleOCR-VL passes, do the same for PaddleOCR-VL.
3. If no GGUF arm of an engine passes, that engine keeps its shipped backend.
4. An MLX arm never leads to an engine decision.
5. If an MLX arm passes and no GGUF arm passes, the report says so and stops.

## Arms

Each engine has five arms. Two arms are shipped or reused. Four arms are new. Each new arm is compared with its engine's shipped arm.

### dots.mocr

| Arm | Backend | Weights | Role | Source |
| --- | --- | --- | --- | --- |
| D0 | PyTorch MPS, bf16 | `rednote-hilab/dots.mocr` at `e539fbb5` | baseline (shipped) | reuse Experiment 37 output |
| D1 | MLX, bf16 | `mlx-community/dots.mocr-bf16` | comparison, no decision | new run |
| D2 | MLX, 8-bit | `mlx-community/dots.mocr-8bit` | comparison, no decision | new run |
| D3 | llama.cpp GGUF, bf16 | own conversion of `rednote-hilab/dots.mocr` at `e539fbb5` | runtime, decides | new run |
| D4 | llama.cpp GGUF, Q8_0 | own conversion, as D3, then quantised | runtime, decides | new run |

### PaddleOCR-VL

| Arm | Backend | Weights | Role | Source |
| --- | --- | --- | --- | --- |
| P0 | CPU | `PaddlePaddle/PaddleOCR-VL-1.6` (shipped) | baseline (shipped) | reuse Experiment 37 output |
| P1 | MLX, bf16 | own conversion of `PaddlePaddle/PaddleOCR-VL-1.6` | comparison, no decision | new run |
| P2 | MLX, 8-bit | own conversion, as P1, then quantised | comparison, no decision | new run |
| P3 | llama.cpp GGUF, 16-bit | `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` (official file) | runtime, decides | new run |
| P4 | llama.cpp GGUF, Q8_0 | own conversion of `PaddlePaddle/PaddleOCR-VL-1.6` (Apache-2.0) | runtime, decides | new run |

### Comparisons

- **Gated.** Each new arm against its engine's shipped arm: D1, D2, D3, D4 against D0; P1, P2, P3, P4 against P0.
- **Matched precision (reported).** GGUF against MLX at the same precision: D3 against D1 (16-bit against bf16), D4 against D2 (8-bit against Q8_0), P3 against P1, P4 against P2.

## Facts checked on 2026-10-30

These facts shaped the arms. Each one comes from a read-only check. Nothing was downloaded or run.

1. **dots.mocr has no official GGUF on the Hub.** Third-party GGUF files exist. Their provenance and licence are not checked, so this plan does not use them.
2. **The local llama.cpp binary names dots OCR, not dots.mocr.** Build 11941 (commit `19ff817fb`) contains the strings `dotsocr` and `dotsocr.cpp`. It contains no `dots.mocr` string. Conversion and load of dots.mocr may fail. A failure is a finding. It stops that arm only.
3. **PaddleOCR-VL GGUF has one main file and no 8-bit file.** `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` holds `PaddleOCR-VL-1.6-GGUF.gguf` (935,769,056 bytes) and `PaddleOCR-VL-1.6-GGUF-mmproj.gguf` (881,770,560 bytes). The name has no quant label. The size suggests 16-bit weights for a 0.9B model. The tensor type is read from the header at download. The repository README names `PaddleOCR-VL-1.6.gguf`, which differs from the file name. The plan uses the file name in the repository.
4. **No published MLX repository holds PaddleOCR-VL 1.6 in bf16 or 8-bit.** `mlx-community/PaddleOCR-VL-8bit` and `mlx-community/PaddleOCR-VL-bfloat16` are built on `baidu/ERNIE-4.5-0.3B-Paddle`, not on 1.6. `mlx-community/PaddleOCR-VL-1.6-5bit` exists, but 5-bit is out of scope. P1 and P2 therefore need own conversions.
5. **The dots.mocr MLX repositories name `rednote-hilab/dots.mocr` as the base.** This holds for `dots.mocr-bf16` (revision `90fe26b`) and `dots.mocr-8bit` (revision `6d9e750`). The 2026-10-06 note said the quantised repositories used `dots-studio/dots.mocr`. This is a conflict, and DR-2 covers it.

## Corpus and ground truth

No new documents. Reuse everything from Experiment 37, without relabelling.

| Run | Pages | Ground truth |
| --- | ---: | --- |
| `E-maths` | 40 | maths labels (sha256 `324ef438`, frozen); KaTeX check only |
| `E-scan` | 28 | operator noise review |
| `E-script` | 189 | Experiment 33 reference transcriptions (split body text) |
| **Total** | **257** | |

The page lists are frozen in `plan.json` (`page_lists`, SHA-256 `09f13055`). They match Experiment 37.

The Experiment 37 outputs and corpus are gitignored. They sit in the `omrs-v3` worktree, at `../omrs-v3/experiments/37-dots-mocr-routing-acceptance-2026-09-30/`. This experiment reads them there. It does not copy them without a hash check.

## Runtime pinning

The GGUF arms run through llama.cpp build 11941 (commit `19ff817fb`), as ADR-103 requires.

- The `runtime` block of `plan.json` is added before the first score. It holds the real SHA-256 of each weights file. The checker refuses the all-zero placeholder, so this plan does not put a placeholder hash in that block.
- Before the first score, `verify_llamacpp_runtime` (`experiments/_lib/llamacpp_runtime.py`) checks the build and each file hash. A wrong build or hash stops the run.
- Each run writes a run record through `experiments/_lib/run_record.py`.
- The server runs on loopback only.
- `runtime_under_test` is `true` for the GGUF arms. Each GGUF arm records its build and the SHA-256 of each weights file.
- The server arguments that change output are the greedy setting (`--temp 0`), the mmproj file and the token cap (8192). The exact flags are confirmed at the smoke test.

The MLX arms run through `mlx-vlm`. They are not in the `runtime` block, because the block allows llama.cpp only, unless `runtime_under_test` is set.

## Variables

| Type | Variable | Values |
| --- | --- | --- |
| Independent | Runtime and precision | shipped backend (baseline); MLX bf16 and 8-bit; llama.cpp GGUF 16-bit and Q8_0 |
| Dependent | Speed | seconds per page, median and 90th percentile |
| Dependent | Memory | peak physical footprint, client and server summed |
| Dependent | Reliability | timeouts, empty results, conversion or load failures, restarts |
| Dependent | Formula validity | KaTeX 0.16.22 render error rate |
| Dependent | Script recall | token recall on `E-script`, Experiment 33 tokeniser |
| Dependent | Invented text | operator verdict on the review list |
| Dependent | Similarity | token Dice coefficient against the baseline arm, per page |
| Controlled | Pages | the same 257 pages as Experiment 37 |
| Controlled | Prompt, render size, token cap, decoding | the dots.mocr engine constants (`prompt_layout_all_en`, 200 DPI with the engine's long-side rule, 8192 tokens, greedy); the PaddleOCR-VL engine settings |
| Controlled | Post-processing | the dots.mocr `layout.py` (header and footer dropped, one `$$` pair per display formula) on every dots.mocr arm |
| Controlled | Request timeout | 300 s per page |
| Controlled | Machine load | one arm at a time, with no other GPU job |

Not changed: engine folders, routes, settings defaults, the maths detector, and the pinned PyTorch dots.mocr revision `e539fbb52280393adc081b289ec597430a0f9031`.

## Gates

The operator set these gates on 2026-10-06. They apply to every new arm against its own baseline. The operator did not change them for the GGUF arms.

| ID | Rule | Role |
| --- | --- | --- |
| C1 | Speed. A D arm: median s/page at most 0.5 times D0, on the 20 Experiment 37 pages that ran alone (D0 56.62 s, eq01 p2 excluded as model load). A P arm: median s/page at most 0.5 times P0 over all 257 pages (P0 40.2 s, shared-load bias stated). | decides |
| C2 | The arm has 0 timeouts at 300 s (P0 had 34 of 257). | decides |
| C3 | KaTeX error rate at most 0.01 over `E-maths` and `E-scan`. Changed from 0.05 on 2026-10-06. | decides |
| C4 | Median `E-script` recall at least the baseline median minus 0.05 (D0 0.8889, P0 0.6095). | decides |
| C5 | The operator finds no invented text on the review list (Experiment 37 G3 rule). | decides |
| C6 | Median Dice similarity to the baseline at least 0.90. | information only |
| C7 | Peak memory below 22.2 GiB for D arms (F5). | information only |

**Pass rule.** C1 to C5 all hold for an arm. C6 and C7 inform the decision only.

**Gate changes.** The operator sets gates before the first run. A later change is a dated amendment. It keeps the original rule in the record.

## Procedure

1. Operator approves the install, download, licence and budget gates in `plan.json` (`approvals`). Each stays `false` until then.
2. Operator confirms DR-2 (licence scope) and DR-4 (precision list). No download starts before both.
3. Install `mlx-vlm` and the llama.cpp conversion tools (Python `gguf` and `transformers`) into gitignored environments inside this folder. Record each version.
4. Download the official PaddleOCR-VL GGUF and the source weights. Record each revision and SHA-256.
5. Convert dots.mocr and PaddleOCR-VL to GGUF at build 11941, with bf16 or 16-bit outtype. Quantise to Q8_0. Record each SHA-256. Stop a conversion that fails and record the error as a finding.
6. Convert PaddleOCR-VL to MLX bf16 and 8-bit with `mlx-vlm` (open item OI-4). Record each step.
7. Add the `runtime` block with the real hashes. Run `verify_llamacpp_runtime` on each GGUF arm.
8. Run a two-page smoke test (`eq01` p2 and p3) for each new arm. Compare with the scratch figures. Stop an arm whose output is empty.
9. Run each new arm alone, through `E-maths`, `E-scan` and `E-script`. Use the checkpoint and resume rules in `run_rules`.
10. If a speed-up is at least 1.5 times and below 3 times, run `T-control` for that baseline (20 pages alone, seed 41).
11. Score KaTeX, recall and similarity for every arm. List every formula that changed against the baseline.
12. Build the review page for each arm: the 10 lowest-similarity pages, every page the noise screen flags, and 5 random pages (seed 41; DR-3). Follow `references/review-page-pattern.md`.
13. Operator reviews. Write `report.md`, `output/summary.json` and the verdict.

## Interpretation rules

- A GGUF arm that passes C1 to C5 supports a follow-up OpenSpec change for that engine. It changes no default by itself.
- An MLX arm that passes supports a report only. It does not support a runtime change.
- A GGUF arm that fails at conversion or load is a finding. The engine keeps its shipped backend unless another GGUF arm passes.
- A speed gain that disappears under `T-control` is a baseline artefact.
- Formula differences are findings. The report lists them even when every gate passes.
- Each result applies to this Mac and these 257 pages. It says nothing about other hardware.

## Runtime budget (estimate)

The estimate covers the 8 new arms, with conversion and model load. The operator sets `runtime_budget_h` in `plan.json`.

- Roughly 3 to 7 hours of machine time in total.
- The GGUF arms and the MLX arms are timed separately.
- No cap is set in this plan.

## Approvals and licence

`approvals` in `plan.json` holds four gates. All stay `false`.

1. **Install.** `mlx-vlm` and the llama.cpp conversion tools. The approval covers both.
2. **Downloads.** About 1.8 GB of PaddleOCR-VL source weights, about 6 GB of dots.mocr bf16 source, about 0.9 GB of PaddleOCR-VL GGUF with its mmproj, and the MLX and GGUF conversions. The target is `OMRS_OCR_MODEL_CACHE`.
3. **Licence.** The dots.mocr agreement covers derivative works (clause 3.3). This plan proposes (DR-2) that the check covers:
   - our own GGUF conversion of dots.mocr, which is a derivative work;
   - `mlx-community/dots.mocr-bf16` (decided 2026-10-06);
   - `mlx-community/dots.mocr-8bit`, whose base the 2026-10-30 check shows as `rednote-hilab/dots.mocr`.
   The operator decides before any download. PaddleOCR-VL is Apache-2.0.
4. **Run budget.** The operator sets `runtime_budget_h` and sets `approved`.

## Artefacts expected

| File | Content |
| --- | --- |
| `protocol.md`, `plan.json` | this plan |
| `experiment.json` | the record (status, finding) |
| `output/` (gitignored) | per-arm Markdown, state files and run records |
| `output/summary.json` | per-arm gate values (committed) |
| `report.md` | verdict, arm table, formula list, the operator's review |

## Open items

These items stay open until the operator or a run closes them. Each one is also in `plan.json` (`open_items`).

- **OI-1.** Confirm that the dots-mocr `layout.py` imports no PyTorch before reuse.
- **OI-2.** dots.mocr conversion and load in llama.cpp build 11941 are not established. Try the conversion. Record the result.
- **OI-3.** Read the tensor type of the official PaddleOCR-VL GGUF from its header. Record whether it is 16-bit.
- **OI-4.** Check that `mlx-vlm` converts PaddleOCR-VL 1.6. Confirm the converted weights load.
- **OI-5.** The PaddleOCR-VL MLX arm reuses the engine's page-subset code (TDR-027) without editing the engine folder.
- **OI-6.** Confirm that the memory sampler covers the llama-server process as well as the client.
- **OI-7.** The Experiment 37 source files sit in `../omrs-v3`. Check their hashes before use.
- **OI-8.** The install approval must cover the llama.cpp conversion tools (Python `gguf` and `transformers`), not only `mlx-vlm`.

## Decisions for the operator

- **DR-2 (extended 2026-10-30).** Confirm the licence scope in the approvals section.
- **DR-4 (open).** Confirm the precision list. The 2026-10-06 plan excluded quantised conversions. This plan includes 8-bit and Q8_0 arms, because the operator asked for them.

## References

- `experiments/37-dots-mocr-routing-acceptance-2026-09-30/report.md`, `plan.json`, `output/` (in `../omrs-v3`)
- `experiments/33-ocr-routing-natural-positive-2026-09-17/` (labels, tokeniser, reference transcriptions)
- `experiments/_lib/llamacpp_runtime.py`, `experiments/_lib/run_record.py`
- `experiments/41-mlx-ocr-backends-2026-10-06/` (on `feat/experiment-41-mlx-ocr-backends`, read only)
- ADR-074, ADR-103, `experiments/38-rescue-quality-signal-2026-09-30/report.md`
- PaddleOCR `PaddleOCR-VL-1.6-GGUF` README (llama.cpp usage)
