# Design: decision models and named document-reading routers

## Context

See proposal.md for the why.

**Observed in the code (branch `v3`, `12699bda`):**

- The TDR-024 reset is in `integrations/pdf/pdf_inspector.py`: after `_rescue_pages` recovers text, `metadata["pages_needing_ocr"] = 0` and the old count goes to `pages_needing_ocr_before_fallback`. Nothing checks the recovered text.
- The document unit then calls `ocr_required_by_gate` (`ocr_routing.py`): OCR when `pdf_type` is unconditional, confidence is below 0.5, or flagged pages reach `ocr_fallback_page_fraction` (0.10). That is the 10% rule. `ocr_routing.py` is at the 500-line ceiling.
- The page unit (`_page_unit_documents`) already sends a list of pages to the local tier and an escalated list to the engines in one page-listed request (protocol 1.1, `_escalated_worker_text`). It degrades when the worker speaks protocol 1.0. A router can reuse this path for rejected pages under either unit.
- Classification has one address and one model (ADR-108): `llamacpp_classify_url` (blank follows the Chat address) and `llamacpp_chat_model`; `classification_url(settings)` in `core/settings.py`. Ollama classification uses `ollama_classify_model`. Neither speaks the System One request.
- No decision model code exists in `src/` or `web/src/` (searched for `systemone`, `typesafe`, `jev`, `clef`).
- `integrations/llamacpp_runtime/spec.py`: `Role = Literal["chat", "embeddings", "ocr"]`, runtime ids `chat`, `embeddings`, `ocr-<engine>`. OCR runtimes already declare files with SHA-256, including `--mmproj`, and a required build (`wrong-build` refusal).
- Experiment 43 (other worktree, read only): the local arm calls `llama-server` `/v1/systemone` with an `images` list; the hosted arm calls `https://api.typesafe.ai/v1/systemone` with the image in `assets` and the header `TypeSafe-Danger-Zone-Images: true`. Frozen thresholds: Clef-Flash Q8_0 0.172, Jev 0.21, both fitted on 561 Experiment 33 pages. Pages were rendered with `pdftoppm` at 150 DPI, long side at most 1,568 px. Images and 2,000 characters came to about 2,460 tokens, inside a 4k context.
- Results stated by the operator: the image check caught 62 (local) and 61 (hosted) of 89 junk pages against 37 for the word check, and all 54 junk pages of `rf06` and `rf07` on the local arm. Under the 10% rule it also routed good documents (`rf05`; `rf08`, `tl04`, `tl06` for Jev).

**Proposed:** the decisions below.

## Goals / Non-Goals

**Goals:** a decision model provider kind; named routers chosen by name; per-page routing of rejected pages; local by default and hosted only by explicit opt-in; model checks that enforce gotcha 16 and the projector rule; a confirmation experiment.

**Non-Goals:** flipping the routing-unit default or removing the 10% rule (open decision below); judging OCR output; a router that moves a request to another OCR engine; a default router.

## Decisions

### D1. Decision models are named entries, not one flat setting

Classification has one address and one model because one model labels metadata. Routers need more than one decision model (Experiment 43 used a local and a hosted arm). So `decision_models` is a map of named entries: `kind`, `address`, `model`, `images`, `key` (reference, hosted only), and for `llamacpp` `server` (`external` or `managed`) with `model_file`, `projector_file`. The address rule and key-reference rule reuse the classification address check (`address_problem`) and the provider key resolution (ADR-083, gotcha 18). Alternative: flat `decision_url`, `decision_model` like ADR-108. Rejected: a second router on a different model would need a second set of keys.

### D2. A registry of kinds, one request shape

`core/providers/decision/registry.py` maps kind to an adapter file. Each adapter builds one System One `noul` request (options `no`, `yes`), sends text and an optional image, and returns P(yes). `llamacpp`, `typesafe`, `cloudflare` and `ollama` ship now. Only `llamacpp` and `typesafe` have a live recorded request (Experiment 43). `cloudflare` and `ollama` are written from the facts below and tested against fake servers only. Settings labels them "Not yet tested" until the operator runs the live check (see Workflow follow-up in tasks.md). Facts for the two later kinds:

