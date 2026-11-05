# dots-mocr-llamacpp: real-document check results

The engine was called `dots-mocr-llamacpp` during these checks. At cut-over (task 4.1) it became `dots-mocr`, in `ocr-workers/engines/dots-mocr`. The evidence files keep the old name.

Change `dots-mocr-llamacpp-backend`, design D9, tasks 3.1 to 3.7. Run on 2026-11-01 and 2026-11-02 on one Apple silicon Mac (macOS, 64 GB), with llama.cpp build 11941 (Metal) and the Q8_0 model. The Linux build was not run.

**Verdict:** every rule passes. The `rf06` ingest rule passed in the page-mode re-run of 2026-11-03 (see "Open finding F1" and the task 3.4 re-run). The operator confirmed cut-over on 2026-11-05.

**Status on 2026-11-02 (superseded):** rules 1, 2 (parity), the offline smoke test, the clean exit and the app view passed. One rule was not met as written: `rf06` never reached OCR under the then-default document routing.

## Pass or fail per rule

| Rule (design D9) | Result | Evidence |
| --- | --- | --- |
| Provisioning: files match their hashes, `--capabilities` prints the D7 fingerprint (task 3.1) | Pass | Model `6017b184…`, projector `63f415f9…`. Fingerprint: `dots_mocr_llamacpp`, pipeline `prompt_layout_all_en+llamacpp-b11941+q8_0+layout-1`. Provisioning found a wrong program path in the manifest, fixed in `ec87f011`. |
| Offline smoke on `eq01` p2 and p3, network blocked (task 3.2) | Pass | Both pages gave Markdown (3,992 and 5,441 characters). Build 11941. Runtime started by the host manager; no process left. `run.json`. |
| Parity 1: every page Dice 0.99 or more against Experiment 41 arm D4 | Pass | Lowest Dice 1.0 on all 22 pages. `parity.json`. |
| Parity 2: at least 18 of 22 pages identical to D4 | Pass | 22 of 22 identical (after trimming outer whitespace). |
| Parity 3: median Dice against the T-control (PyTorch) text 0.99 or more | Pass | Median 1.0. Lowest pages: `rf06:29` 0.857, `rf07:49` 0.909, `rf06:50` 0.944. D4 differs from PyTorch on the same pages, so the new engine matches D4, not the PyTorch text, on them. |
| Ingest `eq01`, `io06`, `rf06` with the CLI into a scratch collection; search finds a known phrase from an OCR page of each (task 3.4) | **Pass (re-run 2026-11-03, page mode)** | See "Re-run in page mode" below. 2026-11-02 run (document mode): `eq01` and `io06` passed, `rf06` was not OCR'd (F1). |
| KaTeX 0.16.22 renders every formula on the `eq01` pages (task 3.4) | Pass | 2026-11-03 re-run: 300 formulas in the 24 stored `eq01` chunks (30 display), 0 errors; broken-formula self-test gives 1 error. 2026-11-02: `eq01` p2 and p3 70 formulas, all stored chunks 304 formulas, 0 errors. |
| Integrations page shows the engine ready at 1,280 px and 390 px (task 3.5) | Pass | `screenshots/integrations-1280.png`, `integrations-390.png`, and the runtimes tab at both widths. No horizontal scroll at 390 px. |
| Clean exit (task 3.6) | Pass | After the CLI run and after the web preview, no `llama-server` runs from the engine folder. `server.json` in the scratch state folder records `stopped_by: last-client`. |

## Numbers

- **Seconds per page (parity, 22 pages):** minimum 9.2, median 34.6, maximum 47.8, total 629. Light scans take about 10 to 15 seconds. Dense maths pages take about 40 to 45 seconds.
- **Smoke test:** 36.0 s (`eq01` p2, includes loading the model) and 45.2 s (`eq01` p3).
- **Full ingest of the three PDFs:** 800.8 s (about 13.3 minutes, `total_seconds` in `smoke_evidence/ingest-summary.json`), 3 files indexed, 118 chunks, 0 failed. `eq01` 23 chunks and `io06` 34 chunks went through dots.mocr. `rf06` 61 chunks came from its text layer.
- **Peak memory:**
  - Smoke test (2 pages): worker 79 MB, server 3.9 GB lifetime peak footprint, total 4.15 GB.
  - Web preview during the ingest: the server row showed 7.0 to 8.3 GiB.
  - Experiment 41 reported 17.3 GiB (client plus server) over its runs. The three figures use different methods and page sets, so they are not comparable. This run did not record a lifetime peak over all pages. Plan for the Experiment 41 figure when sizing a machine.
