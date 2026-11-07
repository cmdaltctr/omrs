# ADR-112: Reading Parts: One Descriptor, an Ordered Page-Rule Pipeline, Ordered Fallback Lists and Entry-Point Discovery

- **Date:** 2026-11-04
- **Status:** Accepted (2026-11-04; built and merged to v3 in PR #168). Amended by ADR-110 (2026-11-05): `RuleOutcome.add`, `RuleContext.claimed`, `RuleContext.judge` and the fifth declared fact `adds_pages`. Amended by [ADR-114](114-per-backend-local-ocr-cuts.md) (2026-11-06): decision 4, the cut override and `keeps_scripts`. Amended by [ADR-116](116-skip-blank-switch-and-fixed-page-rule-order.md) (2026-11-07): decision 3, the `blank` rule switch.
- **Deciders:** Maintainer
- **Amends:** [ADR-037](037-architecture-v2-conformance.md) (decision 1: registries stay the dispatch, and entry points become a second source of names), [ADR-066](066-tiered-reader-fallback-chain.md) (fallback follows list order, not a fixed chain), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (page routing runs as a pipeline of registered rules), [ADR-105](105-pipeline-steps-own-their-ocr-settings.md) (decision 1: the Read document step gains the local backend list)
- **Related:** [ADR-072](072-modular-ocr-engines-dots-mocr-primary-and-maths-routing.md) (the `omrs.ocr_engine` entry-point group, the precedent), [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) (owns the word "plugin"), [ADR-110](110-decision-models-and-named-document-routers.md) (routers join the rule pipeline), [ADR-050](050-configure-pdf-inspector-as-default-reader.md) (reader metadata in the registry), [ADR-104](104-pdf-inspector-emits-page-documents.md) (one document per page)
- **Change:** `openspec/changes/local-ocr-backends/`
- **Experiment:** `experiments/46-local-ocr-backends-2026-11-04/` (PASS)

## Context

The operator wants page reading to work like a car. Each part can be replaced, and a broken part can be found on its own. The code does not work like that today. All paths below are under `src/omrs/` unless they start with `tests/` or `pyproject.toml`.

1. **A new page rule touches many files.** The non-Latin rule (PR #167, merge `6959d774`) is one module, `integrations/pdf/script_routing.py`. It still edited 16 other production files in `src/` and 5 in `web/src/`. Each copy is a hand list of keys or a hand field, for example `config/rules.py:139-146`, `core/ingestion/graph_adapters_catalogue.py:128-136` and `core/pipelines/levers.py:87-95`.
2. **The local OCR tier has no seam.** It is one hard call to `pdf_inspector.process_pdf_with_ocr` (`integrations/pdf/page_routing.py:195-206`). A second backend has nowhere to go.
3. **Page rules are hand calls.** `ocr_routing._page_unit_documents` calls the blank, maths and non-Latin rules one after another (`integrations/pdf/ocr_routing.py:188-195`). Their order carries meaning that only comments state.
4. **The registries share nothing.** There are 10 registries (`tests/test_strategy_registration_inventory.py:62-72`). Each one repeats its own dict, cache and lazy import. No shared helper exists.
5. **No host code discovers parts.** The host never calls `importlib.metadata.entry_points`. Only the OCR worker does, for the `omrs.ocr_engine` group (`ocr-workers/core/src/omrs_ocr_worker_core/engine.py:27,100,113`).
6. **A part that fails is not shown.** When the local tier switches itself off at run time, it records a reason in `_LOCAL_TIER_BROKEN` (`integrations/pdf/page_routing.py:253-264`). Nothing outside `integrations/pdf/` reads that reason. The routing rules have no health row at all.

Experiment 46 gives the first real second part. Indra OCR reads Arabic and Devanagari well: it keeps 58 of 69 pages local, with 0 bad pages, at 0.10 s per page. It reads Bengali badly (median recall 0.59), and its cut still keeps 53 of the 60 Bengali pages. One value for "the local backend" therefore cannot serve all scripts. The simulation in `openspec/changes/local-ocr-backends/evidence/ordered-list-simulation.md` runs the list `[indra (keeps arabic, devanagari), pp-ocrv6-small]` on the same 229 pages. Latin pages give 56 kept and 3 bad, the same as today. All Bengali pages go to the OCR engine, the same as today.

**A note on words.** In this repository "plugin" already means a user-registered external executable with a hashed manifest (ADR-075, `core/plugins/`, `GET /v1/plugins`). This ADR therefore uses **reading part** for a replaceable piece of page reading, and **part descriptor** for the data record that describes it. Do not call a reading part a plugin in code, settings or documents.

## Decision

1. **One part descriptor, pure data.** `src/omrs/core/reading_parts.py` defines the descriptor. The module imports nothing from `omrs`. A descriptor holds the name, the kind, the import path, the install extra or probe module, the settings fields, the identity contribution and the UI label. `config/` may import the module. Integration code keeps its lazy `register()` lines and does not import the descriptor type; a test pins that the descriptor names match the registry names, as `tests/unit/test_document_reading_rules.py:54-55` does today for PDF readers. This keeps the import contracts `config-is-leaf` (`pyproject.toml:631-655`), `integrations-are-leaves` (`:660-689`) and `settings-models-are-pure-data` (`:209-222`) intact.
2. **One shared registry helper.** A small helper gives every registry the same dict, cache, lazy import and listing. The page-reading registries (PDF readers, local OCR backends, page rules) adopt it in change `local-ocr-backends`. The other registries adopt it later, one change each.
3. **Page rules are an ordered, registered pipeline.** Blank, maths and non-Latin become registered page rules that run in a fixed order. ADR-110 routers join the pipeline next. The order and semantics stay as today: the blank rule removes pages first; the maths rule reads every page and then drops blank ones; the non-Latin rule reads routed pages only and keeps its own local post-check reason and degrade path (`integrations/pdf/page_routing.py:231-232`, `integrations/pdf/ocr_routing.py:258-270`).

   **Amendment by ADR-110 (2026-11-05).** A rule can now add pages that the scan did not flag. `RuleOutcome.add` holds the added pages. `RuleContext.claimed` holds the pages that earlier rules dropped, sent direct or added. `RuleContext.judge` carries the page judge that compose builds. The descriptor and `register()` gain a fifth declared fact, `adds_pages`, pinned like the other four. All three default to empty, `None` or false, so the blank, maths and non-Latin rules do not change. The semantics are fixed:

   - Only a rule that declares `adds_pages` may return a non-empty `add`. Any other rule has returned a bad outcome.
   - A valid added page is in the page scan, has non-blank text, is not flagged and is not claimed. Any other page in `add` is a bad outcome.
   - Added pages join the direct set once. A page that several rules name goes once in the page-listed request.
   - A later rule's `drop` removes an added page. The final direct set is the union of all direct sets minus every dropped page.
   - `pages_needing_ocr` stays the count of pages that the scan flagged.

   **Amended by ADR-116 (2026-11-07).** The `blank` rule gains the `ocr_skip_blank_pages` switch. The rule order stays fixed.
4. **Every fallback is an ordered list.** PDF readers (`PDF_READERS`) and OCR engines (`OCR_ENGINES`) are lists already. Local OCR backends become a list too: setting `ocr_local_backends` (env `OCR_LOCAL_BACKENDS`), default `["pp-ocrv6-small"]`. Each local backend declares its calibrated confidence cut and `keeps_scripts`, the scripts whose output it may keep. A backend keeps a page only when the page passes its cut and, if it declares `keeps_scripts`, the output script is in that set. A page it does not keep passes to the next entry. A page that no entry keeps goes to the OCR engines. `ocr_local_min_confidence` becomes an optional override: unset, each backend uses its own cut; set, it replaces the cut of every listed backend (design D8 to D10 of change `local-ocr-backends`).

   **Amendment by ADR-114 (2026-11-06).** The cut override `ocr_local_min_confidence` is retired. The map `ocr_local_cuts` holds one operator cut per backend, and a backend without an entry uses its descriptor default (0.92 for `pp-ocrv6-small`, 0.94 for `indra`). The descriptor field `keeps_scripts` and the escalation reason `script_not_kept` are removed: confidence alone decides.
5. **Entry-point discovery with the standard library.** The host reads installed distributions with `importlib.metadata.entry_points`. This is the pattern that the stevedore library made common, without a dependency on stevedore. Each part kind has one group: `omrs.pdf_readers`, `omrs.local_ocr_backends` and `omrs.page_rules` (design D11). An entry point value is a `module:attr` path to the part's descriptor, which the registry imports lazily, as for a built-in. A name that clashes with a built-in is refused and the built-in stays. When two distributions declare the same name, the earlier one keeps it and the later one is refused. Each refusal logs one warning that names the distribution and the clash. A part that fails to load is skipped and shown as broken. It never stops start-up. Discovery runs only in the composition root, never in `config/` or `core/`.
6. **Health reads the descriptors.** The health and diagnosis surfaces (for example `transports/api/runtime_components.py`) list every reading part from its descriptor, with one state: ready, missing, broken or switched off, and a reason. A local OCR backend that switches itself off at run time shows its reason here (the per-backend switch-off replaced `_LOCAL_TIER_BROKEN`). As built, `GET /v1/integrations` carries a `reading_parts` block: each listed local backend (installed, model present, switched off and why, effective cut), each page rule (enabled, version, source) and each discovered part (distribution, version, problem). A broken or missing part is then visible on its own.
7. **Zero behaviour change for current users.** Before the refactor, the change adds digest pins for the gaps the audit found: non-Latin `detect` and `always`, the resolved local model, and maths routing off. With the existing pins (`tests/unit/test_pdf_reader_identity.py:20-24,44-57`, `tests/unit/test_index_identity_baseline.py:280,326`, `tests/unit/test_read_step_lists.py:36-39,152-172`), every index digest and every output stays byte-identical. A local backend list other than the default adds one entry to the PDF `parser` block only, so PDF sources re-index once and other sources keep their digest. The descriptor must reproduce the three identity shapes that exist today: the blank version inside `ocr_routing` (`core/ingestion/ocr_identity.py:96`), the maths block that is always present (`core/ingestion/source_state.py:193`), and the non-Latin `parser` entry, present only when not `off` and only for PDFs (`core/ingestion/reader_identity.py:37-43`, `core/ingestion/embed_exclusions.py:62`).
8. **The old engine keys stay as input aliases.** `ocr_engine_primary` and `ocr_engine_fallback` stay documented and accepted as input, because removing them moves saved graph fingerprints (`core/ingestion/graph_fingerprint.py:59`). Their one internal reader, `compose_runtimes._ocr_runtimes` (`compose_runtimes.py:45,208`), reads the engine list instead. This also fixes a third engine's runtime that is missing from `GET /v1/runtimes` (likelihood 2, impact 3, score 6).
9. **The house rule from now on.** A new reading part is one file, one `register()` line and its tests. A test enforces this for Indra, the first part added after the refactor (`tests/unit/test_indra_is_one_part.py`): its name may appear in production code only in its own file, its descriptor entry and its registration line. Root `AGENTS.md` invariant 11 is reworded at implementation time to say so, and to name entry points as the second source.

## Consequences

### Positive

- A new reading part, such as Indra, is one file. The 21-file edit that PR #167 needed does not happen again.
- A broken or missing part shows on the health surface with a reason. The operator can diagnose one part without reading logs.
- An external package, such as a future `omrs-indra`, can ship a part without a change to OMRS.
- Bengali and Latin pages keep today's result when Indra joins the list (simulation file).
- The `compose_runtimes` runtime gap for a third engine closes.

### Negative

- One large refactor across settings, routing, identity, health and the web lists. It needs the new digest pins first, or a silent identity change can pass review.
- The descriptor must reproduce three different identity shapes exactly. A uniform shape would be simpler, but it would change every digest.
- Settings generated from descriptors read less plainly than hand-typed fields. This affects a later change, not this one.
- Tests patch functions by module path (gotcha 8b). The audit counts about 37 such targets, for example `ocr_routing.find_blank_pages` (15) and `page_routing._LOCAL_TIER_BROKEN` (4). A registry that captures objects at registration time turns those patches into no-ops, so the targets must stay where they are or move with their tests.
- An installed external part runs code inside the OMRS process. Discovery reads installed distributions only and downloads nothing, but the operator owns what is installed.

### Neutral

- The index identity still changes when a part is added to a list. That is by design: a new part can change the text.
- The OpenAPI contract and the web lists stay hand-typed for now. Drift tests compare them with the descriptors.
- Built-in parts keep their lazy registration. Entry points add names; they do not replace `register()`.

## Alternatives Considered

| Option | Why not |
| --- | --- |
| Depend on the stevedore library | A new core dependency for what `importlib.metadata.entry_points` already does. |
| A new top-level package for parts (for example `omrs/parts/`) | It fails `tests/unit/test_verification_gaps_boundaries.py:59-70`, which pins the top-level packages. |
| Keep hand wiring per rule | Each new rule edits about 21 production files (PR #167). |
| Generate the OpenAPI enums and web lists from descriptors now | Too much in one change. Deferred; drift tests guard the copies instead. |
| One local OCR backend value instead of a list | Indra alone would keep 53 Bengali pages, 9 of them bad. The simulation shows the list keeps Latin and Bengali unchanged. |

## Verification

1. **One-file test.** Add a fake reading part in one file with one `register()` line. The test suite passes, and the part shows in the registry listing and on the health surface, with no other production file edited.
2. **Digest pins.** Every pin in decision 7, old and new, passes unchanged before and after the refactor.
3. **Discovery test.** A fake distribution with an entry point in each group is found at composition. A fake that fails to import shows as broken and start-up continues. A fake that clashes with a built-in name is refused, and the message names both sources.
4. **Import contracts.** `lint-imports` passes with no new non-permanent ignore.
5. **Runtime list.** With three engines in `OCR_ENGINES`, `GET /v1/runtimes` lists the runtime of each engine that declares one.

## References

- `openspec/changes/local-ocr-backends/` (proposal, design, tasks)
- `openspec/changes/local-ocr-backends/evidence/ordered-list-simulation.md`
- `experiments/46-local-ocr-backends-2026-11-04/report.md`
- PR #167 (non-Latin script routing, merge `6959d774`)
- Root `AGENTS.md`, architecture invariant 11 and gotcha 8b
- Amended at implementation time, one status line each: ADR-037, ADR-066, ADR-069, ADR-105
