# Tasks

Code tasks are tests first: write the test, run it, confirm it fails, then change the code. No test contacts a real decision model: use `httpx.MockTransport` or a fake server. Update the pins in `tests/test_clean_base_tripwire.py` by test IDs after each group. Open Questions 1 to 4 were answered by the operator; Open Question 5 (router scope) is confirmed at the plan gate.

## 1. Settings maps

- [ ] 1.1 Tests first: `decision_models` and `document_routers` load from `omrs.jsonc` as named maps; a broken entry is ignored and listed while others load; no env var sets a map; `document_router` follows the source order and env locks it; a literal key in an entry is ignored (`config/`, `settings_file.py`, `settings_file_write.py`; tests set `OMRS_CONFIG_DIR` to a tmp folder). Verify: `uv run pytest tests/unit -k "settings_file or provider_config" -q` passes.
- [ ] 1.2 Tests first: page writes of the maps keep comments, use the revision check, refuse a literal key and refuse deleting an entry that a router or a saved profile names. Verify: the tests pass; only `omrs web` code paths write the maps (a test asserts the CLI path opens the file read-only).

## 2. Decision model providers

- [ ] 2.1 Tests first: `core/providers/decision/registry.py` with `llamacpp`, `typesafe`, `cloudflare` and `ollama` adapters (the last two against fake servers only): request shape (`noul`, options `no` and `yes`), image list for llama.cpp, `assets` plus `TypeSafe-Danger-Zone-Images: true` only for hosted image requests, P(yes) bounds, malformed reply gives a fixed reason with no body in logs. `compose_decision.py` resolves key references. Add the contract entry in import-linter. Verify: `uv run pytest tests -k "decision_model" -q` passes; `lint-imports` passes.
- [ ] 2.2 Tests first: GGUF header quantisation check on small fixture headers (Q8_0, F16 pass; Q4_K_M refused with the rule text); external model-name check; "Quantisation not checked" when unknown. Verify: a mutation that accepts Q4_K_M fails a test.
- [ ] 2.3 Tests first: the projector smoke test against a fake server (right text high, wrong text low passes; equal answers fail with `projector-not-loaded`); set the margin constant from the Experiment 43 smoke results with a version. Verify: the tests pass; the bundled fixture image is under 50 KB and holds no personal data.
- [ ] 2.4 Tests first: a managed decision runtime: role `decision`, id `decision-<name>`, model and projector files with SHA-256, build floor refusal `wrong-build`, `127.0.0.1`, one slot (`integrations/llamacpp_runtime/spec.py`, `compose_runtimes.py`). Verify: `uv run pytest tests -k "llamacpp_runtime or runtimes" -q` passes; `GET /v1/runtimes` lists the role in a route test.
- [ ] 2.5 Update `docs/guides/providers.md` (Decision models, kinds, key references, the 8-bit rule, projector, build floor) and `docs/guides/configuration.md` (map format with a commented example). Verify: the example block parses in a test that loads it from the guide.

## 3. The router page rule

Group 3 follows `docs/guides/reading-parts.md` (Add a page rule) and the group-1 discipline of `local-ocr-backends`. Before any production edit, run `tests/unit/test_page_routing_golden.py` and `tests/unit/test_reading_parts_digest_pins.py` and record that they pass. With no router selected they must stay byte-identical to the end of the change. A moved pin is a stop: report it and wait.

- [ ] 3.1 Tests first: the hook extension. `RuleOutcome.add` joins the local set (`local = (flagged - dropped - direct) | added`); an `add` page that is flagged, blank, dropped, direct or has no text fails a built-in rule and skips a discovered rule; a rule with an empty `add` changes nothing; `PageRuleDescriptor` and `register()` carry `adds_pages`, pinned like the other four flags; `RuleContext.judge` defaults to `None`. Confirm the path of the judge from compose to the rule in the code (`core/ingestion/backends/local.py`, `integrations/pdf/factory.py`, `OcrRoutedPdfInspector`) and write the test for it. Verify: `uv run pytest tests/unit -k "page_rule or reading_parts" -q` passes; the golden snapshots and digest pins pass unchanged; `ocr_routing.py` stays at or under 500 lines.
- [ ] 3.2 Tests first: `ocr_routing.py` reads `plan.added`. An added page goes to the local tier and, when not kept, to the one page-listed request; with no tier it keeps native text and counts unresolved; with no local runtime it goes to the engine list; `pages_needing_ocr` stays the scan count; `ocr_required` is true when a page is added; the five counts sum to the page count; 1 rejected page of a 1,000-page fixture sends exactly 1 page to OCR; a protocol 1.0 worker degrades added pages to unresolved with a warning. Verify: the tests pass; a mutation that adds rejected pages to `flagged` fails a test; a mutation that drops `added` from `plan.local` fails a test.
- [ ] 3.3 Tests first: the `document_router` rule (`integrations/pdf/page_rules/document_router.py`, order 40, `adds_pages`, one descriptor entry, one `register()` line, a `test_document_router_is_one_part.py` modelled on `test_indra_is_one_part.py`). It returns an empty outcome with no router, without calling the judge; it judges only unflagged text pages that no earlier rule dropped or sent direct; P(yes) below the threshold rejects; text is cut to the character limit; a failed request keeps the page and counts it unjudged; requests go one at a time. Verify: `uv run pytest tests -k "document_router or page_rule" -q` passes; a mutation that judges flagged pages fails a test.
- [ ] 3.4 Tests first: degradation and privacy. Each reason (`unknown-model`, `unreachable`, `quantisation-refused`, `projector-not-loaded`, `wrong-build`, `renderer-missing`, `needs-opt-in`, `request-failed`) gives an empty outcome and `router_status`; a hosted router without opt-in sends no request (MockTransport sees zero calls); the five stamp keys are in `EXCLUDED_EMBED_METADATA_KEYS` and `IDENTITY_UNLISTED_KEYS`, are absent with no router, and never reach the embedding text. Verify: `uv run pytest tests -k "document_router or embed_exclusion" -q` passes; a mutation that sends a request without the opt-in fails a test.
- [ ] 3.5 Tests first: the `parser` identity entry `document_router` is present only for PDFs with a router selected and holds question, threshold, image flag, character limit, kind, model identity and rule version; renaming a router leaves digests; a threshold change moves PDF digests only; the default digests equal the pinned values (`ocr_identity.py`, `reader_identity.py`). Add a note to TDR-024 that page routing superseded the zero for routing and that routers cover unflagged junk pages. Verify: the digest pins pass.
- [ ] 3.6 Tests first: the page renderer list (`integrations/pdf/page_images/`, LiteParse `screenshot` first, pypdfium2 when the `pdf-pypdfium2` extra is installed) returns a PNG at 150 DPI, long side at most 1,568 px; a missing renderer gives `renderer-missing`. Verify: on one scanned page and one vector-only page, the two renderers give images within 2 px of each other in size, and the Clef-Flash answers on the two images differ by less than 0.05; the test fails when the first renderer is removed and no second exists.
- [ ] 3.7 Update `docs/guides/reading-parts.md` (the router is the fourth page rule; `adds_pages`; `RuleOutcome.add`; a worked example). Verify: `uv run pytest tests/unit/test_reading_parts_pins.py tests/unit/test_reading_parts_single_source.py tests/unit/test_page_rule_pipeline.py -q` passes.

