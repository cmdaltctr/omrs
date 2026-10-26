# Design: Edit protocol and report files from the Library

## Context

See `proposal.md` for the reason. The facts below shape the design. Each one was checked on `v3` at `f8aa838d` on 2026-10-26.

- **The rule.** `experiments/AGENTS.md:87` says: "In a finished or converted experiment, change only `experiment.json`. Never edit its other files. A tool may add the git-ignored derived files `analysis.ipynb`, `analysis.marimo.py` and `__marimo__/`. Never commit them." The same text is in `src/omrs/core/experiment_records/templates/experiments-agents.md:87`, `.agents/skills/s-experiment/references/template-experiments-agents.md:87` and `.agents/skills/s-experiment/SKILL.md:17`. The requirement "The experiments folder guide stands alone" in `openspec/specs/experiment-records/spec.md` pins it. The personal skill copy outside the repository holds it too (`SKILL.md` and `references/template-experiments-agents.md`).
- **Which ADRs hold the rule.** ADR-097 does not quote the rule. Its Neutral consequence says "Old protocols, plans and reports keep their content." ADR-099 decision 1 rewrote the rule text to name the derived files. ADR-100 decision 5 says "The app reads text files only, inside the experiment folder." ADR-100 decision 7 already lets the app write files (it creates an experiment folder).
- **The record format.** `experiment.json` has `format: "omrs-experiment/1"`. The pydantic model uses `extra="forbid"` (`src/omrs/core/experiment_records/record.py`), and the spec says unknown keys are an error. ADR-097 decision 4: "A later format adds `/2` with a converter."
- **The precedent for an event log.** Run records are an append-only JSON Lines file with their own format, `omrs-run-record/1`, outside `experiment.json` (ADR-097 decision 6, `run_record.py`). They live in the git-ignored `output/`.
- **The current folders.** 50 folders have `experiment.json`, and all 50 carry a `migration` note. 33 folders keep the report in `results.md` and have no `report.md`. 11 have `report.md`. None of the protocol, report or results files has a CR line ending.
- **The Report tab.** `ExperimentTabs.tsx` picks the first viewable name of `report.md`, then `results.md`. The Protocol tab picks `protocol.md`. The Plan tab picks `plan.json`, then `plan.md`.
- **The read path.** `experiment_pages.read_file` checks the name, the suffix and the resolved path, then reads at most 1 MiB + 1 byte through `read_regular_file`, which opens the file relative to a folder handle with `O_NOFOLLOW`. The response is `{name, text, truncated, size}`; text is decoded with replacement characters. `ExperimentFileText` in `openapi.yaml` sets `additionalProperties: false`.
- **The safe-write precedent.** ADR-087 decision 5 (`src/omrs/config/settings_file_write.py`): each read returns a revision (SHA-256 of the file), a save with an old revision gets 409 and writes nothing, the write goes to a temporary file, then `fsync` and `os.replace`.
- **The Origin check.** `middleware.py` rejects a foreign `Origin` and a cross-site `Sec-Fetch-Site` on every `/v1` path. A new route gets it with no extra code.
- **The web primitives.** `web/src/components/ui/` has no text area primitive. The studio keeps unsaved canvas drafts per browser (`web/src/studio/storage.ts`), but no page has a leave guard for a text editor.
- **File sizes.** `experiment_pages.py` has 389 lines, `routes/experiment_library.py` 244, `check.py` 303, `ExperimentTabs.tsx` 139. The ceiling is 500.

## Goals / Non-Goals

**Goals:**

- Edit `protocol.md` and the Report tab file of any listed experiment from the app, with no lost update and no partial file.
- Leave a durable, git-tracked trail of each save from the app, which a reader can match against git history.
- Keep every reader that exists today working on edited folders, including older `omrs` releases.

**Non-Goals:**

- Edit `plan.json`, `plan.md`, scripts, `experiment.json` or any other file. Change the status or the finding from the app.
- Create a missing `protocol.md` or report.
- A rich Markdown editor, a live preview while typing, or a diff view.
- Log edits made outside the app (terminal, editor, agent). Git records those.
- Run git, stage or commit.

## Decisions

### D1. The app edits three fixed names, and only files that exist

The server accepts a save only for `protocol.md`, `report.md` and `results.md`. `results.md` is editable only when the folder has no `report.md`, so the Edit button appears exactly where the Report tab shows the file. The name is checked against this list before any file access. The request path carries no other path part. The project must be an added Library project and the folder a listed experiment folder, through the same checks that `read_file` uses (`check_name`, `_folder`, `_served`).

