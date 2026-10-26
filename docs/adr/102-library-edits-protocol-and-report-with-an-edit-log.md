# ADR-102: The Library Edits Protocols and Reports, and Logs Each Save in edits.jsonl

- **Date:** 2026-10-26
- **Status:** Proposed
- **Deciders:** Maintainer
- **Related:** [ADR-097](097-experiment-records-versioned-format.md) (experiment record format; this ADR amends its rule that old protocols and reports keep their content), [ADR-099](099-library-experiments-open-in-marimo-with-the-project-environment.md) (decision 1 holds the current rule text), [ADR-100](100-experiment-library-reads-project-folders-and-keeps-choices-in-the-workspace-database.md) (decision 5: the Library reads files only), [ADR-087](087-settings-live-in-omrg-jsonc.md) (decision 5: revision check and atomic write)
- **Change:** `openspec/changes/edit-experiment-files-in-library/` (design D1 to D10)

## Context

The experiment page in Experiments, Library shows `protocol.md` and the report as read-only Markdown. The user wants to edit both files from their tabs, in any experiment. All 50 current experiments carry a `migration` note, so every one is a converted record.

Three rules stand in the way:

- `experiments/AGENTS.md` (and its package template and skill copies) says: "In a finished or converted experiment, change only `experiment.json`. Never edit its other files." ADR-099 decision 1 set this text.
- ADR-097 says, as a neutral consequence: "Old protocols, plans and reports keep their content."
- ADR-100 decision 5 says the app reads text files only, inside the experiment folder.

The user decided:

1. Allow edits to `protocol.md` and the report in any experiment, with a visible warning when the experiment is finished or converted. Git keeps the history.
2. Record a "last edited" audit trail and show it in the page.
3. Keep `plan.json` frozen. The Plan tab stays read-only.

Two facts shape where the audit trail goes. The record model forbids unknown keys (ADR-097 decision 4), so a new key in `experiment.json` makes every current release refuse an edited record. Run records already set a precedent: an append-only JSON Lines file with its own format, outside `experiment.json` (ADR-097 decision 6).

## Decision

1. **A finished or converted experiment may change three files.** They are `experiment.json`, `protocol.md` and the report file (`report.md`, or `results.md` in an older folder without `report.md`). `experiment.json` stays editable by hand, as ADR-097 allows; the app never writes it (decision 4). All other files stay frozen. `plan.json` stays frozen after the first run, as ADR-097 decision 2 says.
2. **The app edits only those report and protocol names, and only files that exist.** The server checks the name against a fixed list before any file access. The project must be an added Library project and the folder a listed experiment folder. The file must be a regular file directly in the folder, at most 1 MiB, in UTF-8, with no NUL character. The save needs the browser session with the `manage` scope and passes the Origin check.
3. **Saves are safe.** Each read returns a revision (SHA-256 of the file). A save carries the revision it was based on. A file that changed on disk gets 409 `changed_on_disk` and nothing is written. The write goes to a temporary file in the same folder, then `fsync` and `os.replace`. Line endings and a leading byte order mark are kept. This follows ADR-087 decision 5.
4. **Each save from the app appends one line to `edits.jsonl`.** The file sits in the experiment folder and git tracks it. Each line has the format `omrs-edit-record/1`: file name, UTC time, SHA-256 and size before and after, the record status at the time, whether the record is converted, and the tool. No user name and no path. Lines are only appended. The file is replaced first and the line appended second; when the append fails, the app restores the old text and reports that nothing was saved. If the restore also fails, the app reports that the file was saved but the edit was not recorded. `experiment.json` does not change.
5. **The checker validates the edit log.** `omrs experiments check` reports `edit-log-invalid` (warning) for a line that does not load.
6. **The page warns and shows the trail.** Edit mode on a finished (`PASS`, `FAIL`, `INCONCLUSIVE`, `MEASURED`, `SUPERSEDED`) or converted experiment shows a warning that names the status and says that git keeps the old text and that the app records the save. The tab shows "Last edited" from the log.
7. **The app never runs git.** It does not stage or commit. The user commits the file and `edits.jsonl` together.

This ADR amends ADR-097 (neutral consequence on old protocols and reports), ADR-099 decision 1 (the rule text) and ADR-100 decision 5 (the Library reads only).

## Consequences

### Positive

- The user fixes a protocol or report in the app, with no terminal.
- No lost update: a stale editor gets 409 and keeps its text.
- Each app save leaves a git-tracked line with both hashes, which a reader can match against `git show <commit>:<path> | shasum -a 256`.
- Every current `omrs` release keeps reading edited folders, because `experiment.json` and its format do not change.

### Negative

- A finished record can now change after the fact. The warning, the edit log and git history are the only guards.
- Edits made outside the app (terminal, editor, agent) are not logged. Git records them.
- An edited folder gains one more file, `edits.jsonl`.
- The rule text changes in four repository files and in the personal skill copy, which must be kept in step by hand.
- A terminal edit in the microseconds between the last hash check and the rename is not detected. If that edit was not committed, it is lost.

### Neutral

- The Plan tab, `plan.json`, run records and the derived notebook files are unchanged.
- `edits.jsonl` shows in the Files tab like any other `.jsonl` file.
- A rollback of the code leaves `edits.jsonl` files in git; older readers ignore them.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Optional `edits` list in `experiment.json` under `omrs-experiment/1`** | Every current release forbids unknown keys and would show an edited record as invalid, with an error that names the key instead of asking for a newer `omrs`. Each save would also rewrite the whole record and race with status updates. |
| **`edits` list in `experiment.json` with `omrs-experiment/2`** | Every reader, the schema, the templates and the skill copies would need to accept two versions and a converter, for one optional list. |
| **A table in `workspace.db`** | Not in git and not visible to the CLI, agents, reviewers or other machines. ADR-100 keeps only the user's own choices there. |
| **`output/edits.jsonl`** | `output/` is git-ignored. The trail would leave git history. |
| **The app commits each save** | The app never runs git. A commit is the user's decision. |
| **Keep the files read-only (status quo)** | The user must leave the app for every small fix. The user asked for edits. |
| **Edit only experiments that are not finished** | All 50 current experiments are converted records. The feature would apply to none of them. |

## References

- `openspec/changes/edit-experiment-files-in-library/design.md` (evidence and decisions D1 to D10)
- `src/omrs/core/experiment_records/edit_log.py` and `src/omrs/core/workspace/experiment_file_edits.py` (planned)
- `src/omrs/transports/api/routes/experiment_library.py` and `openapi.yaml` (`writeExperimentFile`)
- `web/src/experiments/library/ExperimentTabs.tsx`, `FileView.tsx`, `FileEditor.tsx`
- `experiments/AGENTS.md`, `src/omrs/core/experiment_records/templates/experiments-agents.md`, `.agents/skills/s-experiment/`
- [Experiment records guide](../guides/experiment-records.md)