- **`ollama`.** Ollama 0.40.13 answers `POST /v1/systemone` (checked 2026-11-02: an empty body gives HTTP 400 `model is required`, so the route exists and needs a model name). Ollama issue 18769 (non-finite scores on this route) was closed on 7 October; whether the fix is in 0.40.13 is not checked. Rule 16 applies: 8-bit or higher. Ollama cannot show a GGUF header to OMRS, so the quantisation check reads "Quantisation not checked". The dots-mocr test showed that `ollama create` builds a vision model from two local files (model plus projector) with a two-line Modelfile. Do the same for Clef-Flash Q8_0, so the entry runs the pinned file. Ollama may serve its own library Clef on MLX on a Mac (ADR-103 does not allow MLX as an experiment runtime), so the entry should name a model built from our files.
- **`cloudflare`.** From the Experiment 38 notes (not re-read today): the Workers AI route is `/ai/run/@cf/cloudflare/clef` and `/ai/run/@cf/cloudflare/clef-flash`, it accepts the Jev request format, images go in an `images` list as base64 (at most 4 images, PNG, JPEG or WebP, 4 MiB and 16 MP each, 8 MiB in total), and the reply names the model without a version, so a silent model change cannot be detected. The address holds the account id. The key is the Cloudflare API token by reference (`env://CLOUDFLARE_API_TOKEN`). It is hosted, so a router needs the opt-in tick. Cloudflare's data retention terms for Workers AI have not been checked and must be read before the first hosted run. The adapter adds `TypeSafe-Danger-Zone-Images: true` only for a hosted image request. Only `compose_decision.py` imports a concrete adapter (the `providers-constructed-only-in-compose` contract).

### D3. Routers live in `omrs.jsonc` (confirmed by the operator 2026-11-02)

`document_routers` is a map of named recipes; `document_router` names the host default. Both live in `omrs.jsonc` (ADR-087). The CLI, the stdio MCP server and the watcher can then run the host router without the web server, and a hand edit applies like any other setting. Alternative: a workspace database table, like user profiles (ADR-080). Rejected: gotcha 18 says the workspace database holds no settings, and the host default must resolve in processes that only read the workspace. Rename and delete are refused while a saved profile names the router.

### D4. Where a router runs

1. pdf-inspector reads. If the contradiction triggers, the rescue tiers return page texts (change A makes the tiers a list).
2. With a router selected, `integrations/pdf/page_router.py` judges each rescued page (scope `rescued`) or every page with native or rescued text (scope `all-text`). Requests go one at a time to a local model (ADR-074 rule 5).
3. "Yes" keeps the text. "No" adds the page to a rejected set, carried in process, not as metadata.
4. The rejected set goes to the page path: local tier, then escalation to the engine list. Under the `document` unit this path runs for the rejected pages only. `pages_needing_ocr` equals the rejected count, and the document gate does not see rejected pages, so the 10% rule cannot fire on them.
5. Pages are numbered from 1, as in `page_routing.py`.
6. Under the `page` unit, flagged pages already go to the local tier (observed: `page_evidence` flags come from the full scan, not from the rescue). The router skips pages that page routing already sends to OCR. So scope `rescued` acts under the `document` unit, and scope `all-text` acts on unflagged native pages under both units.

A router never sends a whole document to OCR. One rejected page costs one page of OCR.

### D5. Page images

An image router renders one page at 150 DPI, long side at most 1,568 px, PNG (Experiment 43 values, so the frozen threshold stays valid). Page renderers are a list that grows through Integrations, like PDF readers. The first renderer is LiteParse, which is always installed and has a `screenshot` call (checked on 2026-11-02: one scanned page rendered in 0.12 s, 1,475 by 1,238 px). Where the optional `pdf-pypdfium2` extra is installed, pypdfium2 is the second renderer (same page in 0.09 s, 1,476 by 1,239 px). The operator may add others the same way. The router uses the first renderer that is available. A router whose renderers are all missing degrades with reason `renderer-missing`. Both renderers wrap PDFium, so images should match to about a pixel. Task 3.x checks this on a scanned page and a vector-only page before the threshold is reused.

### D6. Model checks

- **Quantisation:** managed entries read `general.file_type` from the GGUF header (a few bytes, no model load) and accept Q8_0, F16, BF16, F32. External entries check the reported model name for a quantisation marker; otherwise "Quantisation not checked".
- **Projector:** managed image entries must declare `projector_file` (runtime flag `--mmproj`). Every image entry runs the smoke test: one bundled page image (a rendered fixture with known text), right text against wrong text, pass when P(yes) right minus P(yes) wrong is at least 0.5. The margin is a constant with a version, set from the Experiment 43 smoke results during task 2.3.
- **Build:** managed entries use the existing build check with a floor (Open Questions). External entries: the build is not checked; the row says so.
- Results cache per process and per entry fingerprint. Test re-runs them on request.

### D7. Privacy

- Hosted is decided by address: anything not loopback is hosted.
- A hosted router needs `send_off_machine: true` on the router itself. A hosted decision model alone does not grant it.
- Settings shows the third-party name and what leaves (text; images when the flag is on). Hosted image routers carry "experimental".
- Logs never hold page text, images, keys or reply bodies. Diagnostics hold counts and fixed reasons only.

