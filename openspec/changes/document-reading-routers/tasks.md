# Tasks

Code tasks are tests first: write the test, run it, confirm it fails, then change the code. No test contacts a real decision model: use `httpx.MockTransport` or a fake server. Update the pins in `tests/test_clean_base_tripwire.py` by test IDs after each group. Resolve the design Open Questions with the operator before group 2 starts.

## 1. Settings maps

- [ ] 1.1 Tests first: `decision_models` and `document_routers` load from `omrs.jsonc` as named maps; a broken entry is ignored and listed while others load; no env var sets a map; `document_router` follows the source order and env locks it; a literal key in an entry is ignored (`config/`, `settings_file.py`, `settings_file_write.py`; tests set `OMRS_CONFIG_DIR` to a tmp folder). Verify: `uv run pytest tests/unit -k "settings_file or provider_config" -q` passes.
- [ ] 1.2 Tests first: page writes of the maps keep comments, use the revision check, refuse a literal key and refuse deleting an entry that a router or a saved profile names. Verify: the tests pass; only `omrs web` code paths write the maps (a test asserts the CLI path opens the file read-only).

## 2. Decision model providers

- [ ] 2.1 Tests first: `core/providers/decision/registry.py` with `llamacpp` and `typesafe` adapters: request shape (`noul`, options `no` and `yes`), image list for llama.cpp, `assets` plus `TypeSafe-Danger-Zone-Images: true` only for hosted image requests, P(yes) bounds, malformed reply gives a fixed reason with no body in logs. `compose_decision.py` resolves key references. Add the contract entry in import-linter. Verify: `uv run pytest tests -k "decision_model" -q` passes; `lint-imports` passes.
- [ ] 2.2 Tests first: GGUF header quantisation check on small fixture headers (Q8_0, F16 pass; Q4_K_M refused with the rule text); external model-name check; "Quantisation not checked" when unknown. Verify: a mutation that accepts Q4_K_M fails a test.
- [ ] 2.3 Tests first: the projector smoke test against a fake server (right text high, wrong text low passes; equal answers fail with `projector-not-loaded`); set the margin constant from the Experiment 43 smoke results with a version. Verify: the tests pass; the bundled fixture image is under 50 KB and holds no personal data.
- [ ] 2.4 Tests first: a managed decision runtime: role `decision`, id `decision-<name>`, model and projector files with SHA-256, build floor refusal `wrong-build`, `127.0.0.1`, one slot (`integrations/llamacpp_runtime/spec.py`, `compose_runtimes.py`). Verify: `uv run pytest tests -k "llamacpp_runtime or runtimes" -q` passes; `GET /v1/runtimes` lists the role in a route test.
- [ ] 2.5 Update `docs/guides/providers.md` (Decision models, kinds, key references, the 8-bit rule, projector, build floor) and `docs/guides/configuration.md` (map format with a commented example). Verify: the example block parses in a test that loads it from the guide.

## 3. Routers in the reader

- [ ] 3.1 Tests first: `integrations/pdf/page_router.py` judges rescued pages; "no" pages form the rejected set; `pages_needing_ocr` equals the rejected count; no router keeps the TDR-024 zero; pages already sent to OCR by page routing are skipped; scope `all-text` also judges unflagged native pages. Verify: `uv run pytest tests -k "page_router or rescue or pdf_inspector" -q` passes; `ocr_routing.py` stays at or under 500 lines.
- [ ] 3.2 Tests first: under the `document` unit, 1 rejected page of a 1,000-page fixture and 5 of 20 send exactly those pages through the local tier and escalation; the document gate never sees them; a protocol 1.0 worker degrades them to unresolved with a warning. Verify: a mutation that adds rejected pages to the gate count fails a test.
- [ ] 3.3 Tests first: degradation reasons (`unknown-model`, `unreachable`, `quantisation-refused`, `projector-not-loaded`, `wrong-build`, `renderer-missing`, `needs-opt-in`, `request-failed`); a hosted router without opt-in sends no request (MockTransport sees zero calls); counts are stamped and excluded from embedding text; the page renderer follows the resolved Open Question 1. Verify: `uv run pytest tests -k "page_router or embed_exclusion" -q` passes.
- [ ] 3.4 Tests first: identity block only with a router selected; rename leaves digests; threshold change moves PDF digests only; default digest equals the pinned pre-change digest (`ocr_identity.py`, `source_state.py`). Add a note to TDR-024 that a selected router replaces the zero. Verify: the pinned-digest test passes.
- [ ] 3.5 Tests first: a page renderer list (LiteParse `screenshot` first, pypdfium2 when the `pdf-pypdfium2` extra is installed) returns a PNG at 150 DPI, long side at most 1,568 px; a missing renderer gives `renderer-missing`. Verify: on one scanned page and one vector-only page, the two renderers give images within 2 px of each other in size, and the Clef-Flash answers on the two images differ by less than 0.05; the test fails when the first renderer is removed and no second exists.

