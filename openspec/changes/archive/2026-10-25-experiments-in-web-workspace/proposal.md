# Proposal

## Why

The Experiments area of the web workspace cannot show the research experiments that OMRS keeps in `experiments/`. It shows only sandbox contexts (in memory, gone on restart, and unusable today because the login item starts no experiment root), marimo editor launch and pipeline runs. To read a protocol or a report, the user opens files by hand.

The `experiment-format-v1` change gives every experiment folder a versioned `experiment.json`, a checker, a generated index and a folder creator. This change puts them in the web workspace, so the app can drive the experiment work: see every experiment, read its files, group experiments into notebooks and start a new experiment.

## What Changes

- **Experiment projects.** The user adds a project from the web workspace by giving the path of a folder that holds an `experiments/` directory. The workspace database stores the list. The path is checked when it is added and again on every read.
- **Library.** A new default section of Experiments lists the experiments of one project or of all projects as cards: number, title, status, category, date, finding and checker findings. The user filters by status and category and searches by text.
- **Experiment page.** `#/experiments/library/<project>/<folder>` shows the record, the protocol, the plan, the report (or `results.md` for older folders), the file list with the top-level names in `output/`, and the checker findings. Markdown is rendered without raw HTML. HTML files are listed but not opened.
- **Notebooks.** Every project is a notebook made automatically. The user can also create a named notebook and add experiments from any project to it. The workspace database stores user notebooks and their entries. An entry whose folder no longer exists is shown as missing, not deleted.
- **New experiment.** A form in the Library creates a folder through the `experiment-format-v1` folder creator, then rewrites the index table in that project's `EXP_README.md` when the file has the index markers.
- **Names in Experiments.** The sections become Library, Notebooks, Sandboxes (was "Experiments": sandbox contexts), Code editor (was "Notebooks": marimo) and Runs. The sandbox and marimo panels keep their behaviour.
- New HTTP routes with OpenAPI entries, a workspace database migration (version 7), and web client, queries and screens.

Out of scope: running an experiment from the app, linking runs or sandboxes to an experiment, git history checks (whether a plan was committed before its run), and editing existing experiment files. Later changes can add them.

## Capabilities

### New Capabilities

- `workspace-experiment-library`: experiment projects, the library listing, the experiment page and file reading, notebooks, and creating experiments from the web workspace.

### Modified Capabilities

- `workspace-experiments`: the Experiments view gains the Library and Notebooks sections, and the existing sections are renamed Sandboxes and Code editor.

## Impact

- `src/omrs/core/workspace/`: a repository protocol for projects and notebooks.
- `src/omrs/integrations/workspace_sqlite/`: migration 7 and the SQLite repository.
- `src/omrs/transports/api/routes/`: a new route module; `openapi.yaml`; runtime wiring in `lifespan.py`.
- `web/src/experiments/` and `web/src/api/`: new client, queries, Library, experiment page, Notebooks and new-experiment form; renamed section chips; a new route in `web/src/lib/routes.ts`.
- Docs: `docs/guides/experiment-records.md` (web section), `docs/guides/web-workspace.md`, `src/omrs/transports/api/README.md`.
- No new dependency. `react-markdown` and `remark-gfm` are already in the web package.
- The live workspace database is upgraded to version 7 on the next start of `omrs web`, with the usual automatic backup.