- **llama.cpp build:** 11941 (`llama_cpp_build` in `run.json`).

## Re-run in page mode (task 3.4, 2026-11-03)

Master flow group 3, gate G3 approved by the operator. This branch predates page-routing-default, so the scratch `omrs.jsonc` sets `"ocr_routing_unit": "page"`. OCR: `dots-mocr-llamacpp` (build 11941). Embeddings: the Llama app on port 9931 (Qwen3-Embedding-0.6B Q8_0), chosen with `local_backend = "llamacpp"`. `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` pointed at this worktree's venv. Two consecutive local OCR calls on `rf06` p29 worked before the run. The log held 0 lines of "Local OCR tier unavailable". Scratch config, state and LanceDB were in the session scratchpad. `~/.omrs` and `~/.config/omrs` were not touched.

| File | Pages | Time | Chunks | Pages by route (local / worker / native / unresolved) |
| --- | --- | --- | --- | --- |
| `rf06` | 89 | 3,511 s | 57 | 13 / 41 / 0 / 35 |
| `io06` | 78 | 294 s | 71 | 48 / 22 / 0 / 8 |
| `eq01` | 14 | 489 s | 24 | 0 / 11 / 3 / 0 |

- **`rf06` p29 (the F1 page):** stored text reads "Antonía Cruz González / Sevilla 17 de Agosto de 1911". "Sevilla 17 de Agosto" is an exact match. The source spelling has accents, so the plain "Antonia Cruz Gonzalez" is not an exact string; matching ignored accents, as the handover allows. Search "Antonia Cruz Gonzalez" returns p29 at rank 3 (score 0.998), "Sevilla 17 de Agosto" at rank 1 (0.999).
- **`io06`:** the phrase "gradu, quoad nuptias, in- cipiat collateralis cognatio" is on p28. The long query returns it at rank 3. The stored text keeps the print hyphenation, so a query written as one word misses.
- **`eq01`:** the formula pages (2 to 7, 10 to 14) went to the worker. Pages 1, 8 and 9 stayed native. A phrase from p3 is the top hit (0.999). A phrase from p1 is not evidence of OCR, because p1 is native.
- **Unresolved pages:** 35 of 89 for `rf06` and 8 of 78 for `io06`. The 2026-11-02 check found 4 of 10 sampled `rf06` pages were blank sheets, which fits the rate here. These 43 pages were not checked one by one. Change `skip-blank-pages-before-worker` is not in this branch.
- **First attempt:** a first three-PDF run stopped with no output for 29 minutes and was killed. A debug re-run of `eq01` alone and the runs above did not show the stop again. The cause is not found. That run used an Ollama embedder, and this table does not.
- **Not measured:** peak memory over the whole run. Memory stayed at 54% free or more.

## Open findings

- **F1: `rf06` is not OCR routed.** The gate reads `rf06` as a text PDF (`pdf_type text_based`, confidence 1.0). All 4 sampled pages are flagged before the text-layer rescue and 0 after it, so the page-fraction rule does not fire. Lowering `OCR_FALLBACK_PAGE_FRACTION` to 0.01 and raising `OCR_FALLBACK_MIN_CONFIDENCE` to 1.0 still left OCR off (checked on a 4-page extract). The stored `rf06` text is the embedded text layer. This is how the host routes today. It does not come from the new engine. The OCR quality of `rf06` is covered by the parity check (4 `rf06` and 3 `rf07` pages, all identical to D4), not by the end-to-end ingest. Operator decision 2026-11-02: task 3.4 stays open until change `image-based-rescue-gate` (Experiment 43) tests a routing fix. Tracked in issue #161. **Update 2026-11-03:** page mode reads `rf06` p29 correctly (see "Re-run in page mode"), so task 3.4 is ticked. Issue #161 itself is closed by the page-routing-default change, not by this engine.
- **F2: false start-up log line (host). Fixed.** At web start the log said "declares a llama.cpp runtime but no runtime manager is set; route unavailable", and the route line said `[not provisioned]` for an engine that was provisioned. `log_route_plan` asked `resolve_route_command`, which needs the runtime manager. It now reads the engine folder alone through `resolve_engine_command`. Test `test_an_engine_with_a_runtime_is_provisioned_and_the_line_raises_no_manager_warning` failed before the fix and passes after it. Mutation check: an always-provisioned line fails three tests. Score was likelihood 10, impact 2.
- **F3: Linux and CUDA.** The engine pins a macOS arm64 build and an Ubuntu x64 CPU build of b11941. A CUDA build of b11941 is not pinned, so the engine on a CUDA machine would use the CPU build or an external server. The parity result was measured on Metal. An external server (`OCR_RUNTIME_URL`) with a CUDA build of b11941 avoids a code change, but OMRS cannot check the model files on it. Run `parity_check.py` on that machine first.
- **F4: the parity page texts stay local.** `smoke_evidence/parity-pages/` is ignored, because the pages come from the corpora.

