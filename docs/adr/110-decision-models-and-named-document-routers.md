# ADR-110: Decision Models and Named Document-Reading Routers

- **Date:** 2026-11-02
- **Status:** Proposed (2026-11-02; revised 2026-11-05 for the page-rule form; not accepted)
- **Deciders:** Maintainer
- **Amends:** [ADR-112](112-reading-parts-descriptor-pipeline-and-discovery.md) decision 3 (the page rule outcome gains `add`, the rule context gains `claimed` and `judge`, and the descriptor gains `adds_pages`). Page routing (`page-routing-default`) already replaced the [TDR-024](../tdr/024-pdf-inspector-silent-empty-extraction-on-legacy-winansi-fonts.md) zero as the routing input. This change adds a note to TDR-024 that says so.
- **Related:** [ADR-066](066-tiered-reader-fallback-chain.md) (rescue tiers), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (page routing), [ADR-112](112-reading-parts-descriptor-pipeline-and-discovery.md) (a router is a page rule), [ADR-074](074-run-local-decision-models-through-llama-cpp-q8-0-gguf.md) (8-bit decision models), [ADR-087](087-settings-live-in-omrg-jsonc.md) (`omrs.jsonc`), [ADR-105](105-pipeline-steps-own-their-ocr-settings.md) (step OCR settings), [ADR-108](108-local-chat-and-classification-stay-apart.md) (classification address), [ADR-109](109-omrs-owns-local-model-runtimes-components-are-clients.md) (managed runtimes), root `AGENTS.md` gotchas 16 and 18
- **Change:** `openspec/changes/document-reading-routers/`

## Context

