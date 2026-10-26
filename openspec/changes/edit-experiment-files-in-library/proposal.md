# Proposal: Edit protocol and report files from the Library

## Why

The experiment page in Experiments, Library shows `protocol.md` and the report as read-only Markdown. To fix a typo, add a missed caveat or clarify a finding, the user must leave the app and edit the file in a terminal or an editor. The user wants to edit these two files from their tabs, in any experiment, also in finished and converted ones. All 50 current experiments carry a `migration` note, so every one of them is converted.

The experiment rule forbids this today. `experiments/AGENTS.md` says: "In a finished or converted experiment, change only `experiment.json`. Never edit its other files." The user decided to change the rule: edits are allowed, the app shows a clear warning on a finished or converted experiment, git keeps the old text, and an audit trail records each save from the app. ADR-102 records this change to the rule set by ADR-097.

## What Changes

- The Protocol tab and the Report tab get an **Edit** button. Edit opens the Markdown source in a text editor with **Save** and **Cancel**. The Plan tab does not change, and `plan.json` stays frozen.
- The app edits only three fixed file names: `protocol.md`, `report.md`, and `results.md` when it is the Report tab file (an older folder with no `report.md`; 33 of the current folders). The app edits a file that exists. It does not create a missing file.
- A finished experiment (`PASS`, `FAIL`, `INCONCLUSIVE`, `MEASURED`, `SUPERSEDED`) or a converted experiment shows a warning in edit mode. The warning says that the file is part of a finished record, that git keeps the old text, and that the app records the save.
- A new route `PUT /v1/experiment-projects/{project_id}/experiments/{folder}/files/{name}` saves the text. It needs the session `manage` scope and passes the existing Origin check. The save carries the revision (SHA-256) that the editor loaded. A file that changed on disk since then gets 409 and nothing is written. The write is atomic (a temporary file in the same folder, then a rename).
- Each save from the app appends one line to a new tracked file, `edits.jsonl`, in the experiment folder. The line has the format `omrs-edit-record/1`: the file name, the UTC time, the SHA-256 and size before and after, the experiment status at the time of the edit, whether the record is converted, and the tool. `experiment.json` does not change.
- The file read (`GET .../files/{name}`) also returns the file revision, whether the app can edit the file, and the last logged edit of that file. The tab shows "Last edited <date>" when the log has an entry for the file.
- `omrs experiments check` validates `edits.jsonl`. A line that does not load gives the warning `edit-log-invalid`.
- The experiment rule changes in `experiments/AGENTS.md`, its package template, the repository skill copy and the skill text. A finished or converted experiment may now change `experiment.json`, `protocol.md` and its report file, and append to `edits.jsonl`. All its other files stay frozen.
- The app never runs git and never commits.
- ADR-102 (Proposed) amends ADR-097 (the old protocols and reports keep their content), ADR-099 decision 1 (the rule text) and ADR-100 decision 5 (the Library reads only).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-experiment-library`: the experiment page edits `protocol.md` and the report file, with a revision check, an atomic write, a warning on finished and converted experiments, an unsaved-changes guard and a "Last edited" line.
- `experiment-records`: a new append-only edit log `edits.jsonl` with its own format; the checker validates it; the experiments folder guide states the new rule for finished and converted experiments.

## Impact

- **Core:** a new module `omrs.core.experiment_records.edit_log` (model, append, read, last edit per file), in the pure package; a new module `omrs.core.workspace.experiment_file_edits` (allow-list, revision check, atomic write, roll back when the log append fails); `experiment_pages.read_file` adds `revision`, `editable` and `last_edited`; `check.py` gains the `edit-log-invalid` code.
- **Server:** one new route in `src/omrs/transports/api/routes/experiment_library.py` with a 409 `reason` map.
- **Contract:** `openapi.yaml` gains the `writeExperimentFile` operation, the `ExperimentFileWrite` and `ExperimentFileSaved` schemas, the `ExperimentEdit` schema and three new fields on `ExperimentFileText`. The conformance families in `tests/unit/test_web_openapi_conformance_support.py` gain the operation.
- **Web:** `web/src/experiments/library/ExperimentTabs.tsx` and `FileView.tsx`, a new `FileEditor.tsx`, a new client call and mutation in `web/src/api/experimentLibrary.ts` and `experimentLibraryMutations.ts`, and refusal lines in `refusal.ts`.
- **Rules and records:** `experiments/AGENTS.md`, `src/omrs/core/experiment_records/templates/experiments-agents.md`, `.agents/skills/s-experiment/references/template-experiments-agents.md`, `.agents/skills/s-experiment/SKILL.md`; ADR-102 and the index row (written with this proposal); notes in ADR-097, ADR-099 and ADR-100 after merge.
- **Docs:** `docs/guides/experiment-records.md` (rule, edit log, checker code, "Edit a protocol or report" procedure); `src/omrs/transports/api/README.md` if it lists the library routes.
- **Dependencies:** none.
- **Outside the repository:** the personal skill copy (`~/.agents/skills/s-experiment/`) needs the same rule text after merge.
- **Tests:** new Python and web tests; the clean-base tripwire pins change and are re-pinned by test-ID diff.
