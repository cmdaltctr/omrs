# Tasks

Code tasks are tests first: write the test, run it, confirm it fails, then change the code. Count fast tests with `pytest --collect-only -q` before and after each group and update the pins in `tests/test_clean_base_tripwire.py` by test IDs.

## 1. List settings and old-key reading

- [x] 1.1 Tests first: `pdf_readers` and `ocr_engines` resolve from env (comma-separated), `.env` and `omrs.jsonc` (array); a wrong file type is ignored and listed; env locks the field (`tests/test_settings_resolver.py`, `tests/unit/test_settings_file.py`). Add the fields to `config/__init__.py`, `config/ocr_routes.py` and `EffectiveSettings`. Verify: the new tests pass and fail when the field validator is removed.
- [x] 1.2 Tests first: the single-value expansion (design D4): `pdf_inspector` gives `pdf_inspector, liteparse, pypdf`; `liteparse` gives itself; `auto` keeps the probe; old engine keys build the list; an empty fallback gives one engine; within one source the list key wins and the old key is reported. Implement in `config/`. Verify: `uv run pytest tests/unit -k "settings_file or document_reading_rules or legacy" -q` passes, and `check_legacy_env_vars` does not fire on `PDF_READER`.
- [x] 1.3 Tests first: `document_reading_problem` accepts a list of known names, refuses an empty list, duplicates and `auto` in a list; `setting_shapes` gives a list kind; a page write of `pdf_reader`, `ocr_engine_primary` or `ocr_engine_fallback` is refused and names the list key; a page save writes the list key and removes old keys in one atomic write with comments kept (`config/rules.py`, `setting_shapes.py`, `settings_file_write.py`). Verify: the tests pass, and `omrs config init` output shows `pdf_readers` and `ocr_engines` but not the old keys.

## 2. Reader chain

- [x] 2.1 Tests first: start-up picks the first installed listed reader; none installed logs an error and uses pypdf; `auto` in a list is dropped with a warning (`capabilities.resolve_pdf_reader`, `compose_settings.py`). Verify: the tests pass with `PDF_READER=pypdf` test defaults unchanged.
- [x] 2.2 Tests first: add `integrations/pdf/chain.py` (design D3). `PdfInspectorReader` takes tier names; bare construction keeps `liteparse, pypdf`; list `pdf_inspector, pypdfium2` retries with pypdfium2 only; a list of one runs no tier; tier exceptions hand over and the last propagates. Keep the existing rescue tests green. Add the module row to the integration inventory in `docs/guides/architecture.md`. Verify: `uv run pytest tests -k "pdf_inspector or rescue or reader_fallback or strategy_registration" -q` passes; a mutation that hard-codes `liteparse` makes the custom-list test fail.
- [x] 2.3 Tests first: identity (design D5): `pdf_reader=pdf_inspector`, `pdf_readers=pdf_inspector,liteparse,pypdf` and the code default give the digest pinned from `v3` before this change; a different list adds `parser.pdf_readers` and moves only PDF digests (`core/ingestion/source_state.py`). Verify: the pinned-digest test passes and fails if the old key is dropped from the payload.
- [x] 2.4 Update `docs/guides/configuration.md` "PDF reading" with the list, the D2 rule and the default list, and add an upgrade note. Update `.env.example`. Verify: the guide's reader table guard test passes and the documented env line resolves as written.

## 3. OCR engine list

- [x] 3.1 Tests first: `OcrRoutes` holds a tuple; the first available route serves; three engines with only the third available use the third; an empty answer never moves a request; shared commands share one client; the operator-stop retry goes once to the next available route (`integrations/ocr_worker/routes.py`, `dispatch.py`). Verify: `uv run pytest tests -k "ocr_route or ocr_worker or maths_rout" -q` passes; a mutation that retries on empty output fails a test.
- [x] 3.2 Tests first: identity keeps `ocr_worker_fingerprint` and `ocr_fallback_fingerprint`; a list of one gives the unavailable payload; a third engine adds `ocr_more_fingerprints` (`core/ingestion/ocr_identity.py`, `source_state.py`). Verify: the default two-engine digest equals the pinned pre-change digest.
- [x] 3.3 Update `runtime_components.py` so engine items name `ocr_engines` in `used_by`, with its tests. Update `docs/guides/configuration.md` "OCR fallback and isolated engines" and "Document reading values", and remove the "cannot set no fallback engine" note. Verify: `uv run pytest tests/unit -k runtime_components -q` passes.

## 4. Studio and HTTP contract

- [x] 4.1 Tests first: `ReadParams` accepts `pdf_readers` and `ocr_engines`; old options still validate and expand; both forms together fail with both names; a saved graph with `pdf_reader: pypdf` keeps its identity; `uninstall_profiles.py` finds a reader in either form (`graph_adapters_catalogue.py`, `graph_adapters_values.py`, `graph_fingerprint.py`, `core/pipelines/levers.py`). Verify: `uv run pytest tests -k "read_params or graph_fingerprint or uninstall_profiles or levers" -q` passes.
- [x] 4.2 Contract first (the settings `kind` enum gains `list`; a PUT of an old key is refused): change `openapi.yaml` (`IntegrationList.pdf_readers` item schema, document-reading keys and array values, read-step parameters) and confirm the conformance tests fail. Then add the `pdf_readers` block to `routes/integrations.py` from `capabilities.pdf_reader_options()` and list support in `transports/api/document_reading.py`. Update `docs/guides/pipelines.md`. Verify: `uv run pytest tests/unit -k "openapi or integrations or document_reading" -q` passes.

## 5. Front end

- [x] 5.1 Load the `omrs-design` skill. Tests first (Vitest): `PdfReadersSection.tsx` shows one row per reader, "Not installed" with a copy command, use positions, and the chip count for a reader in use but missing; add the section to `sections.ts` and every typed fixture. Verify: `npm run lint`, `npm run typecheck` and `npm test` pass in `web/`.
- [x] 5.2 Tests first: `OrderedListControl.tsx` (add, remove, move, empty list refused) used by `DocumentReadingSection.tsx` for both lists, with lock and "Not provisioned" or "Not installed" lines; Studio reader and engine controls use the same control with Inherit. Keep each component under 200 lines. Verify: `npm test` passes; `npm run typecheck` finds no fixture without the new fields.
- [x] 5.3 Check Integrations › PDF readers and Settings › Document reading in a browser at 1280 px and 390 px (Chrome DevTools, else Orca; scratch config folder, free port). Warn the user before starting the server. Save screenshots in the change folder. Update `docs/guides/web-workspace.md`. Verify: no horizontal scroll at 390 px, and move and remove buttons are reachable and labelled.

## 6. Integration checks

- [ ] 6.1 Run `./scripts/local_ci.sh`. Verify: no step prints `SKIPPED`, every step passes, including `tests/test_file_size_ceiling.py` and the tripwire.
- [ ] 6.2 Run `openspec validate ordered-reader-and-ocr-lists --strict` and `openspec validate --all --strict`. Verify: both pass.

## Workflow follow-up

- Branch `feat/ordered-reader-and-ocr-lists` from `v3` in a sibling worktree. Open a pull request into `v3`. Do not merge.
- Watch CI to the end, fix failures, and answer every review thread.
- Archive the change after the operator approves the merge.
