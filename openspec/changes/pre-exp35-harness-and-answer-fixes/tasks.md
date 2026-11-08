# Tasks

Rules for every group: tests first and shown to fail on the current code; one mutation check per behaviour; keep files under 500 lines; re-pin the tripwire only by test-ID diff; work in `omrs-v3-feat-pre-exp35-harness-and-answer-fixes`; no live app, no pod.

## 1. Answer sampling settings (spec `answer-sampling`, design D1 to D3)

- [ ] 1.1 Check each provider's request field for temperature and seed with Context7 (llama.cpp server, OpenRouter, OpenAI, Ollama, Anthropic). Record the table in design D2 if it differs. Verify: design D2 matches the docs.
- [ ] 1.2 Add `temperature`, `seed`, `verify_temperature`, `verify_seed` to `AnswerSettings` and `AnswerBlock` with range checks. Tests: values read from `omrs.jsonc` and env; out-of-range refused. Verify: new tests fail before, pass after.
- [ ] 1.3 Add `sampling_kwargs` to each provider module, `temperature=` and `seed=` keywords to each provider's `build()`, and `ignored_sampling` to the LLM registry; pass the values from `compose_answer.py` for the Chat and judge roles. Tests per provider: request body carries the set values, empty values leave the request as before (temperature 0.1 on OpenAI-like), Chat values never reach judge requests, Anthropic reports the seed ignored, and on OpenRouter and OpenAI-compatible a set reasoning level and a set seed both reach the body. Verify: tests plus one mutation per mapping.
- [ ] 1.4 Record the sampling values each request carried in the answer result (read from the built LLM). Tests: library default recorded as 0.1; set values recorded; judge record only when the judge ran. Verify: the new tests fail before the change, pass after.
- [ ] 1.5 Contract first: `openapi.yaml` gains the four values on the Chat and Judge settings reads and saves, the "ignores" list, and the answer-result `sampling` record. Then `chat_settings.py` and `judge_settings.py`. Tests: OpenAPI conformance, out-of-range save refused with 400, save writes `omrs.jsonc` with the revision check, locked value refused with 409. Verify: the new tests fail before the change, pass after.
- [ ] 1.6 Web: Chat panel and Judge panel show and save the values, with the "ignored by this provider" note and the lock state. Vitest tests; browser check at 1280 px and 390 px on a scratch config and a free port. Verify: Vitest fails before, passes after; screenshots saved.
- [ ] 1.7 Docs: `docs/guides/configuration.md` and `docs/guides/mcp-tools.md` name the four settings, their env names, the 0.1 library default and the answer-result record. Verify: grep both guides for the four env names.

## 2. Per-file ingest overhead (design D5)

- [ ] 2.1 Tell the operator before the run. Profile one 200-file FreshStack ingest on the Mac (scratch `HOME`, scratch config, own router port checked free with `lsof` first, the existing 4B GGUF named by path and SHA-256 with `HF_HUB_OFFLINE=1` so nothing downloads, metadata `disabled`), one `ingest_path_async` call per file as in Experiment 48. Stop the router when done. Save the `cProfile` output, stage spans and a one-page summary under `~/Development/DATA/omrs/experiments/` with SHA-256. Verify: the summary names where the per-file seconds go, with numbers.
- [ ] 2.2 Run after 3.1 (a harness-only fix edits `experiments/_lib/`). Score each cause found (likelihood x impact). For a score of 4 or more in OMRS code: add the requirement with `openspec-update-change`, validate, then fix tests first. For a harness-only cause: change the shared harness (group 3). For 3 or below: list a proposed issue in the PR. Verify: a rerun of 2.1 shows the saving, or the PR states that nothing was fixed and why.

## 3. Shared benchmark harness (spec `benchmark-harness`, design D4)

- [ ] 3.1 Create `experiments/_lib/ranking.py`, `timing.py` and `router_env.py` with tests under `tests/` (`tests/test_experiment_lib_*.py`), starting from the Experiment 48 functions and their existing tests. Verify: the copied tests pass and are collected by the default `pytest` run; no file in `experiments/48-pipeline-sweep-llamacpp-2026-11-01/` changes (`git diff --stat` on that folder is empty).
- [ ] 3.2 Neighbour lists exclude the query chunk on slices of k or fewer chunks. Test: 5-chunk slice, k 10; large-slice order unchanged. Verify: test fails on the copied code.
- [ ] 3.3 Atomic writes for every timing and fast-mode output file (temporary file plus rename). Test: a write that raises part-way leaves the old file or none. Verify: the test fails on the copied code.
- [ ] 3.4 Ranking comparison over the union of both runs' questions. Tests: a question only in run 1 reported (the Experiment 48 gap), and a question only in run 2 reported. Verify: the run-1 test fails on the copied code.
- [ ] 3.5 GGUF folder resolved to an absolute path on read; a missing folder refused with the variable and path named. Tests for relative path (working folder changed after the read) and missing folder (no router launch). Verify: both fail on the copied code.
- [ ] 3.6 Carry the review lessons into the new tests (blank result ids, empty comparisons, `--limit` smoke runs, tuple JSON keys, env overrides). Verify: one test per lesson, each mutation-checked.

## 4. Login item keeps the OCR variables (spec `web-login-item`, design D7)

- [ ] 4.1 Tests for the four scenarios (re-install keeps, shell wins, others not carried, nothing to carry) and the printed line. Verify: they fail on current `render_plist`.
- [ ] 4.2 Implement the allow-list in `_web_login_item.py` (`build_plan` and `render_plist`). Verify: tests pass; mutation check on the allow-list.
- [ ] 4.3 Update `docs/guides/cli-reference.md` (`omrs web install`) and verify the carried variables are named there; comment on issue #175 that PR #176 fixed the two library paths and this change fixes the Indra folder; close it after merge.

## 5. Records and follow-ups (design D6, D9)

- [ ] 5.1 State in the PR body that Experiment 48 tasks 4.3, 5.4 and 5.5 stay open and that 35a's first timing step produces the Part C speeds and token counts. Verify: PR body.
- [ ] 5.2 Carry the D9 RunPod recommendation and the D6 timing step to master task 6.1 (note in `rag-benchmark-readiness-flow/tasks.md` under 6.1). Verify: note present; `openspec validate --all --strict` passes.

## 6. Flaky router tests (design D8)

- [ ] 6.1 Router state race: regression test that injects the delay between Start's flag and its status read and fails on current code; then one re-entrant lock around `start`, `load`, `stop` and `status` in `RouterControl`. Verify: the new test and `test_every_download_failing_ends_failed_with_one_attempt_per_model` pass 200 times, including under `-n 8`; mutation check (remove the lock).
- [ ] 6.2 Cut-off reply: test that a reply closed after the headers gives "unreachable" `(0, {})`, failing on current code; catch `http.client.HTTPException` in `process.http_get_json`. Fake router binds port 0 and reports its port. Verify: test passes; 200 runs of `test_changed_file_refused_and_others_serve` pass under `-n 8`.

## 7. Close

- [ ] 7.1 Re-pin the tripwire by test-ID diff; `./scripts/local_ci.sh` passes; `openspec validate --all --strict` passes.
- [ ] 7.2 Independent review subagent on the full diff; fix findings scored 4 or more.
- [ ] 7.3 Scan `git diff origin/v3...HEAD` for `/Users/` paths and email addresses; PR into `v3`; CI green; CodeRabbit read, threads replied and resolved. Do not merge without the operator's word.
