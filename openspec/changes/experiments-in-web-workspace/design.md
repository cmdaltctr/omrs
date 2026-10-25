# Design

## Context

See proposal.md for the problem. Facts that shape the approach:

- `experiment-format-v1` (merged before this change) gives `omrs.core.experiment_records`: `scan`, `check`, `index`, `reserved`, `scaffold` and `templates`. They read and write only under a directory that the caller passes, and they import no web code.
- Stored chats follow a pattern this change copies: a repository protocol in `core/workspace/chats.py`, a SQLite class in `integrations/workspace_sqlite/chats.py`, a route module `transports/api/routes/chats.py` that uses `ReadSession`, an `admitted()` block and `run_in_threadpool`, and a `runtime.chats` field built in `lifespan.py`.
- Workspace database migrations live in `integrations/workspace_sqlite/schema.py` as `SCHEMA_MIGRATIONS` (versions 1 to 6). An upgrade makes an owner-only backup next to the file first.
- Only `omrs web` writes the workspace database (gotcha 17). The MCP server, CLI and watcher never read these new tables.
- The web package already has `react-markdown` and `remark-gfm` (Chat uses them). `react-markdown` does not render raw HTML unless a plugin is added.
- The live login item runs `omrs web --login-item` with no `--root` and no `--experiment-root`.

## Goals / Non-Goals

**Goals:**

- Add a project from the GUI, with no restart and no server flag.
- Read any experiment's files safely: only inside the experiment folder, only text, with a size limit.
- Keep the files on disk as the record. The database holds only the user's own choices (projects, notebooks, entries).

**Non-Goals:**

- A cache file for scan results. See D4.
- Rendering HTML review pages. They can hold scripts. See D6.
- Changing sandbox contexts, marimo launch or runs, apart from their section names.

## Decisions

### D1. A project is a folder with an `experiments/` directory

`POST /v1/experiment-projects` takes `{ "path": "<absolute path>", "name": "<label>" }`. The server resolves the real path and refuses it unless:

- it is absolute, exists and is a directory;
- it holds a directory named `experiments` (not a link that points outside the project);
- no other project has the same real path.

The stored row keeps the resolved path. Every read checks the path again and reports `unavailable` when it is gone. This is a trust decision like `--root`, made from the browser session. It needs the `manage` session scope, which a bearer credential cannot have.

- Alternative: a `--experiment-project` server flag, like `--root`. Rejected: the user wants the GUI to drive the system, and the login item would need a reinstall for every project.

### D2. Tables (migration 7)

```sql
CREATE TABLE experiment_projects (
  project_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  root TEXT NOT NULL UNIQUE,
  added_at TEXT NOT NULL
);
CREATE TABLE notebooks (
  notebook_id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE notebook_entries (
  notebook_id TEXT NOT NULL REFERENCES notebooks(notebook_id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES experiment_projects(project_id) ON DELETE CASCADE,
  folder TEXT NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY (notebook_id, project_id, folder)
);
```

Project notebooks are not stored. The API presents each project as a notebook with `kind: "project"`, and user notebooks have `kind: "user"`. Removing a project removes its entries from user notebooks, through the foreign key. The experiment folders on disk are never touched.

- Why not a separate `experiments.db`: the user's choices are small and belong with the other workspace data, in one file with one owner, one backup and one migration path. Foreign keys work only inside one database file.

### D3. Core protocol and SQLite class

`core/workspace/experiment_library.py` holds an `ExperimentLibraryRepository` protocol: `list_projects`, `add_project`, `remove_project`, `get_project`, `list_notebooks`, `create_notebook`, `rename_notebook`, `delete_notebook`, `add_entry`, `remove_entry`, `list_entries`. Path checks for D1 live in a pure function in the same module and take the path only, so they are easy to test. `integrations/workspace_sqlite/experiment_library.py` implements the protocol. `runtime.experiment_library` is built in `lifespan.py` next to `runtime.chats`.

### D4. Scan on each request; no cache file

The library route calls `scan` and `check` for the project on each request. The OMRS `experiments/` folder (50 folders) must scan and check in under 200 ms on the developer machine. Task 2.1 measures this. A cache file would add invalidation rules (new files, edited records, renamed folders) for little gain at this size.