A file is editable when all of these hold: the name is allowed for this folder; the file exists as a regular file directly in the folder (not a link); it is at most 1 MiB; it decodes as strict UTF-8; it holds no NUL character, because a save refuses NUL (D5). One repository file holds a NUL on purpose (`21-lancedb-literal-faithfulness-2026-09-02/results.md`); the browser check found it.

Alternatives:

| Option | Rejected because |
| --- | --- |
| Edit only `protocol.md` and `report.md` | 33 of 50 folders show `results.md` in the Report tab. The user would see an Edit button on one report and not on the next. |
| Any `.md` file in the folder | The user asked for the Protocol and Report tabs. A wider list widens the write surface for no stated need. |
| Create a missing protocol or report | The user did not ask for it. A new file in a converted folder changes the size rules that the checker applies. Left as an open question. |

### D2. The audit trail is a tracked sidecar file, `edits.jsonl`, in the experiment folder

Each save from the app appends one JSON line to `<experiment folder>/edits.jsonl`. Git tracks the file. `experiment.json` does not change. The app never rewrites or removes a line.

Why a sidecar file and not a key in `experiment.json`:

1. **Older readers keep working.** A new key under `omrs-experiment/1` breaks every release that exists today. Their model forbids unknown keys, so an edited folder would show as `record-invalid` in the live app before its reinstall, in the parked `v4` worktree, in older worktrees and in the personal skill workflow. The error would name the key, not say "a newer omrs is needed". A sidecar file is invisible to them: the scanner reads only `experiment.json` and the top level of `output/`.
2. **A format bump costs more than it gives.** Moving to `omrs-experiment/2` would make old readers give the right message, but every reader, the JSON Schema, the templates, the skill copies and the index would need to accept two versions, plus a converter, for one optional list.
3. **Append is safer than rewrite.** A sidecar line is appended. A key in `experiment.json` means a full rewrite of the record through `dump_record`. That rewrite can reformat a hand-written record, and it races with an agent who updates `status` or `finding` at the same time. A second revision check would be needed on a second file.
4. **It follows the run-record precedent.** ADR-097 already keeps an append-only event log with its own format outside the record (decision 6). An edit log is the same kind of data.
5. **No cap is needed.** A line is about 300 bytes. One line per save keeps git diffs to one line. A list inside `experiment.json` would grow the record that the index and every card read.

The cost: an edited folder gains one more file, and the Files tab lists it (it is viewable as `.jsonl`). This is visible on purpose.

Alternatives:

| Option | Rejected because |
| --- | --- |
| Optional `edits` list in `experiment.json`, same format version | Point 1: every current release refuses the record. Point 3: full rewrite and a second revision check. |
| `edits` list in `experiment.json` with `omrs-experiment/2` | Point 2: two versions in every reader and a converter for one optional list. |
| A table in `workspace.db` | Not in git and not visible to the CLI, agents, other machines or reviewers. A workspace reset loses it. ADR-100 keeps only the user's own choices there, and an edit trail is a fact about the experiment. |
| `output/edits.jsonl` (next to run records) | `output/` is git-ignored and is copied out before a worktree is removed. The trail would leave git, which is the history the user relies on. |
| The app commits each save to git | The user and the brief rule this out. The app never runs git. |
| A line inside the Markdown file ("Last edited ...") | It changes the content that the hashes describe, mixes metadata into the record text and breaks the "after" hash. |

### D3. The edit record format is `omrs-edit-record/1`

One JSON object per line, in this key order:

| Field | Type | Meaning |
| --- | --- | --- |
| `format` | `"omrs-edit-record/1"` | The format of this line |
| `file` | string | The file name, a plain name with no path part |
| `edited_at` | string | UTC time of the save, ISO 8601 with seconds and `Z` |
| `before_sha256` | string | SHA-256 (hex) of the file bytes before the save |
| `after_sha256` | string | SHA-256 (hex) of the file bytes after the save |
| `before_size` | integer | Size in bytes before |
| `after_size` | integer | Size in bytes after |
| `status` | string | The record status at the time of the save (one of the seven values) |
| `converted` | boolean | True when the record has a `migration` note |
| `tool` | string | One line, for example `omrs web 3.4.0` |

The model lives in `omrs.core.experiment_records.edit_log` with `extra="forbid"` and `frozen=True`, like `RunRecord`. A line with another `format` value fails with the version named. `file` takes the plain-name pattern, not the three-name list, so a later wider allow-list needs no format change; the writer enforces the list (D1). The record holds no user name, login or path, because the file goes into git (personal identifiers stay out of shared files). The package ships no JSON Schema for this format, the same as for run records.

To match a line against git: `git show <commit>:<path> | shasum -a 256` prints the hash of that version. Git's own object id is a different hash (SHA-1 over a header and the content), so the guide gives this command.