## 4. Studio and HTTP contract

- [ ] 4.1 Contract first: `openapi.yaml` routes and schemas for decision models (list, save, delete, test) and routers (list, save, rename, delete), the `document_router` read-step option, fixed reasons, and `FAMILIES` entries; confirm the conformance tests fail. Implement routes in `transports/api/routes/` behind the existing session scopes (`manage` for writes; Test needs `manage` because it contacts a host). Verify: `uv run pytest tests/unit -k "openapi or decision or router" -q` passes.
- [ ] 4.2 Tests first: `ReadParams.document_router` (name, `none`, `null`), unknown name gives `option_unavailable`, identity follows the step router. Update `docs/guides/pipelines.md`. Verify: `uv run pytest tests -k "read_params or graph_fingerprint" -q` passes.

## 5. Front end

- [ ] 5.1 Load the `omrs-design` skill. Tests first (Vitest): Decision models card (add, edit, test, remove refused while in use, key state without the key, managed files and runtime state) and Router section (host choice, template with the "not confirmed" note, hosted warning, opt-in checkbox off by default, "Will not run", experimental label). Keep each component under 200 lines. Verify: `npm run lint`, `npm run typecheck` and `npm test` pass in `web/`.
- [ ] 5.2 Check both views in a browser at 1280 px and 390 px against a fake decision server (warn the user before starting servers; scratch config folder, free port). Save screenshots in the change folder. Update `docs/guides/web-workspace.md`. Verify: no horizontal scroll at 390 px and the question text wraps.

## 6. Confirmation experiment and decision record

The master flow (`doc-reading-master-flow`, task 4.3) makes the experiment a separate gate, G7, after this change merges. The operator decides then whether to run it. Tasks 6.1 and 6.2 stay unticked in this pull request and move to a follow-up change if the operator says yes. Task 6.3 records that the confirmation is pending.

- [ ] 6.1 (After GATE G7, operator approval needed.) Reserve the next free experiment number. Write the protocol with the `s-experiment` skill: new documents only (SHA-256 check against Experiments 33, 38, 42, 43, 44), labels frozen before scoring, threshold 0.172 frozen from Experiment 43 `plan.json` with its hash, the page-based pass rule of the `rescue-quality-evaluation` delta, local Clef-Flash Q8_0 with its projector as the primary arm, hosted Jev only after recorded approval. Verify: `plan.json` is committed before any score file exists.
- [ ] 6.2 (After GATE G7.) Run the experiment through the shipped router code on a managed or external runtime that passes the D6 checks, and write `report.md` with per-document OCR page costs. Verify: `experiment.json` validates and the report states PASS or FAIL by the frozen rule.
- [ ] 6.3 Finish ADR-110 (`docs/adr/110-decision-models-and-named-document-routers.md`) for the page-rule form (Decision 3 and 4 match design D4; the Amends line matches TDR-024's note), state that the confirmation experiment is pending, and check its row in `docs/adr/ADR_README.md`. Keep the status Proposed until the operator accepts it. Verify: the ADR links resolve and the README row matches the file name.

## 7. Integration checks

- [ ] 7.1 Run `./scripts/local_ci.sh`. Verify: no `SKIPPED`, every step passes, including the file-size ceiling and the tripwire.
- [ ] 7.2 Run `openspec validate document-reading-routers --strict` and `openspec validate --all --strict`. Verify: both pass.

## Workflow follow-up

- Later, by the operator (not part of this change's task list): run one live request for each of the `cloudflare` and `ollama` kinds with the smoke test (right text against wrong text), record the result, and remove the "Not yet tested" label. For `ollama`, first build the model from the pinned Clef-Flash Q8_0 and projector files with a two-line Modelfile. For `cloudflare`, read the Workers AI data retention terms before sending any page, and re-read the request shape from the current docs.

- Branch `feat/document-reading-routers` from `v3` in a sibling worktree. Open a pull request into `v3`. Do not merge.
- Watch CI to the end, fix failures, and answer every review thread.
- Routing of flagged pages, the three older page rules and every digest without a router stay as they are.
- Archive after the operator approves the merge, once the operator has said what happens to group 6 at GATE G7.