- Revisit when a measured scan of a real project takes more than 500 ms. Then cache by the modification times of the `experiment.json` files.
- This changes decision 4 of the exploration, which planned a cache file. The measurement in task 2.1 is the evidence.

### D5. API

All routes are under `/v1`, return JSON with the existing `ok()` and `error_response()` helpers, and run blocking work in `run_in_threadpool` inside `admitted()`.

| Method and path | Scope | Purpose |
|---|---|---|
| `GET /experiment-projects` | read session | List projects with `available` and experiment counts |
| `POST /experiment-projects` | manage session | Add a project (D1). 400 with a reason when refused |
| `DELETE /experiment-projects/{project_id}` | manage session | Remove a project from the list. Files are untouched |
| `GET /experiment-projects/{project_id}/experiments` | read session | Records, findings per folder, reserved numbers, and project-level findings |
| `GET /experiment-projects/{project_id}/experiments/{folder}` | read session | One record, its findings, its top-level file list and the top-level names in `output/` |
| `GET /experiment-projects/{project_id}/experiments/{folder}/files/{name}` | read session | Text of one top-level file (D6) |
| `POST /experiment-projects/{project_id}/experiments` | manage session | Create an experiment (D7) |
| `GET /notebooks` | read session | Project notebooks and user notebooks |
| `POST /notebooks` | read session | Create a user notebook |
| `PATCH /notebooks/{notebook_id}` | read session | Rename |
| `DELETE /notebooks/{notebook_id}` | read session | Delete a user notebook and its entries |
| `GET /notebooks/{notebook_id}` | read session | Entries with their records, or `missing: true` |
| `PUT /notebooks/{notebook_id}/entries` | read session | Add one entry `{project_id, folder}` |
| `DELETE /notebooks/{notebook_id}/entries/{project_id}/{folder}` | read session | Remove one entry |

Response shapes (the web client and the routes both follow these; field names are fixed):

```text
Project      { project_id, name, root, added_at, available: bool, experiment_count: int|null }
Finding      { severity: "error"|"warning"|"info", code, folder: str|null, message }
Experiment   { folder, number, title, date, category: str|null, size: str|null, status,
               superseded_by: str|null, finding, refs: {adrs, changes, tasks}|null,
               migrated: bool, findings: [Finding] }
Reserved     { number, reason, ref }
FileEntry    { name, size, viewable: bool }

GET  /experiment-projects                 -> { projects: [Project] }
POST /experiment-projects                 -> 201 { project: Project }
DELETE /experiment-projects/{id}          -> { removed: true }
GET  .../{id}/experiments                 -> { project: Project, experiments: [Experiment],
                                               reserved: [Reserved], findings: [Finding] }
                                             (findings = project-level, folder null)
GET  .../{id}/experiments/{folder}        -> { project: Project, experiment: Experiment,
                                               files: [FileEntry], output: [str]|null }
GET  .../{folder}/files/{name}            -> { name, text, truncated: bool, size }
POST .../{id}/experiments                 -> 201 { folder, index: "written"|"no-markers"|"no-readme"|"failed",
                                               message?: str }   (message only with "failed")

Notebook     { notebook_id, name, kind: "project"|"user", project_id: str|null,
               entry_count: int, created_at: str|null }
Entry        { project_id, project_name, folder, added_at, missing: bool,
               experiment: Experiment|null }

GET  /notebooks                           -> { notebooks: [Notebook] }   (project notebooks first)
POST /notebooks {name}                    -> 201 { notebook: Notebook }
PATCH /notebooks/{id} {name}              -> { notebook: Notebook }
DELETE /notebooks/{id}                    -> { removed: true }
GET  /notebooks/{id}                      -> { notebook: Notebook, entries: [Entry] }
PUT  /notebooks/{id}/entries {project_id, folder} -> { entry: Entry }
DELETE /notebooks/{id}/entries/{project_id}/{folder} -> { removed: true }
```

A project notebook's id is `project:<project_id>`. It cannot be renamed, deleted or edited (400). Errors use the existing error envelope: 400 validation, 403 scope, 404 unknown project, folder, notebook or file, 409 duplicate project path or notebook name.

