# Tasks

## 1. Modularity first

- [x] 1.1 Add the modularity test (design D5) for `chroma`, `hybrid`, `pdf-pypdfium2`, `community-leiden`, `azure`, `anthropic` and `torch`. Verify: it passes on the current code, or each failure is fixed in this group with a test; record any extra that needed a fix.

## 2. Server

- [x] 2.1 Add the packages-to-remove rule (D1) and the in-use map (D2) in `install_environment.py`, with a test that every non-base catalogue extra has a map entry. Verify: unit tests fail first, then pass, including a shared package kept and each in-use row.
- [x] 2.2 Add the uninstall action to the install job and `POST /v1/integrations/{extra}/uninstall` (D3, D4), with the catalogue fields and the OpenAPI contract. Verify: route tests for success then `restart-needed`, `in-use` 409, base and `web` 409, unknown 404, bearer 403, a running job 409, a failed check, and contract conformance.

## 3. Page

- [x] 3.1 Load `omrs-design`. Add Uninstall, its dialog (removed and kept lists), progress, "Removed, restart to apply", the in-use line and the lasting command. Verify: Vitest cases from the `workspace-integrations` scenarios fail first, then pass.
- [x] 3.2 Update `docs/guides/web-workspace.md` and write the ADR (load `s-adr`). Verify: docs tests pass.

## 4. Checks

- [x] 4.1 Re-pin the tripwire, then run `./scripts/local_ci.sh` and the web gates, and `openspec validate uninstall-integrations-from-the-app --strict`. Verify: all pass; record the counts here.
  - 2026-10-24 counts: `./scripts/local_ci.sh` passed. Fast suite 7,999 passed, 152 skipped (parallel, 3 min 50 s). Tripwire 5 passed, with `_BASE_EXECUTED` 7912 → 8006 and `_WEB_EXTRA_CASES` 1409 → 1443. ruff and format clean (1,941 files), import-linter 21 kept, `openspec validate --all --strict` 85/85, OpenAPI contract valid, default install torch-free.
  - Web gates: `npm run lint` pass, `npm run typecheck` pass, `npm test` 155 files and 1,920 tests passed, `npm run build` pass. `openspec validate uninstall-integrations-from-the-app --strict` valid.
- [ ] 4.2 Browser check on a scratch `uv tool` install (D6) in Orca: uninstall each non-base extra, restart after each, and check that the app starts and Search answers. Verify: record the results here; the live app on port 8765 is not touched.
