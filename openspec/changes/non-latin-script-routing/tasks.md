# Tasks

Code tasks are tests first: write the test, run it, confirm it fails, then change the code. Update the pins in `tests/test_clean_base_tripwire.py` by test IDs after each group.

## 1. Setting and detector

- [ ] 1.1 Tests first: `ocr_non_latin_routing` defaults to `off`, accepts `off`, `detect`, `always`, and an unknown value stops start-up naming the three (`config/__init__.py`, `config/rules.py` `ACCEPTED` and `DOCUMENT_READING_KEYS`, `core/settings.py`). Verify: `uv run pytest tests -k "settings_resolver or document_reading_rules" -q` passes; `omrs config init` lists the key.
- [ ] 1.2 Tests first: `integrations/pdf/script_routing.py` detector (design D2): 7 Latin letters gives no verdict; 300 letters with 280 Arabic gives non-Latin; accented Latin counts as Latin; digits and punctuation are not letters; a test pins the constants to `SCRIPT_DETECTOR_VERSION`. Add the module row to the integration inventory in `docs/guides/architecture.md`. Verify: the tests pass; changing the share constant without the version fails the pin test.

## 2. Routing under the page unit

- [ ] 2.1 Tests first, with pdf-inspector mocked: `detect` sends a flagged page with an Arabic text layer direct and leaves a scanned page with no text layer on the local tier; `always` sends every flagged page direct and runs no local tier; unflagged pages keep native text; a maths page that is also non-Latin appears once. Implement in `script_routing.py` and a small call in `_page_unit_documents`. Verify: `uv run pytest tests -k "page_unit or maths_rout or script_rout" -q` passes; `ocr_routing.py` stays at or under 500 lines.
- [ ] 2.2 Tests first: under `detect`, a local result of 400 Devanagari letters at confidence 0.95 escalates with `non_latin_output`; a Latin result at 0.95 keeps its text (`page_routing.local_ocr` reasons). Verify: the tests pass; a mutation that drops the new reason fails one.
- [ ] 2.3 Tests first: no available OCR engine makes `always` and `detect` fall back to today's split with one warning per file. (The `document` unit no longer exists, so no document-unit test is needed.) Verify: the tests pass.
- [ ] 2.4 Tests first: identity block present only with a mode other than `off`; the `off` digest equals the pinned pre-change digest; `pages_non_latin` is stamped only when the setting is on and is in `EXCLUDED_EMBED_METADATA_KEYS` (`ocr_identity.py`, `source_state.py`, `embed_exclusions.py`). Verify: `uv run pytest tests -k "identity or embed_exclusion" -q` passes.
- [ ] 2.5 Update `docs/guides/configuration.md` "OCR routing unit and the local OCR tier" with the three values, what `detect` cannot see, the interactions (design D6) and the identity effect. Verify: the documented env line resolves as written in a test or a manual `omrs config show`.

## 3. Studio, contract and Settings page

- [ ] 3.1 Tests first: `ReadParams` accepts `ocr_non_latin_routing`, refuses `arabic` with `invalid_parameter`, and records the value in the step identity. Change `openapi.yaml` first for the document-reading key and confirm the conformance tests fail. Update `docs/guides/pipelines.md`. Verify: `uv run pytest tests/unit -k "openapi or read_params or document_reading" -q` passes.
- [ ] 3.2 Load the `omrs-design` skill. Tests first (Vitest): the Document reading row shows the three choices and the scan note; Studio shows the option with Inherit. Check at 1280 px and 390 px in a browser (warn the user before starting a server; scratch config folder, free port). Verify: `npm run lint`, `npm run typecheck` and `npm test` pass in `web/`; no horizontal scroll at 390 px.

## 4. Experiment before any default

- [ ] 4.1 Reserve the next free experiment number and write the protocol with the `s-experiment` skill (format `omrs-experiment/1`). Inputs, read only: Experiment 33 `labels.json`, stored local OCR outputs (`output/.local_ocr_text`, `output/local_ocr/pages.json`) and Experiment 37 engine outputs for `io01`, `io02`, `io03`, `io07` and every Latin page. No model run, no download. Pre-register in `plan.json`: (a) pages with a pre-OCR verdict, (b) post-local verdicts per document, (c) false positives on Latin pages, (d) local seconds saved by `always`, (e) non-Latin pages kept by the 0.9 cut. Verify: `plan.json` is committed before any analysis output exists.
- [ ] 4.2 Run the analysis with the shipped detector code and write `report.md`. Default rule, fixed in the protocol: propose `detect` as default only if (e) finds at least one non-Latin page that `detect` escalates and (c) is zero; otherwise keep `off`. State the gap: the corpus holds no born-digital non-Latin PDF with flagged pages. Verify: the report gives counts per document, the rule outcome, and the limitation; `experiment.json` validates.

## 5. Integration checks

- [ ] 5.1 Run `./scripts/local_ci.sh`. Verify: no `SKIPPED`, every step passes, including the file-size ceiling and the tripwire.
- [ ] 5.2 Run `openspec validate non-latin-script-routing --strict` and `openspec validate --all --strict`. Verify: both pass.

## Workflow follow-up

- Branch `feat/non-latin-script-routing` from `v3` in a sibling worktree. Open a pull request into `v3`. Do not merge.
- Watch CI to the end, fix failures, and answer every review thread.
- A default change, if the experiment supports it, goes in its own change with an ADR.
- Archive after the operator approves the merge.
