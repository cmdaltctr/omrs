# Experiment records

This guide describes the experiment format `omrs-experiment/1`. The format ships in the `omrs` package, in `omrs.core.experiment_records`. The rules for agents are in [experiments/AGENTS.md](../../experiments/AGENTS.md). The decision is recorded in [ADR-097](../adr/097-experiment-records-versioned-format.md).

## The experiment folder

An experiments directory holds one folder for each experiment. The default directory is `experiments/` at the repository root.

A subfolder is an experiment folder when one of these is true:

- It contains `experiment.json`.
- Its name matches `<number>-<slug>-<YYYY-MM-DD>`.

The tools ignore all other subfolders, for example `_lib/`, `ARCHIVED/` and `example/`.

The tools read only the top level of each `output/` folder. They do not open the files in it.

### Folder names

| Part | Rule | Example |
| --- | --- | --- |
| `number` | One or more digits, then one optional lower-case letter or one optional dot and digits | `43`, `38a`, `10.1` |
| `slug` | Lower-case letters and digits, joined by single hyphens | `ocr-text-quality` |
| `date` | The day the plan was written, as `YYYY-MM-DD` | `2026-10-26` |

The folder name is the identity of the experiment. The number is a label. Old folders can use the same number twice. The checker reports that as a warning on converted records.

The folder name does not contain the category. The category is in `experiment.json`.

### Files for each size

| Size | Required files |
| --- | --- |
| `Quick` | `experiment.json`, `report.md` |
| `Standard` | `experiment.json`, `protocol.md`, `plan.json`, `report.md` |
| `Confirmatory` | The Standard files. Commit `protocol.md` and `plan.json` before the first run. |

## The record file: `experiment.json`

Each experiment folder has one `experiment.json`. It holds the facts that change after planning, and the facts that the index needs.

```json
{
  "format": "omrs-experiment/1",
  "number": "43",
  "title": "OCR text quality",
  "date": "2026-10-26",
  "category": "ingestion",
  "size": "Standard",
  "status": "PLANNED",
  "superseded_by": null,
  "finding": "",
  "refs": {"adrs": [], "changes": [], "tasks": []}
}
```

