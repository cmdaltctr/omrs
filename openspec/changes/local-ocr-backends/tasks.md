# Tasks

Code tasks are tests first: write the test, run it, confirm it fails, then change the code. After each group, update the pins in `tests/test_clean_base_tripwire.py` by test IDs: diff the collected IDs against the last pin, because per-file counts miss replaced cases.

## 1. Pin today's behaviour

- [ ] 1.1 Find every test that patches the pdf-inspector OCR call or the identity probe in `page_routing` (`tests/unit/test_local_ocr_tier.py`, `tests/test_ocr_error_boundary.py`, `tests/test_ocr_routes.py`, `tests/test_page_provenance.py`, `tests/test_ocr_identity_reingestion.py`). List them in the PR description. Verify: `grep -rn "process_pdf_with_ocr\|_probe_local_model_identity\|_model_identity" tests` is listed and each file is covered by a task below.
- [ ] 1.2 Tests first: pin the default `local_tier` identity payload and the default source digest as they are on `4f6dac05`. Pin the default cut 0.9 and the escalation reasons for a page at 0.89, 0.9 and with no confidence. Verify: the tests pass on the current code. They stay green through every later group.

## 2. Registry and dispatch

- [ ] 2.1 Tests first for `integrations/pdf/local_ocr_registry.py`: `register`, `describe`, `get` and `available` work as in `registry.py`; registration with a cut and no `calibrated_by` raises `ValueError`; `get` of an unknown name raises `KeyError` that lists the names; importing the module imports no backend (a test asserts `omrs.integrations.pdf.local_ocr_pp_ocrv6` is not in `sys.modules` after import). Implement the module and the `pp-ocrv6-small` registration (cut 0.9, `calibrated_by` `39-local-tier-escalation-2026-09-30`). Verify: `uv run pytest tests -k "local_ocr_registry" -q` passes; a mutation that drops the `calibrated_by` check fails one test.
- [ ] 2.2 Tests first with a fake backend registered in the test: `local_ocr` dispatches to it, builds `LocalOcrPage` from its `BackendPage` list, and applies the shared rule. Cover `missing_page`, `empty_text`, `low_confidence` (fake cut 0.7, page at 0.65 and at 0.75), `hosted_recommended` and `non_latin_output`. Then move the pdf-inspector call and the identity probe into `integrations/pdf/local_ocr_pp_ocrv6.py` and make `local_ocr` and `resolve_local_model_identity` dispatch through the registry. The identity cache key gains the backend name. Fix the patch targets listed in 1.1. Verify: `uv run pytest tests -k "local_ocr or page_routing or page_provenance or ocr_error_boundary" -q` passes; `page_routing.py` is under 500 lines; `ocr_routing.py` is unchanged.
- [ ] 2.3 Tests first: a backend that raises a non-`Exception` panic still switches the local tier off, and the identity probe failure is still not cached. These behaviours exist today and move under dispatch. Verify: the tests pass before and after the move.

## 3. Setting, cut and identity

- [ ] 3.1 Tests first: `ocr_local_backend` defaults to `pp-ocrv6-small`; an unknown value stops start-up and the message names `pp-ocrv6-small`; a registered backend with no cut is refused with a message that says so (`config/__init__.py`, `config/rules.py` `ACCEPTED`, `core/settings.py`, `compose_settings.py`). Do not add the key to `DOCUMENT_READING_KEYS`. Verify: `uv run pytest tests -k "settings_resolver or document_reading_rules or effective_settings" -q` passes; `omrs config init` lists the key.
- [ ] 3.2 Tests first: `ocr_local_min_confidence` defaults to `None`; `effective_min_confidence` returns 0.9 for the default backend when it is unset, the set value when it is set, and the fake backend's cut for the fake backend. Retype the field in `config/__init__.py` and `core/settings.py`, and add the helper to the registry module. Check each place that reads the field: `compose_settings.py`, `ocr_identity.py`, `page_routing.py`, `tests/unit/test_settings_file_editable_keys.py`, `omrs config init` and `omrs config show` (a `None` default must print as unset and not as `null` text that a user could paste back as a value). Verify: the tests pass; `omrs config init` output is checked by hand once.
- [ ] 3.3 Tests first: the `local_tier` payload holds the resolved cut, the model when it resolves, and `backend` only for a non-default backend; the default digest equals the digest pinned in 1.2; a backend swap and a cut change each reindex PDF sources once; other sources keep their digest (`core/ingestion/ocr_identity.py`, `tests/test_ocr_identity_reingestion.py`). Verify: `uv run pytest tests -k "identity" -q` passes.