A save with no change (the new bytes equal the old bytes) writes nothing and appends nothing. The answer says `changed: false`.

### D4. The save flow: lock, check, write the file, then append the log

The route `PUT .../files/{name}` takes `{"text": "...", "base_revision": "<sha256>"}`. The steps, under one process lock per experiment folder:

1. Check the name (D1), the project and the folder. Refuse with 400 when the file is not editable, and say why.
2. If `edits.jsonl` exists, check that it is a regular file and not a link. Else refuse with 409 `edit_log_unusable`. This runs before any write, so a bad log never leaves an unlogged edit.
3. Read the current bytes through `read_regular_file`. Refuse with 409 `changed_on_disk` when their SHA-256 differs from `base_revision`. Nothing is written.
4. Build the new bytes (D5). If they equal the current bytes, return `changed: false`.
5. Write the new bytes atomically: create `.<name>.omrs-edit-<random>.tmp` in the same folder with `O_CREAT | O_EXCL | O_NOFOLLOW` relative to the folder handle, with the mode of the old file. Write, `fsync`, then hash the target again. If the hash changed since step 3, remove the temporary file and refuse with 409 `changed_on_disk`. Else `os.replace` the temporary file onto the name and `fsync` the folder. A leading dot keeps the temporary file out of the file list.
6. Append one line to `edits.jsonl` with `O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW` relative to the folder handle, mode 0644. If the file does not end with a newline, write one first. `fsync`.
7. Return `{name, revision, size, changed: true, last_edited}`.

If step 6 fails, the server restores the old bytes with the same atomic write, but only when the file still has the new hash. It then returns 500 with "The file was not saved, because the app could not record the edit in edits.jsonl." If the restore fails too, it returns 500 with "The file was saved, but the edit was not recorded in edits.jsonl. Run git diff on the file to see the change." Both messages name no path.

The lock is a `threading.Lock` per (project id, folder), kept in the route module like the editor route's `_LAUNCH_LOCK` (one server process owns the workspace). It stops two browser tabs from interleaving. It cannot stop a terminal edit between step 5's check and the rename; that window is a few microseconds and is accepted (see Risks).

Alternatives:

| Option | Rejected because |
| --- | --- |
| Append the log line first, then write the file | A failed file write leaves a log line for an edit that did not happen. A reader would need to compare hashes to see it. |
| Write both and report a partial state | The user asked for an audit trail. An unlogged edit from the app must not be the normal failure result. |
| `If-Match` header with an `ETag` | The rest of the API carries the revision in the body (ADR-087 settings writes). One pattern is easier to test and to explain. |

### D5. Limits on the text

- The body `text` is at most 1 MiB in UTF-8 (the read limit). A larger body gets 400.
- The text must not contain a NUL character.
- **Line endings.** A browser text area gives LF. If the old file uses CRLF for every line break, the server converts the new text to CRLF. Else it keeps LF. (No current file uses CR.)
- **Byte order mark.** If the old file starts with a UTF-8 byte order mark, the server keeps it; the editor never sees it.
- The server does not add or remove a final newline. It saves what the user typed.

### D6. The contract

- `ExperimentFileText` (the read) gains three required fields: `revision` (string, SHA-256 hex, or null when the text is cut), `editable` (boolean) and `last_edited` (an `ExperimentEdit` object or null). `ExperimentEdit` is `{edited_at, status, converted}`; the page needs no hashes.
- New operation `writeExperimentFile`: `PUT /v1/experiment-projects/{project_id}/experiments/{folder}/files/{name}`, security `sessionCookie: [manage]`, body `ExperimentFileWrite` (`text`, `base_revision`, `additionalProperties: false`), answer 200 `ExperimentFileSaved` (`status`, `name`, `revision`, `size`, `changed`, `last_edited`). Errors: 400 (not editable, too large, NUL), 401, 403, 404, 409 with `reason` (`changed_on_disk`, `edit_log_unusable`), 500, 503.
- The operation joins the `experiment_library` family in `tests/unit/test_web_openapi_conformance_support.py`.
- Each 409 reason has a plain line in an `EDIT_REASONS` map in the route module and in `web/src/experiments/library/refusal.ts`.

### D7. The checker validates the edit log

The checker reads `edits.jsonl` in each experiment folder when it exists. It reports `edit-log-invalid` (warning) for each line that does not load, with the line number and the reason, and for a log that is a link or not a regular file. It writes no file, as now. The checker does not compare the logged hashes with the current file: a later terminal edit is normal and git records it.

`experiment_detail` and the scanner do not change. The Files tab lists `edits.jsonl` like any other file.

