# ADR-100: Experiment Library Reads Project Folders and Keeps Choices in the Workspace Database

- **Date:** 2026-10-25
- **Status:** Accepted (2026-10-25; built and merged to v3 at PR #128, merge commit `24b971bf`. Recorded on 2026-10-26: the change shipped without its own ADR.)
- **Deciders:** Maintainer
- **Related:** ADR-097 (experiment record format), ADR-080 (the web server owns the workspace), ADR-099 (open in marimo)
- **Change:** `openspec/changes/archive/2026-10-25-experiments-in-web-workspace/` (design D1 to D8)

## Context

ADR-097 gave each experiment folder an `experiment.json` record and a
package that scans and checks a folder of experiments. The web workspace
had no way to show them. The user wanted to:

- add any project that has an `experiments/` folder, from the GUI;
- read an experiment's protocol, plan and report in the app;
- group experiments from several projects into notebooks;
- create a new experiment from the app.

Three questions needed an answer:

1. Where the user's choices (projects, notebooks, notebook entries) live: a
   new `experiments.db`, or the existing `workspace.db`.
2. Whether the app keeps a copy of the experiment records, or reads the
   files each time.
3. How far the app may read files in a folder that the browser names.

The workspace database already has one owner (`omrs web`, ADR-080), a
migration list with a backup before each upgrade, and stored chats that
follow a repository protocol plus a SQLite class.

## Decision

1. **The files on disk are the record.** The app never copies
   `experiment.json`, protocols or reports into a database. The database
   holds only the user's own choices.
2. **The choices live in `workspace.db`, migration 7.** Three tables:
   `experiment_projects`, `notebooks` and `notebook_entries`. Entries use
   foreign keys with `ON DELETE CASCADE`, so removing a project removes its
   notebook entries. Foreign keys work only inside one database file. One
   file also keeps one owner, one backup and one migration path.
3. **A project is a folder with an `experiments/` directory, added from the
   GUI.** The server resolves the real path. It refuses a path that is not
   absolute, is not a directory, has no `experiments` directory, has an
   `experiments` link that points outside the project, or is already added.
   Adding a project needs the `manage` session scope, which a bearer
   credential cannot have. This is the same trust level as `--root`.
4. **Each request scans the project again. There is no cache file.** The
   measured scan and check of the OMRS `experiments/` folder (50 folders)
   took 6.3 ms median and 8.2 ms at most. A cache would add rules for new,
   edited and renamed folders for no gain at this size.
5. **The app reads text files only, inside the experiment folder.** It
   serves top-level files with a fixed list of text suffixes, inside the
   folder after path resolution, up to 1 MiB (then truncated). The response
   is JSON, never a raw file, so the browser never renders it as HTML. HTML
   review pages, images and PDFs are listed with their size and are not
   opened. Markdown is rendered with no raw-HTML plugin.
   - *Amended by [ADR-102](102-library-edits-protocol-and-report-with-an-edit-log.md) (2026-10-26):* the app can now also save
     `protocol.md` and the report file of a listed experiment, with a
     revision check and an atomic write. Each save adds one line to
     `edits.jsonl`. It writes no other file.
6. **Project notebooks are not stored.** The API shows each project as a
   notebook with `kind: "project"` and id `project:<project_id>`. It cannot
   be renamed, deleted or edited. User notebooks have `kind: "user"`.
7. **Creating an experiment uses the ADR-097 folder creator.** The route
   then rewrites the index in `EXP_README.md` when both markers exist. The
   response says `written`, `no-markers`, `no-readme` or `failed`. `failed`
   keeps the new folder and names `omrs experiments index --write` as the fix.
8. **Notebook writes need only the read session scope.** They change only
   the user's own grouping, as chat folders do. Adding a project and
   creating an experiment need `manage`, because they read or write files
   outside the workspace.

## Consequences

### Positive

- The user adds a project, reads its experiments and groups them, with no
  restart and no server flag.
- No copy of the records can go stale. An edit in a terminal shows on the
  next page load.
- One backup of `workspace.db` covers every user choice.
- Removing a project never touches the experiment folders on disk.

### Negative

- A folder that the browser names becomes readable by the server, within
  the limits in decision 5. The `manage` scope is the only gate.
- A scan of a much larger project costs time on each request.
- A renamed experiment folder leaves its notebook entries as `missing`.
  The user removes them by hand.

### Neutral

- The MCP server, the CLI and the watcher do not read the new tables
  (gotcha 17).
- The old "Notebooks" section (marimo) is now called "Code editor", and
  the old folders section is now "Sandboxes".

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **A separate `experiments.db`** | Foreign keys do not work across database files. It adds a second owner, backup and migration path for three small tables. |
| **A cache file of scan results** | The measured scan is under 10 ms. A cache needs invalidation rules for new, edited and renamed folders. Revisit when a real project takes more than 500 ms. |
| **A `--experiment-project` server flag, like `--root`** | The user wants the GUI to drive the system. The login item would need a reinstall for every new project. |
| **Copy records into the database** | Two sources of truth. A status change in a terminal would not show until the next import. |
| **Serve HTML review pages** | They can hold scripts, and the workspace origin holds the signed-in session. |

## Revisit Triggers

- A measured scan of a real project takes more than 500 ms. Then cache by
  the modification times of the `experiment.json` files.
- The app needs to read subfolders or binary files of an experiment.
- A second process needs to write the new tables.

## References

- `src/omrs/core/workspace/experiment_library.py` (repository protocol and path checks)
- `src/omrs/integrations/workspace_sqlite/experiment_library.py` and `schema.py` (migration 7)
- `src/omrs/core/workspace/experiment_pages.py`, `experiment_notebooks.py`
- `src/omrs/transports/api/routes/experiments.py`, `notebooks.py`
- `web/src/experiments/`
- `openspec/specs/workspace-experiment-library/`
- `openspec/changes/archive/2026-10-25-experiments-in-web-workspace/timing.md` (scan measurement)
