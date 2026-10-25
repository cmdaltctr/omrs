# Tasks

## 1. Baseline

- [x] 1.1 Confirm the worktree root and branch with `git rev-parse --show-toplevel` and `git branch --show-current`. Verify: both name `llamaindex-rag-mcp-feat-experiments-in-web-workspace` and `feat/experiments-in-web-workspace`.
- [x] 1.2 Confirm that `omrs.core.experiment_records` is importable and that `uv run --no-sync omrs experiments check experiments` reports no errors. Verify: exit code 0.

## 2. Core and storage (design D1 to D4)

- [x] 2.1 Measure `scan` plus `check` on the repository `experiments/` folder, warm, 20 repetitions. Record the median and maximum in `openspec/changes/experiments-in-web-workspace/timing.md`. Verify: the median is under 200 ms, or D4 is revised before going on.
- [x] 2.2 Write tests for the project path check (design D1): absolute, exists, is a directory, has an `experiments` directory, the `experiments` entry does not resolve outside the project, refusal messages. Then add `core/workspace/experiment_library.py` with the protocol and the pure check. Verify: the tests fail first, then pass.
- [x] 2.3 Write tests for migration 7 in the style of the existing schema tests: the version goes from 6 to 7, a backup is made, the three tables exist, and an existing version 6 database keeps its rows. Then add migration 7 to `SCHEMA_MIGRATIONS`. Verify: the tests fail first, then pass.
- [x] 2.4 Write repository tests: add, list, get and remove projects (unique resolved path); create, rename and delete notebooks (unique name); add and remove entries; removing a project removes its entries; deleting a notebook removes its entries. Then add `integrations/workspace_sqlite/experiment_library.py`. Verify: the tests fail first, then pass.
- [x] 2.5 Add an import-contract entry if the new core module needs one, and run `lint-imports`. Verify: all contracts kept.

## 3. HTTP API (design D5 to D7)

- [x] 3.1 Build `runtime.experiment_library` in `lifespan.py` next to `runtime.chats`. Verify: an existing lifespan test, extended, sees the attribute.
- [x] 3.2 Write route tests for projects: list, add (manage session only; bearer refused; bad path refused with 400), remove. Then add `transports/api/routes/experiment_library.py` and register it in `app.py`. Verify: the tests fail first, then pass.
- [x] 3.3 Write route tests for the experiment list and one experiment: records, findings, reserved numbers, top-level files with `viewable`, `output/` names, an unavailable project, an unknown folder (404). Then implement. Verify: the tests fail first, then pass.
- [x] 3.4 Write route tests for file text (design D6): allowed suffixes, refused suffix, `..`, `/`, a leading dot, a link pointing out of the folder, the 1 MiB cut with `truncated: true`, and a JSON response type. Then implement. Verify: the tests fail first, then pass.
- [x] 3.5 Write route tests for notebooks: list (project and user kinds), create, duplicate name refused, rename, delete, add and remove entries, a missing entry shown with `missing: true`. Then implement. Verify: the tests fail first, then pass.
- [x] 3.6 Write route tests for creating an experiment: manage session only, success with `index: "written"`, `no-markers`, `no-readme`, `failed` (README not valid UTF-8, unreadable or not replaceable), refusal when the folder exists, a bad slug. Use a temporary project. Then implement. Verify: the tests fail first, then pass.
- [x] 3.7 Add every new route to `transports/api/openapi.yaml` and list them in `src/omrs/transports/api/README.md`. Verify: `tests/test_openapi_conformance.py` passes.

## 4. Web client and screens (design D8)

- [x] 4.1 Load the `omrs-design` skill. Add `web/src/api/experimentLibrary.ts` with types and calls, and query and mutation hooks next to the existing ones. Add client tests. Verify: `npm test` passes for the new files.
- [x] 4.2 Add the routes `#/experiments/library/<project>/<folder>` and `#/experiments/notebooks/<id>` to `web/src/lib/routes.ts`, with parse and format tests. Verify: the tests pass, and existing run routes still parse.
- [x] 4.3 Rename the section chips to Library, Notebooks, Sandboxes, Code editor and Runs, with Library as the default. Update `ExperimentsView.test.tsx` and the area summary in `views.ts`. Verify: tests pass, and the Sandboxes and Code editor panels render as before.
- [x] 4.4 Build the Library: project picker with "All projects", add-project form, status and category filters, text search, cards with status badge and finding count. Write component tests with a mock server. Verify: tests pass.
- [x] 4.5 Build the experiment page: record header with a `superseded_by` link, tabs Protocol, Plan, Report (falls back to `results.md`), Files and Checks, and an "Add to notebook" menu. Render Markdown with `react-markdown` and `remark-gfm` and no raw HTML. Test that an HTML string in Markdown is shown as text. Verify: tests pass.
- [x] 4.6 Build Notebooks: list, create, rename, delete with confirmation, the notebook page with entry cards, a missing-entry state and remove. Verify: tests pass.
- [x] 4.7 Build the new-experiment form (slug, title, category, size, follow-up) with the server's refusal message shown in plain words. Verify: tests pass.
- [x] 4.8 Run the web gates: `npm run lint`, `npm run typecheck`, `npm test` and `npm run build` in `web/`. Verify: all pass.

## 5. Docs

- [x] 5.1 Add a "Web workspace" section to `docs/guides/experiment-records.md`, and update `docs/guides/web-workspace.md` with the new sections and the renamed ones. Verify: links resolve.
- [x] 5.2 Update `web/src/AGENTS.md` and the `omrs-design` skill screen notes if they describe the Experiments sections. Verify: the text matches the new chips.

## 6. Verification

- [x] 6.1 Update `_BASE_EXECUTED` in `tests/test_clean_base_tripwire.py`. Compare collected test IDs with the base. Verify: the tripwire passes.
- [x] 6.2 Run `./scripts/local_ci.sh`. Verify: every step passes, or each `SKIPPED` step is named.
- [x] 6.3 Run a browser check at 1280 px and 390 px on a scratch `omrs web` server with a scratch config and workspace. Add this repository as a project, open the library, one experiment's Protocol and Report tabs, create a notebook, add an experiment, and create a Quick experiment in a scratch project. Verify: no sideways scroll at 390 px, and record the results in `openspec/changes/experiments-in-web-workspace/browser-check.md`.
- [x] 6.4 Run `openspec validate experiments-in-web-workspace --strict` and `openspec validate --all --strict`. Verify: both pass.
- [x] 6.5 Search the added lines of `git diff` against the base branch for the maintainer login, home-folder paths and email addresses. Verify: no hit, or each hit is explained.