### D8. The page: Edit, Save, Cancel, a warning and a leave guard

- The Protocol and Report tabs show an **Edit** button in the panel header when `editable` is true. The Plan tab never shows it.
- Edit mode replaces the rendered Markdown with a new `Textarea` primitive (`web/src/components/ui/textarea.tsx`, same tokens as `Input`, monospace text, at least 20 rows, full width). **Save** (the one primary action) and **Cancel** sit below it.
- **Warning.** In edit mode on a finished or converted experiment, a warning notice sits above the editor:
  - Finished: "This experiment is finished (PASS). Its protocol and report are part of the record. Saving changes the file on disk. Git keeps the old text, and the app records the save in edits.jsonl."
  - Converted and not finished: "This is a converted record. ..." with the same last two sentences.
  - The status word comes from the record.
- **Leave guard.** While the text differs from the loaded text, Cancel, a tab switch and an in-app link ask "Discard your changes to <name>?" in a `Dialog` with **Keep editing** and **Discard**. A browser reload or close triggers the browser's own `beforeunload` prompt.
- **After a save.** The page leaves edit mode, refetches the file and the experiment detail, and shows "Saved." next to the header for a few seconds (`role="status"`). The header line shows "Last edited 26 Oct 2026, 14:05" from `last_edited`, in local time.
- **On 409 `changed_on_disk`.** The editor stays open with the user's text. A notice says: "This file changed on disk after you opened it. Copy your text, select Reload, then add your changes again." **Reload** loads the new file and revision.
- Other failures use `describeError` / `refusalLine` (one friendly line, raw text to the console).
- Text area width and the buttons fit at 390 px with no sideways scroll.

### D9. The new rule text

The line in `experiments/AGENTS.md` (and its three byte copies or near copies) becomes two lines:

> - In a finished or converted experiment, change only `experiment.json`, `protocol.md` and the report file (`report.md`, or `results.md` in an older folder without `report.md`). Never edit its other files. Say what changed and why in the commit message.
> - The web app appends one line to `edits.jsonl` in the experiment folder for each save of `protocol.md` or the report. Never change or remove a line in `edits.jsonl`. A tool may add the git-ignored derived files `analysis.ipynb`, `analysis.marimo.py` and `__marimo__/`. Never commit them.

`plan.json` stays frozen, as the "While it runs" section says now. The "Converted folders ... can have no run records" line does not change.

### D10. Where the code lives

- `omrs.core.experiment_records.edit_log` (new): the model, `append_edit`, `read_edits` and `last_edit(folder, name)`. It stays in the pure package (import-linter contract `experiment-records-stay-pure`: no subprocess, web framework or store).
- `omrs.core.workspace.experiment_file_edits` (new): the allow-list, editability, the save flow of D4 and the text rules of D5. It takes the tool string as a parameter, because `core/` must not import `omrs.__version__` (contract `core-never-imports-top-level-modules`). The route builds the string.
- `experiment_pages.read_file` adds the three fields by calling the new module. `experiment_pages.py` stays under 500 lines.
- The route goes into `routes/experiment_library.py` (244 lines now).

## Risks / Trade-offs

- [A finished record now changes after the fact] → The warning names the status. The edit log records the time, the status and both hashes. Git keeps the old text. ADR-102 records the decision.
- [A terminal edit lands between the last hash check and the rename] → The window is microseconds under a lock. The next save from any open editor then gets 409, and git shows both changes.
- [The edit log can be edited by hand] → It is a trail, not a proof. Git history of `edits.jsonl` shows any change to an earlier line. The checker reports lines that do not load.
- [A save that is not committed is lost from history on a reset] → The app never commits. The guide says to commit `protocol.md`, the report and `edits.jsonl` together.
- [Hand edits are not logged] → Stated in the rule and the guide. Git records them. A CLI command to log a hand edit is an open question.
- [A new file appears in every edited folder] → It is small and visible on purpose. Older readers ignore it.
- [The live app runs the old code until its reinstall] → The old code cannot save, so no unlogged app edit can happen. Reinstall with the locked commands after merge.

## Migration Plan

1. Merge to `v3`. No data migration: no `edits.jsonl` exists until the first save.
2. Reinstall the live app with the locked commands, after a backup of `workspace.db`.
3. Rollback: revert the merge commit. Existing `edits.jsonl` files stay in git and old readers ignore them.

## Open Questions

- Should the app create a missing `protocol.md` or report from the package template? Today it edits only files that exist.
- Should a CLI command (for example `omrs experiments log-edit <folder> <file>`) let an agent or a terminal user append an edit record by hand? Today only the app logs.