Page routing sends the pages that the PDF scan flags to OCR. A page that the scan does not flag keeps its native text, even when that text is junk. Handwritten scans such as `rf06` keep junk text and never reach OCR (issue #161). Text-only checks failed in Experiments 38 and 42. Experiment 43 asked a decision model, with the page image, whether the text matches the page. It caught most junk pages. It was scored under the old 10% document rule, which also sent good documents to OCR. Its threshold was fitted on the same documents it was tested on.

This ADR was first written before `page-routing-default` and `local-ocr-backends`. It was revised on 2026-11-04 and 2026-11-05 for page routing as the only unit and for page rules as registered parts (ADR-112). The text below describes the code as built in change `document-reading-routers`.

OMRS had no provider for a model that answers yes/no questions about a page. Classification has one address and one model, and speaks chat completions (ADR-108).

A page rule lives in `integrations/`, which is a leaf. The import contract `providers-constructed-only-in-compose` lets only `compose` and `core/providers/` import a concrete provider module. A page rule therefore cannot build its own decision model client.

## Decision

1. **A new provider kind: decision model.** `omrs.jsonc` holds a map of named entries, `decision_models`. Each entry has a `kind`, an `address`, a `model`, an `images` flag and, for hosted kinds, a `key` reference (`env://`, `file://` or `keychain://`, never a literal key). A `llamacpp` entry also has `server` (`external` or `managed`) and, for a managed entry, `model_file` and `projector_file`. The kinds come from `core/providers/decision/registry.py`: `llamacpp`, `typesafe`, `cloudflare` and `ollama`. Every kind sends the same System One `noul` request with the options `no` and `yes`, and returns P(yes). `llamacpp` and `typesafe` have a recorded live request (Experiment 43). `cloudflare` and `ollama` are tested against fake servers only. Settings labels them "Not yet tested" until the operator records one live request for each. An address that is not loopback is hosted.
2. **Local decision models run at 8-bit or higher.** A managed entry reads `general.file_type` from the GGUF header before start. It accepts Q8_0, F16, BF16 and F32. It refuses Q4_K_M and every other type with reason `quantisation-refused`. An external entry checks the reported model name for a quantisation marker. When it finds none, the row says "Quantisation not checked".
3. **Image entries pass a projector smoke test.** A managed image entry declares its projector file (runtime flag `--mmproj`). Every image entry sends one bundled page image twice, once with the right text and once with wrong text. The test passes when P(yes) for the right text minus P(yes) for the wrong text is at least 0.2. The margin comes from Experiment 43 plan rule R4, with version `exp43-r4-2026-11-02` (`core/providers/decision/checks.py`). Experiment 43 recorded 0.903 against 0.069 for local Clef-Flash Q8_0 and 0.39 against 0.01 for hosted Jev. The design text named 0.5 as a placeholder. A margin of 0.5 fails the recorded Jev pass. A failed test gives reason `projector-not-loaded`. The check results are cached per process and per entry.
4. **A managed decision runtime.** A managed `llamacpp` entry runs under ADR-109 with runtime role `decision` and runtime id `decision-<name>`. The server binds `127.0.0.1` and serves one request at a time (`--parallel 1`). It declares the model file and the projector file, each with its SHA-256. Its build floor is b11941, the build that Experiment 43 used, which is above the b11510 floor of ADR-074. A lower build gives reason `wrong-build`. An external entry has no build check, and the row says so. `GET /v1/runtimes` lists the decision runtimes.
5. **Named routers live in `omrs.jsonc`.** `document_routers` is a map of named recipes. Each recipe names a decision model entry and holds the question, the threshold on P(yes), the `images` flag, the character limit (`max_chars`) and the hosted opt-in (`send_off_machine`). "Yes" keeps the page text. "No" sends that page to OCR. `document_router` names the host default. It is the flat setting of the router rule (env `DOCUMENT_ROUTER`) and follows the normal source order. The two maps are file-only: no environment variable sets them. Studio's Read document step (`document_router` on the step) and user profiles pick a router by name. Settings refuses to rename or delete a router while a saved profile names it. No router is selected by default.
6. **The router is the built-in page rule `document_router` at order 40.** It is one module (`integrations/pdf/page_rules/document_router.py`), one `PageRuleDescriptor` in `core/reading_parts.py` and one `register()` line. The descriptor declares `adds_pages` and `has_degrade`. The rule judges every page that has non-blank native text, that the scan did not flag and that no earlier rule claimed (`RuleContext.claimed`). It asks the judge one page at a time. It never judges a flagged page and never judges OCR output. A page with P(yes) below the threshold is rejected. The rule returns the rejected pages in `RuleOutcome.add`. They join the direct set and go once, in the one page-listed request, to the OCR engine list. The local tier reads a rejected page only when no engine reads it: the degrade hook sends it there with one warning. One rejected page sends only that page to OCR. With no router selected, the rule returns an empty outcome before it reads a page, and every digest and output stays as before.
7. **No scope field.** The first plan had a `scope` field (`rescued` or `all-text`). Under page routing as the only unit, the `rescued` scope has no pages, so the field is removed and no setting replaces it. The router always judges the unflagged, unclaimed text pages.
8. **Compose builds the judge, and the rule receives it.** `compose_decision.py` builds a page judge from the selected router, its decision model entry and the resolved key. It is the only module that imports a concrete decision model adapter. At start, compose installs a judge factory on the OCR routes (`install_judge_factory` in `integrations/ocr_worker/routes.py`). The routes call the factory with the settings and carry the result as `OcrRoutes.judge`. `OcrRoutedPdfInspector` puts it on `RuleContext.judge`. The rule and the OCR routes import nothing from `core/providers/`, so `integrations/` stays a leaf. With no router selected, the judge is `None`. The design (D12) first named a path through the local backend and `build_pdf_reader`. The built path uses the factory on the OCR routes.
9. **Page renderers are an ordered list.** An image router renders one page as a PNG at 150 DPI, with the long side at most 1,568 px. These are the Experiment 43 values, so the frozen threshold stays comparable. The renderers live in `integrations/pdf/page_images/` and are held by the shared `PartRegistry` (ADR-112 decision 2). LiteParse is first, because it is always installed. pypdfium2 is second, when the optional `pdf-pypdfium2` extra is installed. The router uses the first available renderer. A renderer is not a reading part: it has no descriptor and no entry-point group. An image router with no available renderer gives reason `renderer-missing`.
10. **Local by default, hosted by explicit opt-in.** A router on a hosted decision model runs only when its own `send_off_machine` opt-in is on. A hosted decision model entry alone does not grant it. Without the opt-in the router gives reason `needs-opt-in` and sends no request. Settings warns on every hosted router and labels hosted image input experimental. Logs never hold page text, images, keys or reply bodies.
11. **A router that cannot run changes nothing.** The fixed reasons are `unknown-model`, `unreachable`, `quantisation-refused`, `projector-not-loaded`, `wrong-build`, `renderer-missing`, `needs-opt-in` and `request-failed`. A file-level reason makes the rule return an empty outcome, and `router_status` holds the reason. A failed page request keeps that page's text, and the page counts as unjudged. No file fails because of a router.
12. **Diagnostics and index identity.** The rule stamps `router_pages_judged`, `router_pages_accepted`, `router_pages_rejected`, `router_pages_unjudged` and `router_status`. These keys are in `EXCLUDED_EMBED_METADATA_KEYS` and `IDENTITY_UNLISTED_KEYS`, as `pages_non_latin` is, and with no router the rule stamps nothing. The router adds one entry, `document_router`, to the `parser` block of the index identity. The entry is present only for PDF sources and only when a router is selected. It holds the question, threshold, image flag, character limit, the decision model kind and model identity (the model name and, for a managed entry, the model and projector SHA-256) and the rule version. It does not hold the router name, address, key or opt-in. A router rename therefore does not reindex. Selecting or editing a router reprocesses PDF sources once.
13. **Confirmation before any default, deferred to GATE G7.** A router becomes a default only after an experiment on new documents passes a page-based rule fixed before scoring. The operator decided on 2026-11-04 to move that experiment out of this change. It waits for GATE G7 of `doc-reading-master-flow`. After this change merges, the operator says whether to run it. If yes, it is a follow-up change with new documents only and the threshold of 0.172 frozen from Experiment 43.

## Consequences

### Positive

- Junk native text on pages that the scan did not flag can reach OCR page by page. Only the rejected pages pay the OCR cost.
- The operator chooses the model, the question and the privacy trade-off, and can keep several routers.
- The 8-bit rule, the projector smoke test and the build floor are enforced in code.
- The page-rule interface grows by one declared fact. The blank, maths and non-Latin rules do not change.

### Negative

- A router costs about 3.6 s per judged page with images on a local model (Experiment 43), for every unflagged text page. In Experiment 43 it sent about 2.7% of healthy pages (15 of 565) to OCR. The guide and the router help text state both numbers.
- Two new settings maps make `omrs.jsonc` larger and need a file-only shape.
- Selecting or editing a router reprocesses PDF sources once.
- The Experiment 43 threshold is not confirmed on new documents until the deferred experiment runs.

### Neutral

- Routing of flagged pages and the blank, maths and non-Latin rules do not change.
- The `cloudflare` and `ollama` kinds ship untested and carry a "Not yet tested" label until a live request passes.
- `pages_needing_ocr` stays the count of pages that the scan flagged. Added pages appear in the router counts.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Flat decision model settings like ADR-108 | Routers need more than one model (local and hosted arms in Experiment 43). |
| Routers in the workspace database | Settings live in `omrs.jsonc` (gotcha 18), and the CLI must resolve the host router without the web server. |
| Mark rejected pages as flagged | It corrupts `pages_needing_ocr`, mixes router verdicts into the scan count and moves digests. |
| Keep a `scope` field (`rescued` or `all-text`) | Under page routing the `rescued` scope has no pages. |
| A judge that moves a request to the next OCR engine on a bad answer | The engine list keeps the "unavailable before dispatch" rule. Not in this change. |
| Ship the Experiment 43 threshold as a default router | It was fitted and tested on the same documents. |
| Smoke test margin of 0.5 (design placeholder) | The recorded hosted Jev pass in Experiment 43 (0.39 against 0.01) fails it. |

## Verification

- The golden snapshots and the digest pins stay byte-identical with no router selected.
- Tests show that only a rule with `adds_pages` may add pages, that a rejected page goes once to the engine list, that the local tier reads it only through the degrade hook, and that `pages_needing_ocr` stays the scan count.
- A hosted router without opt-in sends zero requests.
- A smoke test with equal answers fails with `projector-not-loaded`. A Q4_K_M header is refused.
- The confirmation experiment is deferred to GATE G7. When it runs, its report states PASS or FAIL by its frozen rule.

## References

- Issue #161; Experiments 33, 38, 42, 43 and 44; [TDR-024](../tdr/024-pdf-inspector-silent-empty-extraction-on-legacy-winansi-fonts.md).
- `openspec/changes/document-reading-routers/` (proposal, design D1 to D12, tasks).
- [Reading parts guide](../guides/reading-parts.md) and [providers guide](../guides/providers.md).
