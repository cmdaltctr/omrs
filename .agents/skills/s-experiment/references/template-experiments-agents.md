# Experiments: rules for agents

This folder uses the experiment format `omrs-experiment/1`. These rules apply to every experiment folder here.

## Before you start

- Read the repository [AGENTS.md](../AGENTS.md) first. It wins on code paths and settings.
- Read [EXP_README.md](EXP_README.md) to find related experiments.
- To resume, read the experiment's `experiment.json`, `protocol.md`, `plan.json` and `report.md`.

## Folder names

- Name each folder `<number>-<slug>-<YYYY-MM-DD>`, for example `43-ocr-text-quality-2026-10-26`.
- The slug uses lower-case letters, digits and single hyphens. The date is the day you write the plan.
- The folder name is the identity of the experiment. The number is a label.
- A follow-up takes the next free letter: `38a`, then `38b`.
- Never rename or move an existing folder.
- Do not add `AGENTS.md` or `CLAUDE.md` to an experiment folder. This file covers them all.

## The record file

Each folder has one `experiment.json`. It holds the facts that change after planning:

| Field | Meaning |
| --- | --- |
| `format` | Always `omrs-experiment/1` |
| `number` | The number in the folder name, as a string (`22`, `5b`, `10.1`), or empty |
| `title` | A short title |
| `date` | The date in the folder name |
| `category` | `retrieval`, `ingestion`, `runtime`, `generation`, `graph` or `review` |
| `size` | `Quick`, `Standard` or `Confirmatory` |
| `status` | One of the seven values below |
| `superseded_by` | The folder that replaces this one, only with `SUPERSEDED`; else `null` |
| `finding` | The answer in one line |
| `refs` | Optional lists: `adrs`, `changes`, `tasks` |
| `migration` | Set only on folders converted from the old layout |

Unknown keys are an error. Status lives only in `experiment.json`. Do not write a status into `plan.json`, `protocol.md` or `report.md`.

## Status values

| Status | Meaning |
| --- | --- |
| `PLANNED` | The plan is written. No run has started. |
| `ACTIVE` | A run has started, or work is still open. |
| `PASS` | The gates passed and the primary hypothesis holds. |
| `FAIL` | A gate failed, or the primary hypothesis does not hold. |
| `INCONCLUSIVE` | The run finished but did not answer the question. |
| `MEASURED` | A measurement with no pass or fail gate. |
| `SUPERSEDED` | A later experiment replaces this one. Set `superseded_by` to its folder name. |

## Sizes and files

| Size | Files |
| --- | --- |
| Quick | `experiment.json`, `report.md` (plan at the top) |
| Standard | `experiment.json`, `protocol.md`, `plan.json`, `report.md` |
| Confirmatory | The Standard set. Commit `protocol.md` and `plan.json` before the first run. |

## Make an experiment

- Create the folder with `uv run --no-sync omrs experiments new <slug> --title "<title>" --category <category> --size <size>`.
- Add `--follow-up <number>` for a follow-up of an earlier experiment.
- The command takes the next free number. It skips every number in `reserved.json`.
- To reserve a number without a folder, add `{"number", "reason", "ref"}` to the `reservations` list in `reserved.json`.
- Write the plan before you run. The hypothesis, the null and the decision rule are required.

## While it runs

- `plan.json` is frozen after the first run. No tool writes to it. Record a change as a new entry in its `amendments` list.
- Each run appends one line to `output/run-records.jsonl` with the start time, git commit, dirty-tree flag, plan SHA-256 and the command. Call the helper in `_lib/run_record.py` at the start of each run.
- Never change an earlier line in `output/run-records.jsonl`.
- Converted folders (with a `migration` note) can have no run records. Do not add them after the fact.
- Write only inside the experiment folder. Never touch production data or `.env`.
- Never edit `output/` by hand. Regenerate it with the scripts.
- Use `_lib/stats.py` for statistics. Do not write new statistics code.

## Report

- `report.md` opens with the Answer box: question, answer, decision, how sure, next step.
- Every number names the `output/` file it came from.
- Write plain British English. Explain each term where it first appears.
- Keep negative and unclear results.

## Keep the record and the index current

- In a finished or converted experiment, change only `experiment.json`. Never edit its other files.
- Update `status` and `finding` in `experiment.json` at each step.
- Rebuild the index table with `uv run --no-sync omrs experiments index --write`. Do not edit the rows between the index markers by hand.
- Check the folder with `uv run --no-sync omrs experiments check`. Fix every error before you commit.

## Keep the data

- `output/` is not in git. Before you remove a git worktree, copy each experiment's `output/` to the local data store that the repository `AGENTS.md` names.
- Record a SHA-256 checksum for each copy. Check the copy before you remove the worktree.
- Do not upload `output/` to a public host.