## 4. Studio and HTTP contract

- [ ] 4.1 Contract first: `openapi.yaml` routes and schemas for decision models (list, save, delete, test) and routers (list, save, rename, delete), the `document_router` read-step option, fixed reasons, and `FAMILIES` entries; confirm the conformance tests fail. Implement routes in `transports/api/routes/` behind the existing session scopes (`manage` for writes; Test needs `manage` because it contacts a host). Verify: `uv run pytest tests/unit -k "openapi or decision or router" -q` passes.
- [ ] 4.2 Tests first: `ReadParams.document_router` (name, `none`, `null`), unknown name gives `option_unavailable`, identity follows the step router. Update `docs/guides/pipelines.md`. Verify: `uv run pytest tests -k "read_params or graph_fingerprint" -q` passes.

## 5. Front end

- [ ] 5.1 Load the `omrs-design` skill. Tests first (Vitest): Decision models card (add, edit, test, remove refused while in use, key state without the key, managed files and runtime state) and Router section (host choice, template with the "not confirmed" note, hosted warning, opt-in checkbox off by default, "Will not run", experimental label). Keep each component under 200 lines. Verify: `npm run lint`, `npm run typecheck` and `npm test` pass in `web/`.
- [ ] 5.2 Check both views in a browser at 1280 px and 390 px against a fake decision server (warn the user before starting servers; scratch config folder, free port). Save screenshots in the change folder. Update `docs/guides/web-workspace.md`. Verify: no horizontal scroll at 390 px and the question text wraps.

## 6. Confirmation experiment and decision record

- [ ] 6.1 Reserve the next free experiment number. Write the protocol with the `s-experiment` skill: new documents only (SHA-256 check against Experiments 33, 38, 42, 43, 44), labels frozen before scoring, threshold 0.172 frozen from Experiment 43 `plan.json` with its hash, the page-based pass rule of the `rescue-quality-evaluation` delta, local Clef-Flash Q8_0 with its projector as the primary arm, hosted Jev only after recorded approval. Verify: `plan.json` is committed before any score file exists.
- [ ] 6.2 Run the experiment through the shipped router code on a managed or external runtime that passes the D6 checks, and write `report.md` with per-document OCR page costs. Verify: `experiment.json` validates and the report states PASS or FAIL by the frozen rule.
- [ ] 6.3 Finish ADR-110 (`docs/adr/110-decision-models-and-named-document-routers.md`) with the experiment outcome and add its row to `docs/adr/ADR_README.md`. Keep the status Proposed until the operator accepts it. Verify: the ADR links resolve and the README row matches the file name.

## 7. Integration checks

- [ ] 7.1 Run `./scripts/local_ci.sh`. Verify: no `SKIPPED`, every step passes, including the file-size ceiling and the tripwire.
- [ ] 7.2 Run `openspec validate document-reading-routers --strict` and `openspec validate --all --strict`. Verify: both pass.

## Workflow follow-up

- Branch `feat/document-reading-routers` from `v3` in a sibling worktree. Open a pull request into `v3`. Do not merge.
- Watch CI to the end, fix failures, and answer every review thread.
- The routing-unit default and the 10% rule stay as they are. Their decision needs the page-mode re-test, its own change and its own ADR.
- Archive after the operator approves the merge.
