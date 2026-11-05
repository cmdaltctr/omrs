# Design: decision models and named document-reading routers

## Context

See proposal.md for the why.

**Replanned on 2026-11-04** after change `local-ocr-backends` (PR #168, ADR-112) merged. The first plan assumed the `document` routing unit, the 10% rule and a hand-wired `page_router.py`. None of them exist now. The sections below describe the code as it is on `v3` at `2e877109`.

**Observed in the code:**

- **One routing unit.** `OcrRoutedPdfInspector._page_unit_documents` (`integrations/pdf/ocr_routing.py`, 434 lines) is the only path. `page_evidence` scans every page. `flagged` is the set of pages whose scan says `needs_ocr`. The page rules run on `flagged` through `run_rules` (`integrations/pdf/page_rules/pipeline.py`). The local tier reads `plan.local`, and pages it does not keep go to the OCR engine list in one page-listed request. The page unit overwrites `pages_needing_ocr` with `len(flagged)`.
- **The TDR-024 zero no longer routes.** `pdf_inspector.py` still sets `pages_needing_ocr = 0` after a rescue, but the page unit ignores that value and re-scans. A rescued file has its scan-flagged pages read by the local tier. The rescue text is the record only when the scan produced no text on any page (the "last resort" branch). So no "rescued page" set exists to judge, and the 10% rule and `ocr_required_by_gate` are gone.
- **What a router can still change.** A page that the scan did **not** flag and that has native text keeps that text. That is the junk-hidden-layer case of issue #161 that the scan misses. A router judges those pages.
- **The page-rule hook.** `RuleContext` holds `file`, `evidence`, `flagged`, `routed`, `settings`, `routes`. `RuleOutcome` holds `drop`, `direct`, `state`. `local = flagged - dropped - direct`. A rule cannot name a page the scan did not flag: `_checked` refuses a `drop` or `direct` outside `routed`. Blank (10), maths (20) and non-Latin (30) are registered rules. A rule is one module, one `PageRuleDescriptor` in `core/reading_parts.py` and one `register()` line.
- **Identity.** Rule keys in `EXCLUDED_EMBED_METADATA_KEYS` enter every digest through `embedding_text.excluded_keys`, unless the key is in `IDENTITY_UNLISTED_KEYS` (the `pages_non_latin` pattern). The non-Latin entry sits in the `parser` block, present only for PDFs when the mode is on (`reader_identity.py`, `ocr_identity.py`). `source_state.py` is at 499 lines.
- **Layering.** Concrete provider modules may be imported only by `compose` and `core/providers/` (contract `providers-constructed-only-in-compose`). `integrations/` is a leaf. A page rule therefore cannot import a decision model adapter; compose must hand it a built object.
- **Classification** has one address and one model (ADR-108): `llamacpp_classify_url` and `llamacpp_chat_model`. Neither speaks the System One request. No decision model code exists in `src/` or `web/src/`.
- **Runtimes.** `integrations/llamacpp_runtime/spec.py`: `Role = Literal["chat", "embeddings", "ocr"]`, runtime ids `chat`, `embeddings`, `ocr-<engine>`. OCR runtimes declare files with SHA-256, including `--mmproj`, and a required build (`wrong-build` refusal).
- **Experiment 43** (read only): the local arm calls `llama-server` `/v1/systemone` with an `images` list. The hosted arm calls `https://api.typesafe.ai/v1/systemone` with the image in `assets` and the header `TypeSafe-Danger-Zone-Images: true`. Frozen thresholds: Clef-Flash Q8_0 0.172, Jev 0.21, both fitted on 561 Experiment 33 pages. Pages were rendered with `pdftoppm` at 150 DPI, long side at most 1,568 px. Images and 2,000 characters came to about 2,460 tokens, inside a 4k context.
- **Results stated by the operator:** the image check caught 62 (local) and 61 (hosted) of 89 junk pages against 37 for the word check, and all 54 junk pages of `rf06` and `rf07` on the local arm. Those results were scored under the old 10% document rule. This change judges pages, so the confirmation experiment (group 6) scores pages.

**Proposed:** the decisions below.

## Goals / Non-Goals

**Goals:** a decision model provider kind; named routers chosen by name; a router that is one page rule at order 40; per-page routing of rejected pages; local by default and hosted only by explicit opt-in; model checks that enforce gotcha 16 and the projector rule.

**Non-Goals:** the confirmation experiment (it waits for GATE G7, see Deferred); judging OCR output; a router that moves a request to another OCR engine; a default router; any change to the routing of flagged pages, to the blank, maths or non-Latin rules, or to any digest when no router is selected.

## Decisions

### D1. Decision models are named entries, not one flat setting

Classification has one address and one model because one model labels metadata. Routers need more than one decision model (Experiment 43 used a local and a hosted arm). So `decision_models` is a map of named entries: `kind`, `address`, `model`, `images`, `key` (reference, hosted only), and for `llamacpp` `server` (`external` or `managed`) with `model_file`, `projector_file`. The address rule and key-reference rule reuse the classification address check (`address_problem`) and the provider key resolution (ADR-083, gotcha 18). Alternative: flat `decision_url`, `decision_model` like ADR-108. Rejected: a second router on a different model would need a second set of keys.

### D2. A registry of kinds, one request shape

`core/providers/decision/registry.py` maps kind to an adapter file. Each adapter builds one System One `noul` request (options `no`, `yes`), sends text and an optional image, and returns P(yes). `llamacpp`, `typesafe`, `cloudflare` and `ollama` ship now. Only `llamacpp` and `typesafe` have a live recorded request (Experiment 43). `cloudflare` and `ollama` are written from the facts below and tested against fake servers only. Settings labels them "Not yet tested" until the operator runs the live check (see Workflow follow-up in tasks.md). Facts for the two later kinds:

- **`ollama`.** Ollama 0.40.13 answers `POST /v1/systemone` (checked 2026-11-02: an empty body gives HTTP 400 `model is required`, so the route exists and needs a model name). Ollama issue 18769 (non-finite scores on this route) was closed on 7 October; whether the fix is in 0.40.13 is not checked. Rule 16 applies: 8-bit or higher. Ollama cannot show a GGUF header to OMRS, so the quantisation check reads "Quantisation not checked". The dots-mocr test showed that `ollama create` builds a vision model from two local files (model plus projector) with a two-line Modelfile. Do the same for Clef-Flash Q8_0, so the entry runs the pinned file. Ollama may serve its own library Clef on MLX on a Mac (ADR-103 does not allow MLX as an experiment runtime), so the entry should name a model built from our files.
- **`cloudflare`.** From the Experiment 38 notes (not re-read today): the Workers AI route is `/ai/run/@cf/cloudflare/clef` and `/ai/run/@cf/cloudflare/clef-flash`, it accepts the Jev request format, images go in an `images` list as base64 (at most 4 images, PNG, JPEG or WebP, 4 MiB and 16 MP each, 8 MiB in total), and the reply names the model without a version, so a silent model change cannot be detected. The address holds the account id. The key is the Cloudflare API token by reference (`env://CLOUDFLARE_API_TOKEN`). It is hosted, so a router needs the opt-in tick. Cloudflare's data retention terms for Workers AI have not been checked and must be read before the first hosted run. The adapter adds `TypeSafe-Danger-Zone-Images: true` only for a hosted image request. Only `compose_decision.py` imports a concrete adapter (the `providers-constructed-only-in-compose` contract).

### D3. Routers live in `omrs.jsonc` (confirmed by the operator 2026-11-02)

`document_routers` is a map of named recipes; `document_router` names the host default. Both live in `omrs.jsonc` (ADR-087). The CLI, the stdio MCP server and the watcher can then run the host router without the web server, and a hand edit applies like any other setting. Alternative: a workspace database table, like user profiles (ADR-080). Rejected: gotcha 18 says the workspace database holds no settings, and the host default must resolve in processes that only read the workspace. Rename and delete are refused while a saved profile names the router.

`document_router` is the router rule's flat setting (a `SettingField` on its descriptor, env `DOCUMENT_ROUTER`). The maps are file-only and are not part options: `reading_part_options` is for parts with no flat key, and this rule has one.

### D4. The router is a page rule at order 40

The router is a built-in page rule, name `document_router`, order 40. It adds one module `integrations/pdf/page_rules/document_router.py` (the rule object), one `PageRuleDescriptor` in `core/reading_parts.py` and one `register()` line in `page_rules/registry.py`, as `docs/guides/reading-parts.md` describes. The page unit gets no call to the router (the existing `No hand-wired rule` check stays).

**What the rule does.** `run(ctx)`:

1. Returns an empty outcome when no router is selected, when the router cannot run (D8), or when no judge is wired. With no router, `run` is a cheap early return before any page is read, so no digest, count or golden snapshot moves.
2. Takes the candidate pages: every page in `ctx.evidence` with non-blank text that the scan did not flag and that no earlier rule claimed. `ctx.claimed` is the set of pages that earlier rules dropped, sent direct or added. The rule reads it and skips those pages. A flagged page already goes to OCR, so it is never judged. OCR output is never judged.
3. Asks the judge one page at a time (ADR-074 rule 5): P(yes) for the page text (cut to the character limit) and, when the router sees images, the page image (D5).
4. Pages with P(yes) below the threshold are rejected. The rule returns them in `RuleOutcome.add`. Pages with a failed request keep their text and count unjudged.

**Amendment to ADR-112 decision 3 (the page-rule interface).** A rule today can drop or direct only pages that the scan flagged, so it cannot name an unflagged page. The amendment is small and additive, and the four older rules are untouched:

- `RuleOutcome.add`: pages the rule adds to the OCR route. Default empty.
- `PageRuleDescriptor.adds_pages` and the matching `register()` argument: the fifth declared fact, pinned like the other four (`drops_pages`, `sends_direct`, `has_post_check`, `has_degrade`). Default false.
- `RuleContext.claimed` (default empty) and `RuleContext.judge` (default `None`). Existing rules ignore both.

Fixed semantics of `add`:

1. **Only a rule that declares `adds_pages` may return `add`.** Any other rule that returns a non-empty `add` has returned a bad outcome. A built-in rule then fails the file. A discovered rule is skipped for the file, with one warning, and switched off, as for a stray `drop` or `direct`.
2. **A valid added page** is in the page scan, has non-blank text, is not flagged, and is not in `ctx.claimed`. Any other page in `add` is a bad outcome.
3. **Added pages go to the engine once.** They join the direct set. The pipeline folds `add` into that rule's direct pages, so a page that several rules name is sent once, in the one page-listed request. The local tier does not read them first: the router judged their text junk, and its engine is the reader that handles scans and handwriting.
4. **Later drops still apply.** A later rule's `drop` may name a page that an earlier rule added, and the page then leaves the direct set. The final direct set is the union of all direct sets minus every dropped page. No built-in rule runs after order 40, so this matters for rules added later.
5. **`pages_needing_ocr` stays the scan's count** (spec: it remains the count of flagged pages). `ocr_required` is true when any page is flagged, goes direct or is added (it already reads `flagged or direct`).
6. **Degrade.** When no engine reads an added page, the router's `degrade` hook (the declared flag `has_degrade`) returns it, so the local tier reads it with no post-check and one warning says so, as the non-Latin rule does. If the local tier cannot read it either, the page keeps its native text and counts unresolved.
7. **The router stamps its own count.** See Stamp.

**Why not mark rejected pages as flagged.** It would corrupt `pages_needing_ocr`, mix router verdicts into the scan count and move digests.

**Stamp.** The rule stamps the scalar counts `router_pages_judged`, `router_pages_accepted`, `router_pages_rejected`, `router_pages_unjudged` and the text `router_status`. The keys go in `EXCLUDED_EMBED_METADATA_KEYS` and in `IDENTITY_UNLISTED_KEYS`, as `pages_non_latin` does, so a default install keeps every digest. With no router, the rule stamps nothing.

**Scope.** The first plan had a `scope` field (`rescued` or `all-text`). Under the one routing unit the `rescued` scope has no pages (see Context), so the field goes, and no setting replaces it. A router judges the unflagged text pages that no earlier rule claimed.

**Cost, stated to the operator and not a setting.** Experiment 43 measured about 3.6 s per judged page with the local model, and about 2.7% of healthy pages (15 of 565) wrongly sent to OCR. These numbers go in `docs/guides/reading-parts.md` and in the router's help text. The group-6 experiment, when the operator runs it (G7), is the place to re-check them.

### D5. Page images

An image router renders one page at 150 DPI, long side at most 1,568 px, PNG (Experiment 43 values, so the frozen threshold stays valid). Page renderers are an ordered list in `integrations/pdf/page_images/`, held by the shared `PartRegistry` (ADR-112 decision 2), with one `register()` line per renderer. A renderer is not a reading part: it has no descriptor and no entry-point group. A later change can promote it. The first renderer is LiteParse, which is always installed and has a `screenshot` call (checked on 2026-11-02: one scanned page rendered in 0.12 s, 1,475 by 1,238 px). Where the optional `pdf-pypdfium2` extra is installed, pypdfium2 is the second renderer (same page in 0.09 s, 1,476 by 1,239 px). The router uses the first renderer that is available. A router whose renderers are all missing degrades with reason `renderer-missing`. Both renderers wrap PDFium, so images should match to about a pixel. Task 3.6 checks this on a scanned page and a vector-only page before the threshold is reused.

### D6. Model checks

- **Quantisation:** managed entries read `general.file_type` from the GGUF header (a few bytes, no model load) and accept Q8_0, F16, BF16, F32. External entries check the reported model name for a quantisation marker; otherwise "Quantisation not checked".
- **Projector:** managed image entries must declare `projector_file` (runtime flag `--mmproj`). Every image entry runs the smoke test: one bundled page image (a rendered fixture with known text), right text against wrong text, pass when P(yes) right minus P(yes) wrong is at least 0.5. The margin is a constant with a version, set from the Experiment 43 smoke results during task 2.3.
- **Build:** managed entries use the existing build check with the floor in Open Question 2. External entries: the build is not checked; the row says so.
- Results cache per process and per entry fingerprint. Test re-runs them on request.

### D7. Privacy

- Hosted is decided by address: anything not loopback is hosted.
- A hosted router needs `send_off_machine: true` on the router itself. A hosted decision model alone does not grant it.
- Settings shows the third-party name and what leaves (text; images when the flag is on). Hosted image routers carry "experimental".
- Logs never hold page text, images, keys or reply bodies. Diagnostics hold counts and fixed reasons only.

### D8. Degradation

Fixed reasons: `unknown-model`, `unreachable`, `quantisation-refused`, `projector-not-loaded`, `wrong-build`, `renderer-missing`, `needs-opt-in`, `request-failed`, `malformed-reply` (the check's text request got a reply OMRS cannot read). A file-level reason makes the rule return an empty outcome: reading behaves as with no router, and `router_status` holds the reason. A failed page request keeps that page's text and counts it unjudged. After 3 failed requests in a row the rule stops asking for that file, so a hung server costs at most 3 request timeouts, not one per page: the pages left keep their text and count unjudged, and the reason is `unreachable` when no page was judged. A page whose image fails to render is not a failed request. No file fails because of a router. A passing D6 check is kept for the process and entry, a failed one for 60 seconds (D9); the rule never contacts a model when a check has failed or the opt-in is missing.

### D9. Index identity

The router adds one entry to the `parser` block, key `document_router`, present only for PDF sources and only when a router is selected for the source. The descriptor declares it as `IdentitySpec(block="parser", keys=("document_router",), presence="pdf_when_on")`, the shape of the non-Latin rule. The builder goes in `core/ingestion/ocr_identity.py` and the call in `reader_identity.py`, because `source_state.py` is at 499 lines. The entry holds the question, threshold, image flag, character limit and the decision model's kind and model identity (model name; for managed entries the model and projector SHA-256), the rule `version` and `runnable`. `runnable` is the router's counterpart of the OCR worker fingerprint's `available`: it is true only when the PDF path wraps the reader in `OcrRoutedPdfInspector`, the OCR routes' judge hook (`integrations/ocr_worker/routes.page_judge`) gives a judge whose status is `None`, and an image router has a page renderer. A source read while the router could not run therefore stays stale, and a later ingest that can judge its pages reads it again. The identity is computed before the read, so a server can stop in between. `core/ingestion/router_identity.py` therefore also computes the digest with `runnable: false`, and both ingest paths store the source under that digest when a chunk of the read carries a `router_status` other than `ok`. The hook keeps `core` free of the composition root. A passing decision model check is kept for the process; a failed one for 60 seconds only, so a local server started after `omrs web` is found. It does not hold the router name, address, key or opt-in. Cost for real users: selecting or editing a router reprocesses PDF sources once on the next explicit ingest. With no router nothing changes. The operator's current indexes are test data.

### D10. Studio and profiles

`read.document` gets `document_router` (name, `none` or `null`). Built-in profiles use the host router. User profiles pick by name. `uninstall_profiles.py` is not involved, since routers name no extra.

### D11. Speed

Clef-Flash Q8_0 took 0.84 s a page for text (ADR-074). Experiment 43 measured about 3.6 s per judged page with images. A router judges every unflagged text page that no earlier rule claimed, so a long born-digital PDF pays for each page. The help text says so (D4, Cost). No router is selected by default.

### D12. How the judge reaches the rule

Compose builds a page judge from the selected router, its decision model entry and the resolved key (`compose_decision.py`, the only importer of a concrete adapter). The judge is a small object with one method, `judge(text, image) -> float | None`, plus the router recipe. It crosses `core/ingestion/backends/local.py` as `ocr_client` does: compose passes it, the local backend passes it to `build_pdf_reader(..., judge=...)`, and `OcrRoutedPdfInspector` puts it on `RuleContext.judge`. Task 3.1 confirms the exact path in the code before it is edited. With no router selected, the judge is `None`. The rule imports nothing from `core/providers/`.

## Resolved: page routing is the default

The first plan carried an open decision about making page routing the default and removing the 10% rule. Change `page-routing-default` did that. This change does not touch routing of flagged pages.

## Risks / Trade-offs

- [The Experiment 43 threshold was fitted on the same documents it was tested on, and under the old document rule] → the confirmation experiment (deferred to GATE G7) uses new documents and a page-based rule. The template labels the threshold "not confirmed".
- [Hosted image input is not production-ready per TypeSafe] → experimental label, opt-in per router, local default.
- [A router slows ingestion and sends some good pages to OCR] → opt-in; one request at a time; counts show the cost; the help text states about 3.6 s per judged page and about 2.7% of healthy pages sent to OCR (Experiment 43).
- [A local server on a shared port serves another model] → Test checks the model name and the smoke test; managed entries own their runtime.
- [Worker on protocol 1.0 cannot take page lists] → rejected pages keep their text, count unresolved, and a warning names the upgrade, as page routing does today.
- [The hook extension amends ADR-112's rule interface] → `add` is empty for the three older rules, the golden snapshots (`tests/unit/test_page_routing_golden.py`) and digest pins (`tests/unit/test_reading_parts_digest_pins.py`) must stay byte-identical, and a moved pin stops the work.

## Deferred

The confirmation experiment (tasks 6.1 and 6.2 of the first plan) waits for GATE G7 of the master flow (`doc-reading-master-flow`, task 4.3). The operator decided on 2026-11-04 to move it out of this change. After this change merges, the operator says whether to run it. If yes, it is a follow-up change.

## Migration Plan

No router by default, so nothing changes on upgrade. Rollback: revert; the `decision_models`, `document_routers` and `document_router` keys are then reported as unknown and ignored, and reading returns to the behaviour before this change.

## Open Questions

0. **Page-rule hook: settled by change `local-ocr-backends` (ADR-112, 2026-11-04).** The router registers as page rule order 40. D4 records the one amendment the hook needs (`RuleOutcome.add`, `adds_pages`), approved by the operator on 2026-11-04.

1. **Page renderer for image routers. Answered 2026-11-02 by the operator:** LiteParse first (always installed), pypdfium2 when its extra is installed, and more renderers through Integrations later. poppler `pdftoppm` (external program, used in Experiment 43) is not a product renderer. Remaining check: LiteParse and pypdfium2 images match closely on a scanned page and on a vector-only page (task 3.6).
2. **llama.cpp build floor for image decision requests. Answered 2026-11-02 by the operator:** floor b11941, the build Experiment 43 used. ADR-074 sets b11510 for the Metal fix, and b11941 is above it. A lower build may be allowed later, only after it passes the smoke test.
3. **Cloudflare Clef kind. Answered 2026-11-02 by the operator:** set up in this change, tested later. The kind is labelled "Not yet tested" until one recorded live request passes.
4. **Ollama kind. Answered 2026-11-02 by the operator:** set up in this change, tested later. The route exists (see D2 facts). The kind is labelled "Not yet tested" until one recorded live request passes.
5. **Router scope. Answered 2026-11-04 by the operator:** the `scope` field is removed. The router judges pages that are not flagged and not claimed by an earlier rule, and never judges OCR output. No new setting; the cost is stated in the guide and the help text (D4).
6. **ADR-112 amendment. Approved 2026-11-04 by the operator:** `RuleOutcome.add` and `adds_pages`, with the semantics in D4. The alternative, marking rejected pages as flagged, is refused: it would corrupt `pages_needing_ocr` and move digests.
7. **Confirmation experiment. Answered 2026-11-04 by the operator:** it is not part of this change. It waits for GATE G7 of `doc-reading-master-flow` (see tasks.md, Deferred).
