# Proposal: page reading built from replaceable reading parts

## Why

Experiment 46 passed (`experiments/46-local-ocr-backends-2026-11-04/report.md`). Indra OCR 1.1.2 passes gates G1 to G4 for Arabic and Devanagari at a cut of 0.90. It keeps 58 of 69 such pages local and none of the kept pages is bad. It reads Bengali badly (median recall 0.59), so it must not keep Bengali pages. A simulation on the same data (`evidence/ordered-list-simulation.md`) shows that an ordered list `[indra (keeps arabic, devanagari), pp-ocrv6-small]` keeps those 58 pages and leaves Latin and Bengali pages exactly as today. The output script is detected correctly on 229 of 229 pages.

The code cannot take Indra as one part today. The audit of 2026-11-04 found:

1. The local tier is one hard call to pdf-inspector (`integrations/pdf/page_routing.py:195-206`). There is no seam.
2. Each page-routing rule is wired by hand. Non-Latin routing touched 21 production files (16 in `src/`, 5 in `web/src/`). Maths routing touches 15. Each rule has its own call site in `ocr_routing._page_unit_documents` (`ocr_routing.py:188-198`).
3. The 10 registries repeat the same `_registry`, `_cache`, `get()` and probe code. No shared helper exists.
4. Hand-typed lists repeat the same keys in Python, the HTTP contract and the web app (`config/rules.py:139-146`, `graph_adapters_catalogue.py:128-136`, `levers.py:87-95`, `openapi.yaml:11414-11420`, `web/src/api/settingsDocumentReading.ts:15-25`).
5. Health is hand-coded. The local tier's run-time switch-off (`page_routing.py:253-264`) is not shown anywhere. Page rules have no health row.

The operator decided on 2026-11-04 to make page reading plug-and-play "like a car": each part is replaceable and can be diagnosed on its own. This change does that once, then adds Indra as the proof.

## Terms

- **Reading part** (or **part**): one replaceable unit of page reading. Three kinds are in scope: a PDF reader, a local OCR backend and a page rule. The word "plugin" is not used, because ADR-075 and `src/omrs/core/plugins/` use it for marimo-style executables.
- **Part descriptor**: one pure-data record per part. It names the part, its import path, its extra and probe, the settings it reads with defaults, its exact index-identity contribution, its health facts, and its UI label and help key.
- **Page rule**: a part that decides, per page, which pages leave the route, which go direct to the OCR engine, and which local results escalate. Blank pages, maths routing and non-Latin routing become page rules.
- **Local OCR backend**: a part that reads page images locally and returns text with one confidence per page.

## What Changes

- **Part descriptors** in one pure-data module, `core/reading_parts.py`. It imports nothing from `omrs` (precedent `core/reading_lists.py`).
- **A shared registry helper** for the page-reading registries: PDF readers, local OCR backends and page rules. The nine `core/` registries adopt it in later changes.
- **A page-rule pipeline** on one hook in `ocr_routing._page_unit_documents`. Blank, maths and non-Latin become ordered, registered rules. The pipeline reproduces today's order and semantics exactly. Change `document-reading-routers` registers its routers as the next rule.
- **An ordered local OCR list**, `ocr_local_backends` (env `OCR_LOCAL_BACKENDS`), default `["pp-ocrv6-small"]`. Each backend declares its calibrated cut and the output scripts it may keep. A page a backend escalates, or whose output script it may not keep, passes to the next backend. After the last backend, today's shared escalation to the OCR engine applies. `ocr_local_min_confidence` becomes an optional override of each backend's cut.
- **Entry-point discovery** (standard library `importlib.metadata.entry_points`) in groups `omrs.pdf_readers`, `omrs.local_ocr_backends` and `omrs.page_rules`. It runs once in compose. A broken or clashing external part is skipped with a warning and shown in health. It never stops start-up.
- **Diagnosis from descriptors**: the Integrations page lists each local backend (installed, model present, switched off at run time), each page rule (on or off, version) and each discovered part.
- **One fix on the way**: `compose_runtimes._ocr_runtimes` reads the two legacy engine keys (`compose_runtimes.py:45,208`), so a third engine's runtime is missing from `GET /v1/runtimes` (likelihood 2, impact 3, score 6). It moves to the engine list. The legacy keys stay as input aliases (`config/rules.py:108`).
- **Indra OCR as one new backend** behind a new optional extra `local-ocr-indra`, with a cut of 0.90 and `keeps_scripts = {arabic, devanagari}`. It is not in the default list. The operator approves the extra first.
- **Zero behaviour change for current users, proven first.** New digest pins and golden end-to-end snapshots are written before any refactor. Every pin stays byte-identical.
- **Not in this change:** generated web or OpenAPI lists (drift tests pin them instead), the nine `core/` registries, OCR engines (they already plug in through the worker's `omrs.ocr_engine` entry point), a Bengali backend, and any default change.

## Capabilities

### New Capabilities

- `local-ocr-backends`: the ordered list, the backend contract, per-backend cuts and kept scripts, identity, producer names, and the Indra backend.
- `reading-parts`: part descriptors, the shared registry helper, entry-point discovery, part options, diagnosis, single-source lists and drift tests, and the engine-list runtime fix.
- `page-routing-rules`: the rule interface, rule order, the three built-in rules, post-checks, degrade paths and failure handling.

### Modified Capabilities

- `pdf-reader`: the local cut, the escalation rule and the missing-runtime rule now apply to an ordered list of backends.
- `script-page-routing`: the `detect` post-check does not escalate output that the backend may keep.

## Impact

- **New code:** `core/reading_parts.py`; `integrations/part_registry.py`; `integrations/pdf/page_rules/` (interface, pipeline, registry); `integrations/pdf/local_ocr/` (registry, chain, `pp_ocrv6_small.py`, later `indra.py`); a health module under `transports/api/`.
- **Changed code:** `ocr_routing.py`, `page_routing.py`, `blank_pages.py`, `maths_routing.py`, `script_routing.py`, `pdf/registry.py`, `config/` (list setting, override, derived key lists), `core/settings.py` (split first, at 499 lines), `compose.py` and `compose_settings.py` (discovery), `compose_runtimes.py`, `core/ingestion/ocr_identity.py`, `graph_adapters_catalogue.py`, `levers.py`, `embed_exclusions.py`, `runtime_components.py`, `integrations_catalogue.py`.
- **HTTP contract and web:** health fields, the Settings row and Read-step key for `ocr_local_backends`, Integrations page rows.
- **Dependencies:** none in the base install. New optional extra `local-ocr-indra` (`indra-ocr==1.1.2`, which pulls onnxruntime and opencv-python-headless; no PyTorch), after operator approval.
- **Identity:** default digests do not move. A non-default list re-indexes PDF sources once.
- **Docs:** ADR-112 (drafted in parallel, `docs/adr/112-reading-parts-descriptor-pipeline-and-discovery.md`), a new guide `docs/guides/reading-parts.md`, and updates listed in tasks group 8.
- **Experiment 46:** done. Its data-store copy (task 0.5) stays open until worktree removal.