## 4. Experiment 46 (planned in this change; runs after the operator approves the downloads)

- [ ] 4.1 Operator, before any download: approve each arm's download (B Indra about 76 MB; D `ocrmac` and PyObjC, a few MB) one at a time. Read the full Indra licence (modified OpenRAIL-M, limits on commercial and competing use) before arm B. Record the decision in the PR. Verify: the run record of each arm names the approval date.
- [ ] 4.2 Tests first for the pure parts of `run_arm.py` and `summarise.py` (`test_*.py` beside them): the sample rule with seed 46 gives 30, 35 and 35 pages and the same pages on a second call; the character-weighted confidence; the leave-one-document-out cut on a toy table, including the fold with no qualifying cut; each gate on a toy table, including the boundary values 0.70, 0.60, 0.05, 0.30, -0.02, -0.05 and 5.0; a page with no output scores 0. Write the scripts. Verify: the tests pass; a mutation that changes a gate threshold fails one test.
- [ ] 4.3 Run preconditions P1 to P6, fill the tree hashes and the arm versions in `plan.json` `frozen` and `arms` (a fill-in before the first run, not an amendment), run the `sample` step, and record the SHA-256 of `pages.json`. Verify: `uv run --no-sync omrs experiments check` shows no issue for folder 46; the plan SHA-256 is in the first run record.
- [ ] 4.4 Warn the operator, then run arms B and D one at a time (D skips the 60 Bengali pages), one page at a time, with `--resume`. Each arm runs in its own scratch environment outside the repository. Verify: each `output/arm_<id>.jsonl` holds one row per page; an arm that stops under the stop rule is recorded as failing G4.
- [ ] 4.5 Run `summarise.py`, write `analysis.py` and `report.md` (Answer box first, every number names its `output/` file), set the status and the one-line `finding` in `experiment.json`, and add the operator spot-check note if it was done. Copy `output/` to the data store before any worktree removal and record the SHA-256. Verify: the report gives the gates per arm and script, the cut each arm would register, the limits in protocol section 8, and the outcome (PASS, FAIL or INCONCLUSIVE); `omrs experiments index --write` and `omrs experiments check` pass.
- [ ] 4.6 Act on the outcome. PASS: propose the follow-up change (add the backend, its cut, a Settings row). INCONCLUSIVE: propose a task for a script chooser. FAIL: note in the PR that the seam stays with one backend. Verify: the proposal or note exists; no backend code lands in this change.

## 5. Docs

- [ ] 5.1 Update `docs/guides/configuration.md` and `docs/guides/ingestion.md`: the new key, the cut now belongs to the backend, the unset default of `OCR_LOCAL_MIN_CONFIDENCE`, and the identity effect. Add the registry module rows to the integration inventory in `docs/guides/architecture.md`. Grep `docs/guides/` for `OCR_LOCAL_MIN_CONFIDENCE` and fix every line the change makes wrong. Verify: the documented env lines resolve as written in `omrs config show`.

## 6. Integration checks

- [ ] 6.1 Run `./scripts/local_ci.sh`. Verify: no `SKIPPED`, every step passes, including the file-size ceiling and the tripwire. Update the tripwire pin by test IDs.
- [ ] 6.2 Run `openspec validate local-ocr-backends --strict` and `openspec validate --all --strict`. Verify: both pass.

## Workflow follow-up

- Branch `feat/local-ocr-backends` from `v3` in the sibling worktree. Open a pull request into `v3`. Do not merge.
- Watch CI to the end, fix failures, and answer every review thread.
- Archive after the operator approves the merge. Group 4 may finish after the merge. If so, archive the change after groups 1 to 3, 5 and 6, and track group 4 in its own task.