## Other runtimes: Ollama and MLX (checked 2026-11-02, not part of the pass rules)

Question: does this engine give the same text on a runtime other than llama.cpp? The engine ran unchanged against each runtime. It sends no `model` field, so a scratch proxy that only adds that field stood in front of each server. No engine code was changed.

| Runtime | Model | Runs the engine? | Identical to llama.cpp, 10 pages | Lowest Dice | Median Dice |
| --- | --- | --- | --- | ---: | ---: |
| llama.cpp b11941 | pinned Q8_0 plus bf16 projector | yes, unchanged | all pages (22 of 22 in the parity check) | 1.000 | 1.000 |
| Ollama 0.40.13 | the same two pinned files, built with a two-line Modelfile | only with a `model` field | 7 of 10 | 0.767 | 1.000 |
| mlx-vlm 0.7.11 | `mlx-community/dots.mocr-8bit` | only with a `model` field | 3 of 10 | 0.901 | 0.994 |

Both runtimes fail the rule that llama.cpp passed (every page Dice 0.99 or more, and at least 8 of 10 pages identical).

- **Pages:** 10 pages from 8 documents (`eq01`, `io01` twice, `io02`, `io04`, `io07` twice, `mp05`, `rf06`, `rf07`).
- **Ollama differences:** real wording changes on three pages (one handwritten Spanish page, one handwritten Spanish record, one Arabic page with added page markers). The other seven pages are identical. An earlier four-page run used a community conversion (`richardyoung/dots.mocr:Q8_0`). It gave byte-identical output to our own two files, so the differences come from Ollama, not from the conversion.
- **MLX differences:** some are format only (`\mathbf{}` dropped in formulas, a missing space before a danda, spaces inside LaTeX). Others are real wording errors on a Bengali page, an Arabic page and the two handwritten pages. MLX output equals Experiment 41's MLX 8-bit output on the pages checked.
- **Speed and memory:** Ollama 13 to 47 s per page, 6.5 GB with the model loaded. MLX 9 to 28 s per page, 8.4 GB peak.
- **Read this as:** both can run the engine after a one-line change (send a `model` name, which `llama-server` ignores). Neither gives llama.cpp's text. llama.cpp is the only runtime with a parity record. Ollama and MLX need their own 22-page parity run before anyone relies on them, and an Ollama or MLX index needs its own fingerprint value.
- **Limit:** MLX is not an allowed runtime for experiments (ADR-103). It was run here as a comparison only.
- **Where this goes next:** the ADR written after the cut-over (task 4.4) records it. The scratch proxy and driver scripts are not kept.

## Operator confirmation of cut-over (task 3.7)

Confirmed on 2026-11-05 (master flow gate G10). The evidence is master flow group 3, the page-mode re-run of task 3.4: `rf06` p29 found, `eq01` 0 KaTeX errors.

Status on 2026-11-02 (superseded): held. The operator decided that 3.7 is not conclusive while issue #161 is open (task 3.4 is unticked for the same reason). Run the cut-over decision again after the routing work is tested: page-mode test on `rf06` (10-page extract: page 29 found, 4 of 10 pages unresolved, cause unknown), then the judge router. Group 4 has not started.