### D8. Degradation

Fixed reasons: `unknown-model`, `unreachable`, `quantisation-refused`, `projector-not-loaded`, `wrong-build`, `renderer-missing`, `needs-opt-in`, `request-failed`. A file-level reason makes the reader behave as with no router (the TDR-024 zero applies). A failed page request keeps that page's text and counts it unjudged.

### D9. Index identity

Block `document_router` present only when a router is selected for the source: question, threshold, image flag, scope, character limit, decision model kind and model identity (model name; for managed entries the model and projector SHA-256). Not hashed: router name, address, key, opt-in. Cost for real users: selecting or editing a router reprocesses PDF sources once on the next explicit ingest. With no router nothing changes. This is a one-time cost per router edit. The operator's current indexes are test data.

### D10. Studio and profiles

`read.document` gets `document_router` (name, `none` or `null`). Built-in profiles use the host router. User profiles pick by name. `uninstall_profiles.py` is not involved, since routers name no extra.

### D11. Speed

Clef-Flash Q8_0 took 0.84 s a page for text (ADR-074). Image requests are slower: Experiment 43 estimated over an hour for 1,123 pages, about 3 s a page. Scope `rescued` judges only rescued pages, so normal born-digital PDFs pay nothing. Scope `all-text` judges every page and the form says so.

## Open decision: page routing as the default

Not decided here. The operator's view is that page routing should become the default and the 10% document rule should go. Evidence so far:

- Page mode on a 10-page extract of `rf06` made a search for the right name find page 29. Document mode kept the junk.
- 4 of those 10 pages stayed unresolved with junk text. The reason is not known yet. The full 89 pages were estimated at 53 minutes.
- Under page mode every flagged page already goes to the local tier, whatever the rescue returned. So a router adds most under the `document` unit (rescued pages) and, with scope `all-text`, under both units for pages that pdf-inspector did not flag.

Needed before the decision: the page-mode re-test with the cause of the 4 unresolved pages, and the confirmation experiment of this change. The flip would change the identity of every PDF source (the `routing_unit` key appears), so every real user would reindex PDF sources once. That decision needs its own change and ADR.

## Risks / Trade-offs

- [The Experiment 43 threshold was fitted on the same documents it was tested on] → the confirmation experiment (task group 6) uses new documents and a stricter rule. The template labels the threshold "not confirmed".
- [Hosted image input is not production-ready per TypeSafe] → experimental label, opt-in per router, local default.
- [A router slows ingestion] → scope `rescued` by default; one request at a time; counts show the cost.
- [A local server on a shared port serves another model] → Test checks the model name and the smoke test; managed entries own their runtime.
- [Worker on protocol 1.0 cannot take page lists] → rejected pages keep their text, count unresolved, and a warning names the upgrade, as page routing does today.

## Migration Plan

No router by default, so nothing changes on upgrade. Rollback: revert; the `decision_models`, `document_routers` and `document_router` keys are then reported as unknown and ignored, and reading returns to the TDR-024 behaviour.

## Open Questions

0. **Page-rule hook: settled by change `local-ocr-backends` (ADR-112, 2026-11-04).** Blank, maths and non-Latin routing now run as registered page rules on one hook (`integrations/pdf/page_rules/`, orders 10, 20 and 30). Routers register as page rule order 40 on that hook: one module, one descriptor entry in `core/reading_parts.py` and one `register()` line, as `docs/guides/reading-parts.md` describes. A router reads its options from `reading_part_options` or from its own settings (D3). Its identity contribution comes from its descriptor. Still to do before applying: rebase this change onto the current specs. The `document` unit was removed (`page-routing-default`), so D4 steps 4 and 6 and every document-unit scenario need revision.

1. **Page renderer for image routers. Answered 2026-11-02 by the operator:** LiteParse first (always installed), pypdfium2 when its extra is installed, and more renderers through Integrations later. poppler `pdftoppm` (external program, used in Experiment 43) is not a product renderer. Remaining check: LiteParse and pypdfium2 images match closely on a scanned page and on a vector-only page (task list).
2. **llama.cpp build floor for image decision requests. Answered 2026-11-02 by the operator:** floor b11941, the build Experiment 43 used. ADR-074 sets b11510 for the Metal fix, and b11941 is above it. A lower build may be allowed later, only after it passes the smoke test.
3. **Cloudflare Clef kind. Answered 2026-11-02 by the operator:** set up in this change, tested later. The kind is labelled "Not yet tested" until one recorded live request passes.
4. **Ollama kind. Answered 2026-11-02 by the operator:** set up in this change, tested later. The route exists (see D2 facts), so the earlier note that no endpoint was known was wrong. The kind is labelled "Not yet tested" until one recorded live request passes.