| Field | Required | Rule |
| --- | --- | --- |
| `format` | Yes | Must be `omrs-experiment/1`. |
| `number` | Yes | A string with the number pattern above. An empty string means an unnumbered experiment. |
| `title` | Yes | One line. Not empty. |
| `date` | Yes | The date in the folder name. |
| `category` | Yes, unless `migration` is set | `retrieval`, `ingestion`, `runtime`, `generation`, `graph` or `review`. |
| `size` | Yes, unless `migration` is set | `Quick`, `Standard` or `Confirmatory`. |
| `status` | Yes | One of the seven status values below. |
| `superseded_by` | Only with `SUPERSEDED` | The folder name of the newer experiment. Otherwise `null` or absent. |
| `finding` | Yes | One line. It can be empty while the experiment is `PLANNED`. |
| `purpose` | No | `optimisation` or `publication`. A record without it counts as `optimisation`. See [Local models and the experiment purpose](#local-models-and-the-experiment-purpose). |
| `refs` | No | Lists of ADRs (`adrs`), OpenSpec changes (`changes`) and tasks (`tasks`). |
| `migration` | No | Set only on folders converted from the old layout. |

A record with a key that the format does not define does not load. The error names the key.

A record with a different `format` value does not load. The error names the version and tells you to install a newer `omrs`.

A JSON Schema for the record ships at `omrs/core/experiment_records/schema/experiment.v1.schema.json`. The package generates it from the record model, so the two always agree.

### The migration note

The one-time move of the old folders added a `migration` note to each converted record:

| Field | Meaning |
| --- | --- |
| `from_status` | The original status text, unchanged |
| `source` | The file the status came from, for example `EXP_README.md` |
| `date` | The date of the conversion |

Do not add a `migration` note to a new record.

## Status values

| Status | Meaning |
| --- | --- |
| `PLANNED` | The plan is written. No run has started. |
| `ACTIVE` | A run has started, or work is still open. |
| `PASS` | The gates passed and the primary hypothesis holds. |
| `FAIL` | A gate failed, or the primary hypothesis does not hold. |
| `INCONCLUSIVE` | The experiment ran, but it did not answer the question. |
| `MEASURED` | A measurement with no pass or fail gate. |
| `SUPERSEDED` | A later experiment replaces this one. `superseded_by` names its folder. |

The status is in `experiment.json` only. Do not write a status into `plan.json`, `protocol.md` or `report.md` of a new experiment.

## The plan file: `plan.json`

`plan.json` is the machine-readable plan for Standard and Confirmatory experiments. It has no `status` key.

`plan.json` is frozen after the first run. No tool writes to it. The run identity in `experiments/_lib/checkpoint_validity.py` includes the SHA-256 of `plan.json`, so a change to the file stops a resume. Record a change to the plan as a new entry in its `amendments` list, and say why.

## Local models and the experiment purpose

Every experiment has a purpose. `optimisation` means the result tunes this project and is not cited outside it. `publication` means the result may be cited in a paper, so another group must be able to reproduce it on other hardware. A record without `purpose` counts as `optimisation`. ADR-103 records the rule.

Every new experiment runs each local language, embedding and decision model through llama.cpp with a public GGUF file. Do not use Ollama, MLX or oMLX for experiment evidence. A hosted model can run as a reference arm. For a `publication` experiment, `omrs experiments check` enforces the rule. For an `optimisation` experiment, the rule is a guide rule only.

To plan and run an experiment with local models:

1. Choose the purpose: `optimisation` or `publication`.
2. For `publication`, choose the size `Confirmatory`.
3. Run `uv run --no-sync omrs experiments new <slug> --title "<title>" --category <category> --size <size> --purpose <purpose>`.
4. Download each GGUF file from its Hugging Face repository.
5. Get the SHA-256 of each file with `shasum -a 256 <file>`.
6. Get the llama.cpp build number from `GET /props` (`build_info`, for example `b11671-ba3c05f71`).
7. Add a `runtime` block to `plan.json` (see the example below).
8. Add one `models` entry for each local model.
9. Add one `references` entry for each hosted model.
10. Add one `tolerance` entry for each primary metric or per-item score.
11. Commit `protocol.md` and `plan.json` before the first run.
12. Start `llama-server` on `127.0.0.1` with the file and arguments in the plan.
13. In the runner, call `verify_llamacpp_runtime(block, base_url=<server address>)` before the first score.
14. Call `record_run_start(HERE, runtime=found.as_run_record())`.

```json
"runtime": {
  "runtime_under_test": false,
  "models": [
    {
      "role": "embedding",
      "repository": "Qwen/Qwen3-Embedding-0.6B-GGUF",
      "file": "Qwen3-Embedding-0.6B-Q8_0.gguf",
      "sha256": "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
      "runtime": "llama.cpp",
      "build": 11671,
      "server_args": {"pooling": "last", "ubatch-size": 8192, "ctx-size": 8192}
    }
  ],
  "references": [{"role": "reference", "provider": "cloudflare", "model": "clef-flash"}],
  "tolerance": [
    {"metric": "recall_at_10", "max_abs_change": 0.01},
    {"item_score": "noul", "max_abs_change": 0.10}
  ]
}
```

| Field | Rule |
| --- | --- |
| `runtime_under_test` | `true` only when the runtime is the variable under test. |
| `models[].role` | What the model does, for example `embedding`, `language` or `decision`. |
| `models[].repository` | The Hugging Face repository of the GGUF file. A community file is allowed. |
| `models[].file` | The file name, with no folder. |
| `models[].sha256` | The SHA-256 of the file: 64 lower-case hex characters. |
| `models[].runtime` | `llama.cpp`. Another runtime is allowed only with `runtime_under_test` set to `true`. |
| `models[].build` | The exact llama.cpp build number, not a minimum. |
| `models[].version` | The runtime version. Required for a runtime other than `llama.cpp`. |
| `models[].server_args` | Each server argument that can change output, for example pooling or context size. |
| `references[]` | `role`, `provider` and `model` for each hosted model. |
| `tolerance[]` | `metric` or `item_score`, with `max_abs_change`: the largest change that still counts as the same result. At least one entry. |

The runner code looks like this:

```python
from _lib.llamacpp_runtime import verify_llamacpp_runtime
from _lib.run_record import record_run_start
from omrs.core.experiment_records.runtime_block import load_runtime_block

block = load_runtime_block(plan)
found = verify_llamacpp_runtime(block, base_url="http://127.0.0.1:8080")
record_run_start(HERE, runtime=found.as_run_record())
```

`verify_llamacpp_runtime` reads the build from `/props`. It reads each model path from `/v1/models` in router mode, or from `/props` with one model. It hashes each file and compares the results with the plan. It talks only to a loopback address. A difference raises `PreflightError` before any score is written, and the message names the expected and the found value. The run record then holds `runtime`: the build and one `{file, sha256}` for each model.

To run on another llama.cpp build:

1. Add an entry to `amendments` in `plan.json` that names the new build.
2. Change `build` in the `runtime` block.
3. Run again.
4. Compare the result with the earlier result against the tolerance.

A past experiment keeps its record. To use its result in a paper, create a `publication` follow-up with `--follow-up <number>`, for example `38a`, and run it again.

## Reserved numbers: `reserved.json`

`experiments/reserved.json` lists numbers that are reserved but have no folder yet. Git tracks the file, so a reservation in one worktree reaches the other worktrees on merge.

```json
{
  "format": "omrs-experiment-reservations/1",
  "reservations": [
    {"number": "44", "reason": "Planned OCR follow-up", "ref": "openspec/changes/<change-id>"}
  ]
}
```

Each entry has a `number`, a one-line `reason` and a one-line `ref`. A missing file means no reservations.

To reserve a number:

1. Open `experiments/reserved.json`.
2. Add an entry to the `reservations` list.
3. Commit the file.

When the folder exists, remove the entry.

## Run records: `output/run-records.jsonl`

Each run appends one line to `output/run-records.jsonl` when it starts. A resume also appends a line. The tools never change an earlier line.

| Field | Meaning |
| --- | --- |
| `format` | `omrs-run-record/1` |
| `started_at` | The start time in UTC |
| `git_commit` | The commit the run started from |
| `git_dirty` | `true` when the working tree had uncommitted changes |
| `plan_sha256` | The SHA-256 of `plan.json`, or an empty string when there is no plan |
| `command` | The command that started the run |
| `runtime` | Optional. The llama.cpp `build` and one `{file, sha256}` for each model, from the live-server check |

To add run records to a runner:

1. Import `record_run_start` from `experiments/_lib/run_record.py`.
2. Call `record_run_start(HERE)` at the start of `main()`, before the first cell.
3. Pass `command=` only when `sys.argv` does not show the real command.

The helper reads the git commit and the dirty flag. It then calls the append function in `omrs.core.experiment_records.run_record`.

`output/` is not in git. Copy it, with its run records, to the local data store before you remove a worktree. The repository `AGENTS.md` names the data store and the copy procedure.

## Edit log: `edits.jsonl`

The web app appends one line to `edits.jsonl` in the experiment folder each time it saves `protocol.md` or the report file. Git tracks the file. The app never changes or removes an earlier line. It does not log edits made outside the app: git records those.

| Field | Meaning |
| --- | --- |
| `format` | `omrs-edit-record/1` |
| `file` | The file name, for example `protocol.md` |
| `edited_at` | The time of the save in UTC, with seconds |
| `before_sha256`, `after_sha256` | The SHA-256 of the file bytes before and after the save |
| `before_size`, `after_size` | The size of the file in bytes before and after the save |
| `status` | The record status at the time of the save |
| `converted` | `true` when the record has a `migration` note |
| `tool` | The tool that saved the file, for example `omrs web 3.4.0` |

A line holds no user name, login or path. A line with a key that the format does not define does not load.

To match a line against git:

1. Find a commit that changed the file: `git log --oneline -- <folder>/<file>`.
2. Print the SHA-256 of the file in that commit: `git show <commit>:<folder>/<file> | shasum -a 256`.
3. Compare the result with `before_sha256` or `after_sha256`.

Git's own object id is a different hash, so do not compare the log with it.

## The index table

The index table in `experiments/EXP_README.md` is generated from the `experiment.json` files. It is between two marker lines:

```text
<!-- omrs:experiment-index:start -->
<!-- omrs:experiment-index:end -->
```

The table has five columns: number, experiment (a link to the folder), date, status and finding. Rows are sorted by number, then by folder name. Unnumbered experiments come last.

The generator changes only the lines between the markers. It does not pad the cells, so a new experiment changes one line. It writes `|` in a cell as `\|`. It refuses to write a file that does not have both markers.

Do not edit the rows between the markers by hand.

## Commands

All commands write their output to stderr. `DIR` is the experiments directory. The default is `./experiments`.

| Command | Effect |
| --- | --- |
| `omrs experiments check [DIR] [--strict] [--json]` | Reads the directory and reports findings. It does not write a file. |
| `omrs experiments index [DIR] [--write]` | Without `--write`, prints the table. With `--write`, replaces the marked block. |
| `omrs experiments new SLUG --title T --category C --size S [--purpose P] [--follow-up N] [--date D] [DIR]` | Creates a folder and prints its path. |

### Check the experiments

1. Run `uv run --no-sync omrs experiments check`.
2. Read each finding. Each one has a severity, a code, a folder and a message.
3. Fix each `error` finding.
4. Run the command again until it reports no errors.

The command exits with code 1 when it finds an error. With `--strict`, it also exits with code 1 when it finds a warning. Add `--json` to get the findings as JSON.

### Rebuild the index

1. Run `uv run --no-sync omrs experiments index`.
2. If the command exits with code 1, the table in `EXP_README.md` is stale.
3. Run `uv run --no-sync omrs experiments index --write`.
4. Commit `EXP_README.md` with the record change.

### Create an experiment

1. Choose a slug, a title, a category, a size and a purpose.
2. Run `uv run --no-sync omrs experiments new <slug> --title "<title>" --category <category> --size <size> --purpose <purpose>`.
3. Read the folder path that the command prints.
4. Fill in the plan files in that folder.

The command takes the next whole number above every folder number and every reserved number. For a follow-up, add `--follow-up <number>`. The command then takes the next free letter, for example `38a` and then `38b`.

The command writes `experiment.json` with status `PLANNED`, the purpose (`optimisation` when `--purpose` is absent) and the template files for the size. It does not overwrite a file. It refuses a folder name that exists, and then writes nothing.

## Checker codes

Each finding has a stable code. Some codes are less severe on a converted record (a record with a `migration` note).

| Code | Severity | Problem | What to do |
| --- | --- | --- | --- |
| `record-missing` | error | A detected experiment folder has no `experiment.json`. | Write `experiment.json`. |
| `record-invalid` | error | `experiment.json` does not load. The message names the key or the rule. | Fix the named field. |
| `folder-name` | warning | The folder has a record, but its name does not match `<number>-<slug>-<YYYY-MM-DD>`. | Leave an old folder as it is. Use the pattern for new folders. |
| `number-mismatch` | error | The record `number` differs from the number in the folder name. | Correct `number` in `experiment.json`. |
| `date-mismatch` | error | The record `date` differs from the date in the folder name. | Correct `date` in `experiment.json`. |
| `superseded-target-missing` | error | The `superseded_by` value does not name another experiment folder in this directory, or names the record's own folder. | Correct the folder name. |
| `number-shared` | error; warning if converted | More than one folder uses the same number. | Give the new folder the next free number. |
| `report-status` | warning; info if converted | The `Status` line in `report.md` differs from the record status. | Make the record status correct. The record wins. |
| `size-missing` | info | A converted record has no `size`. | Add `size` when you know it. |
| `category-missing` | info | A converted record has no `category`. | Add `category` when you know it. |
| `files-missing` | warning; info if converted | A file that the size needs is missing. | Add the file, or correct `size`. |
| `run-records-invalid` | warning | `output/run-records.jsonl` has a line that does not load. | Find the bad line. Do not change the other lines. |
| `edit-log-invalid` | warning | A line of `edits.jsonl` does not load, or the file is a link or not a regular file. The message names the line. | Find the bad line in the git history of `edits.jsonl`. Do not change the other lines. |
| `plan-changed` | warning | A run record has a `plan_sha256` that differs from the current `plan.json`. | Record the change as an amendment. Rerun if the plan change affects the result. |
| `publication-not-confirmatory` | error | A `publication` record has a size other than `Confirmatory`. | Set `size` to `Confirmatory`, or set `purpose` to `optimisation`. |
| `publication-plan-unreadable` | error | A `publication` record has no `plan.json`, or the file does not load. | Write a valid `plan.json`. |
| `publication-runtime-missing` | error | The `plan.json` of a `publication` record has no `runtime` block. | Add the `runtime` block. |
| `publication-runtime-invalid` | error | The `runtime` block of a `publication` record does not load. The message names the field. The template values (build `0`, a SHA-256 of 64 zeros) also fail. | Fix the named field. Pin the real file and build. |
| `reserved-invalid` | error | `reserved.json` does not load. | Fix the named entry. |
| `reserved-has-folder` | info | A reserved number now has a folder. | Remove the entry from `reserved.json`. |
| `index-missing` | warning | `EXP_README.md` does not exist. | Create it with both index markers. |
| `index-markers` | error | `EXP_README.md` does not have both index markers. | Add the missing marker line. |
| `index-stale` | error | The index table differs from the generated table. | Run `uv run --no-sync omrs experiments index --write`. |

## Experiments in the web workspace

The web workspace (`omrs web`) shows the experiments of each project you add. It reads the files on disk on each request. It stores only your project list and your notebooks, in the workspace database.

The Experiments area has five sections:

| Section | Shows |
|---|---|
| Library | The experiments of one project or of all projects, as cards with status, finding and checker counts. |
| Notebooks | One notebook for each project, plus notebooks that you make. |
| Sandboxes | Experiment contexts for notebook runs (`--experiment-root`). |
| Code editor | The marimo notebook editor plugin. |
| Runs | Pipeline runs. |

### Add a project

1. Open **Experiments**, then **Library**.
2. Select **Add project**.
3. Type the absolute path of a folder that holds an `experiments` folder.
4. Type a name, then select **Add**.

The server refuses a folder without an `experiments` folder. It also refuses an `experiments` link that points outside the project. Removing a project removes it from the list and from your notebooks. It does not change any file.

### Read an experiment

Select a card to open the experiment page. The tabs show the protocol, the plan, the report and the checker findings. An older folder without `report.md` shows `results.md` in the Report tab. You can edit the Protocol and Report tabs (see the next section). The other tabs are for reading only.

The app opens only text files at the top level of the experiment folder: `.md`, `.json`, `.jsonl`, `.txt`, `.csv`, `.yaml`, `.yml` and `.py`. It shows the first 1 MiB of a larger file. It lists other files, such as HTML review pages, but does not open them, because they can hold scripts. Open those files from your file manager.

### Edit a protocol or report from the app

The app can edit `protocol.md` and the report file (`report.md`, or `results.md` in an older folder without `report.md`) of any experiment. It edits only a file that exists, up to 1 MiB of UTF-8 text with no NUL character. It never edits `plan.json`, the scripts or `experiment.json`.

1. Open the experiment page.
2. Select the **Protocol** tab or the **Report** tab.
3. Select **Edit**.
4. Read the warning. A finished or converted experiment shows one, because its protocol and report are part of the record.
5. Change the text.
6. Select **Save**. The page shows "Saved." and "Last edited" with the date and time.
7. Commit the edited file and `edits.jsonl` together, and say why in the commit message.

Select **Cancel** to stop without a save. When you have changes, the page asks before it discards them.

Each save adds one line to `edits.jsonl` in the experiment folder (see [Edit log](#edit-log-editsjsonl)). The app does not log edits made outside the app, for example in a text editor or by an agent. Git records those. The app never runs git and never commits.

When the file changed on disk after you opened the editor, the save is refused and your text stays in the editor. Copy your text, select **Reload**, then add your changes again.

### Open an experiment in marimo

The experiment page can open the analysis of the experiment in the marimo notebook editor. The notebook runs with your full access, in the `.venv` of the project.

1. Register marimo in **Code editor** first.
2. Open the experiment page, then select **Open in marimo**.
3. Read the dialog and tick the box.
4. Select **Open in marimo** in the dialog. The editor opens in a new browser tab.
5. Paste the access token from the page into the marimo sign-in page.

OMRS converts `analysis.py` to `analysis.marimo.py` in the experiment folder. It does not change a tracked file. Add `experiments/**/analysis.marimo.py` and `experiments/**/__marimo__/` to the `.gitignore` of the project. Read [Full access from the Library](notebooks.md#full-access-from-the-library) before you open a notebook.

### Group experiments in a notebook

1. Open **Notebooks**.
2. Type a name, then select **Create**.
3. Open an experiment, then select **Add to notebook**.

A notebook can hold experiments from more than one project. When a folder is renamed or removed on disk, its entry shows as missing. Remove it from the notebook yourself.

### Create an experiment from the app

1. Open **Library** and select one project.
2. Select **New experiment**.
3. Type the slug, title, category and size. Choose the purpose. **Publication** sets the size to Confirmatory. For a follow-up, type the number it follows.
4. Select **Create**.

The app runs the same folder creator as `omrs experiments new`. It then rewrites the index table in `EXP_README.md` when the file has both index markers.
