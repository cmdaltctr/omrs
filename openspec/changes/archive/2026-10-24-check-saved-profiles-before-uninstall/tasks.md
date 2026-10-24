# Tasks

## 1. Server

- [x] 1.1 Add the profile walk (D1, D2, D4) to `uninstall_plan.py` and a `profiles` reader on `InstallJob` (D5). Verify: unit tests fail first, then pass, for a `pypdfium2` Read document step, a disabled step, a deleted profile, a profile `embed_provider` with an extra (registered test provider), a global setting named first, and no catalogue.
- [x] 1.2 Add `uninstall_profile` to the catalogue entry and `profile` to the 409 body, in `openapi.yaml` first (D3). Verify: route tests with a real profile saved through the profile service, and contract conformance.

## 2. Page

- [x] 2.1 Load `omrs-design`. Show the profile line with its Studio link, and name the profile in a refused uninstall (D6). Verify: Vitest cases from the `workspace-integrations` scenarios fail first, then pass.
- [x] 2.2 Update `docs/guides/web-workspace.md`, ADR-096 (close the known gap) and the `transports/api` folder guide. Verify: docs and guide tests pass.

## 3. Checks

- [x] 3.1 Re-pin the tripwire, run `./scripts/local_ci.sh`, the web gates and `openspec validate check-saved-profiles-before-uninstall --strict`. Verify: all pass; record the counts here.
  - 2026-10-24 counts: `./scripts/local_ci.sh` passed. Fast suite 8,051 passed, 152 skipped; tripwire 5 passed (`_BASE_EXECUTED` 8044 → 8058, `_WEB_EXTRA_CASES` 1444 → 1446); ruff clean, import-linter 21 kept, `openspec validate --all --strict` 85/85; web 155 files and 1,924 tests passed, build pass.
  - The first run failed `test_a_value_from_the_config_file_has_that_source_and_does_not_lock`: it searched the whole reply for the word "saved", and this worktree's path contains it. The test now checks the field sources only; a mutation that reports "saved" as a source still fails it.