Notebook writes use the read session scope, as chat folders do: they change only the user's own grouping. Adding a project and creating an experiment use `manage`, because they read or write files outside the workspace.

`folder` path segments must match a folder that the scan found. A name with `/`, `..` or a leading dot is refused before any file access.

### D6. Reading files

`files/{name}` serves only a file directly inside the experiment folder (no subfolders) whose suffix is `.md`, `.json`, `.jsonl`, `.txt`, `.csv`, `.yaml`, `.yml` or `.py`. The resolved path must stay inside the folder, so a link that points out is refused. Files over 1 MiB return their first 1 MiB with `truncated: true`. The response is JSON `{ name, text, truncated, size }`, never a raw file response, so the browser never renders it as HTML.

The file list marks other files (for example `.html` review pages, images, PDFs) as `viewable: false`. The page shows them with their size and a note that the app does not open them. This keeps scripts in review pages out of the workspace origin, which holds the signed-in session.

Markdown is rendered with `react-markdown` and `remark-gfm`, with no raw-HTML plugin, as Chat does. Relative links between experiment files open in the same page. Other links open in a new tab with `noopener`.

### D7. Creating an experiment

`POST .../experiments` takes `{slug, title, category, size, follow_up?}`. It calls the `experiment-format-v1` folder creator with today's date, then rewrites the index in the project's `EXP_README.md` when both markers exist. The response returns the new folder name and `index: "written" | "no-markers" | "no-readme" | "failed"`. `failed` means the folder exists but `EXP_README.md` could not be read, is not valid UTF-8, or could not be replaced. Then the response also has a plain `message` that names `omrs experiments index --write` as the fix. The rewrite replaces the file atomically, so a failure never leaves a half-written file. A refusal from the creator (folder exists, bad slug) returns 400 with its message and writes nothing.

### D8. Web screens

- `ExperimentsView` sections: Library (default), Notebooks, Sandboxes, Code editor, Runs. The existing `FoldersSection` becomes Sandboxes and the existing `NotebooksSection` becomes Code editor, unchanged inside.
- Routes: `#/experiments/library/<project_id>/<folder>` for the experiment page, and `#/experiments/notebooks/<notebook_id>` for a notebook. Existing run routes stay.
- Library: a project picker ("All projects" first), an "Add project" form (path and name), filters (status, category), a text search over number, title and finding, and cards. A card shows number, title, status badge, category, date, finding, and a small count of checker warnings and errors.
- Experiment page: a header with the record fields and links to `superseded_by`; tabs Protocol, Plan, Report, Files, Checks; an "Add to notebook" menu.
- Notebooks: the list of project and user notebooks, a create form, and a notebook page with its entry cards and a remove action.
- Status badge colours reuse the existing badge variants: `PASS` success, `FAIL` error, `INCONCLUSIVE` and `ACTIVE` warning, `PLANNED` and `MEASURED` info, `SUPERSEDED` muted.
- The `omrs-design` skill is loaded before UI work. Phone width (390 px) shows one card per row with no sideways scroll.

## Risks / Trade-offs

- [A project path from the browser lets the server read files there] → `manage` session scope only, text files only, inside experiment folders only, 1 MiB limit, links that point out refused. This is the same trust level as `--root`, given from the GUI.
- [Scanning on each request gets slow for a large project] → Measured in task 2.1. The rule to add a cache is written in D4.
- [Renaming sections confuses current users of "Notebooks"] → The marimo panel keeps its content. Its chip reads "Code editor". The guide names both.
- [A notebook entry points to a folder that was renamed] → Shown as missing with a remove action. Nothing is deleted on its own.
- [The live database upgrade to version 7] → The existing migration path makes a backup first. The new tables are additive. Rollback: stop the server and restore the backup file.

## Migration Plan

1. Merge `experiment-format-v1` first.
2. Ship migration 7. On the next start, `omrs web` backs up `workspace.db` and adds the three tables.
3. No data move. The user adds projects from the Library.

Rollback: revert the commits and restore the `workspace.db.v6-to-v7.*.bak` backup.
