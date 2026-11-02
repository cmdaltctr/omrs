# dots-mocr-llamacpp: real-document check results

Change `dots-mocr-llamacpp-backend`, design D9, tasks 3.1 to 3.7. Run on 2026-11-01 and 2026-11-02 on one Apple silicon Mac (macOS, 64 GB), with llama.cpp build 11941 (Metal) and the Q8_0 model. The Linux build was not run.

**Verdict for the operator:** rules 1, 2 (parity), the offline smoke test, the clean exit and the app view pass. One rule is not met as written: `rf06` never reaches OCR under the default routing (see "Open finding F1"). Cut-over waits for your decision.

## Pass or fail per rule

| Rule (design D9) | Result | Evidence |
| --- | --- | --- |
| Provisioning: files match their hashes, `--capabilities` prints the D7 fingerprint (task 3.1) | Pass | Model `6017b184…`, projector `63f415f9…`. Fingerprint: `dots_mocr_llamacpp`, pipeline `prompt_layout_all_en+llamacpp-b11941+q8_0+layout-1`. Provisioning found a wrong program path in the manifest, fixed in `ec87f011`. |
| Offline smoke on `eq01` p2 and p3, network blocked (task 3.2) | Pass | Both pages gave Markdown (3,992 and 5,441 characters). Build 11941. Runtime started by the host manager; no process left. `run.json`. |
| Parity 1: every page Dice 0.99 or more against Experiment 41 arm D4 | Pass | Lowest Dice 1.0 on all 22 pages. `parity.json`. |
| Parity 2: at least 18 of 22 pages identical to D4 | Pass | 22 of 22 identical (after trimming outer whitespace). |
| Parity 3: median Dice against the T-control (PyTorch) text 0.99 or more | Pass | Median 1.0. Lowest pages: `rf06:29` 0.857, `rf07:49` 0.909, `rf06:50` 0.944. D4 differs from PyTorch on the same pages, so the new engine matches D4, not the PyTorch text, on them. |
| Ingest `eq01`, `io06`, `rf06` with the CLI into a scratch collection; search finds a known phrase from an OCR page of each (task 3.4) | **Partly met** | `eq01` and `io06` pass. `rf06` was not OCR'd: see F1. |
| KaTeX 0.16.22 renders every formula on the `eq01` pages (task 3.4) | Pass | `eq01` p2 and p3: 70 formulas, 0 errors. All stored `eq01` chunks of the 14-page ingest: 304 formulas, 0 errors. A deliberately broken formula gives 1 error (self-test). |
| Integrations page shows the engine ready at 1,280 px and 390 px (task 3.5) | Pass | `screenshots/integrations-1280.png`, `integrations-390.png`, and the runtimes tab at both widths. No horizontal scroll at 390 px. |
| Clean exit (task 3.6) | Pass | After the CLI run and after the web preview, no `llama-server` runs from the engine folder. `server.json` in the scratch state folder records `stopped_by: last-client`. |

## Numbers

- **Seconds per page (parity, 22 pages):** minimum 9.2, median 34.6, maximum 47.8, total 629. Light scans take about 10 to 15 seconds. Dense maths pages take about 40 to 45 seconds.
- **Smoke test:** 36.0 s (`eq01` p2, includes loading the model) and 45.2 s (`eq01` p3).
- **Full ingest of the three PDFs:** 22.7 minutes, 3 files indexed, 118 chunks, 0 failed. `eq01` 23 chunks and `io06` 34 chunks went through dots.mocr. `rf06` 61 chunks came from its text layer.
- **Peak memory:**
  - Smoke test (2 pages): worker 79 MB, server 3.9 GB lifetime peak footprint, total 4.15 GB.
  - Web preview during the ingest: the server row showed 7.0 to 8.3 GiB.
  - Experiment 41 reported 17.3 GiB (client plus server) over its runs. The three figures use different methods and page sets, so they are not comparable. This run did not record a lifetime peak over all pages. Plan for the Experiment 41 figure when sizing a machine.
- **llama.cpp build:** 11941 (`llama_cpp_build` in `run.json`).

## Open findings

- **F1: `rf06` is not OCR routed.** The gate reads `rf06` as a text PDF (`pdf_type text_based`, confidence 1.0). All 4 sampled pages are flagged before the text-layer rescue and 0 after it, so the page-fraction rule does not fire. Lowering `OCR_FALLBACK_PAGE_FRACTION` to 0.01 and raising `OCR_FALLBACK_MIN_CONFIDENCE` to 1.0 still left OCR off (checked on a 4-page extract). The stored `rf06` text is the embedded text layer. This is how the host routes today. It does not come from the new engine. The OCR quality of `rf06` is covered by the parity check (4 `rf06` and 3 `rf07` pages, all identical to D4), not by the end-to-end ingest. Operator decision 2026-11-02: task 3.4 stays open until change `image-based-rescue-gate` (Experiment 43) tests a routing fix. Tracked in issue #161.
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

Not given yet. Date and confirmation go here.

Status on 2026-11-02: held. The operator decided that 3.7 is not conclusive while issue #161 is open (task 3.4 is unticked for the same reason). Run the cut-over decision again after the routing work is tested: page-mode test on `rf06` (10-page extract: page 29 found, 4 of 10 pages unresolved, cause unknown), then the judge router. Group 4 has not started.
