---
name: s-experiment
description: "Plan, run and report experiments for OMRS in the experiments/ folder, in the experiment format omrs-experiment/1. Use when the user asks to plan, design, run, resume, summarise or analyse an experiment, write a hypothesis or protocol, choose statistics, write report.md, update experiment.json, reserve an experiment number, or set up an experiments folder. Triggers: \"run experiment\", \"plan experiment\", \"create experiment\", \"experiment N\", \"resume eval\", \"summarise results\", \"experiment protocol\", \"hypothesis\", \"stats level\", \"eval runner\", \"ground truth\", \"report.md\", \"experiment.json\", \"analysis.py\", \"omrs experiments\"."
---

# s-experiment (OMRS repository copy)

This skill runs experiments in a fixed, simple way. Every experiment answers one question, and every report starts with the answer. This copy follows the experiment format `omrs-experiment/1`, which ships in the `omrs` package.

## Rules that always apply

1. One experiment answers one question, about one change against one baseline.
2. Write the plan before you run anything. You cannot run without the hypothesis, the null and the decision rule.
3. Pick the smallest size that answers the question (see "Sizes"). Keep to its script limit. Ask the user before you add more.
4. Do not change `plan.json` after the first run. Record any change as an amendment in its `amendments` list. No tool writes to `plan.json`.
5. Status lives only in `experiment.json`. Never write a status into `plan.json`, `protocol.md` or `report.md`.
6. In a finished or converted experiment, change only `experiment.json`, `protocol.md` and the report file (`report.md`, or `results.md` in an older folder without `report.md`). Never edit its other files. Say what changed and why in the commit message. The web app appends one line to `edits.jsonl` in the experiment folder for each save of `protocol.md` or the report. Never change or remove a line in `edits.jsonl`. A tool may add the git-ignored derived files `analysis.ipynb`, `analysis.marimo.py` and `__marimo__/`. Never commit them.
7. Write only inside the experiment folder. Never touch production data or `.env`.
8. Every number in a report names the `output/` file it came from.
9. Reports open with the Answer box. Write in plain British English, with sentences of 20 words or fewer. Explain each term in the sentence where it first appears.
10. Keep negative and unclear results. Report them honestly.
11. Only `experiments/` has `AGENTS.md` and `CLAUDE.md`. Never add them to an experiment folder.

## Before you start

1. Read the repository `AGENTS.md`. It overrides this skill on code paths and settings.
2. Read `experiments/AGENTS.md`. It holds the folder rules. Read `docs/guides/experiment-records.md` for the full format.
3. If you are resuming, read the experiment's `experiment.json`, `protocol.md`, `plan.json` and `report.md`.
4. Find the project's own entry points: the package name, the function under test and its settings objects. Look in the repository `AGENTS.md` and in earlier experiments. Do not import from a remembered path.
5. Pass settings in as objects (`EffectiveSettings`). Patch env vars or module globals per cell only when there is no other way, and say so in the plan.

## The `omrs experiments` commands

Use these when `omrs` is installed (`uv run --no-sync omrs --help` works). All output goes to stderr.

| Command | Use |
| --- | --- |
| `uv run --no-sync omrs experiments new <slug> --title "<title>" --category <category> --size <size>` | Create a folder, `experiment.json` at `PLANNED`, and the template files for the size |
| `... new <slug> ... --follow-up <number>` | Create a follow-up: `38a`, then `38b` |
| `uv run --no-sync omrs experiments check` | Read-only check. Exit 1 on errors. Add `--strict` to fail on warnings too |
| `uv run --no-sync omrs experiments index --write` | Rebuild the index table in `EXP_README.md` between its markers |

Without `omrs`, do the same steps by hand. Copy the templates from `references/` (see "References"), and write `experiment.json` from the field table below.

## Sizes

Ask the user: "Quick, Standard or Confirmatory?" Recommend one, with a reason.

| Size | Use for | Files | Script limit | Stats level |
| --- | --- | --- | --- | --- |
| Quick | Smoke test, "does it run", a one-off check | `experiment.json`, `report.md` (plan at the top) | 1 | basic |
| Standard | One change against a baseline. Most experiments | `experiment.json`, `protocol.md`, `plan.json`, `report.md` | 3 (run, summarise, analysis) | medium |
| Confirmatory | Repeat an earlier result on new data before a default changes | Standard set, with `protocol.md` and `plan.json` committed before the run | 5 | expert |

The script limit counts the Python files you write in the folder. Tests for those scripts do not count. Shared code in `experiments/_lib/` does not count.

Signs of over-engineering. Stop and simplify if you see one:
- A command-line flag that no step in the plan uses.
- A script that only one other script calls. Merge the two.
- More than one runner for one question.
- A new statistics function. Use the shared statistics module.
- More than three amendments. Ask the user whether this is a new experiment.

## Categories

Each experiment has one category. Record it in `experiment.json`. The folder name does not carry it.

| Category | Covers |
| --- | --- |
| `retrieval` | Embedding, reranker, hybrid search, chunking, thresholds |
| `ingestion` | Readers, OCR routing, fallback chains, normalisation, file-type detection |
| `runtime` | Speed, caches, devices, locks, storage lifecycle |
| `generation` | Answers, citations, faithfulness |
| `graph` | Code and document graphs, communities |
| `review` | Operator labelling and review pages |

If none fits, ask the user. Do not invent a category.

## Folder names and numbers

- Name: `<number>-<slug>-<YYYY-MM-DD>`, for example `43-ocr-text-quality-2026-10-26`. The slug is lower-case letters, digits and single hyphens.
- The folder name is the identity. The number is a label. Old folders can repeat a number; leave them.
- `omrs experiments new` takes the next whole number above every folder number and every number in `experiments/reserved.json`.
- To hold a number for work that has no folder yet, add an entry to the `reservations` list in `reserved.json` (format `omrs-experiment-reservations/1`): `{"number": "44", "reason": "<why>", "ref": "<change, branch or task>"}`. Remove it when the folder exists.
- Never rename or move an old folder.

## The record: `experiment.json`

| Field | Value |
| --- | --- |
| `format` | `omrs-experiment/1` |
| `number` | String: `22`, `5b`, `10.1`, or empty for an unnumbered folder |
| `title` | Short title |
| `date` | The date in the folder name |
| `category` | One of the six categories |
| `size` | `Quick`, `Standard` or `Confirmatory` |
| `status` | One of the seven values below |
| `superseded_by` | Folder name of the newer experiment, only with `SUPERSEDED`; else `null` |
| `finding` | The answer in one line, no line break |
| `refs` | Optional: `{"adrs": [], "changes": [], "tasks": []}` |
| `migration` | Only on converted folders. Never add it to a new record |

Unknown keys are an error. A newer `format` value is refused.

| Status | Meaning |
| --- | --- |
| `PLANNED` | The plan is written. No run has started |
| `ACTIVE` | A run has started, or work is still open |
| `PASS` | The gates passed and the primary hypothesis holds |
| `FAIL` | A gate failed, or the primary hypothesis does not hold |
| `INCONCLUSIVE` | It ran, but did not answer the question |
| `MEASURED` | A measurement with no pass or fail gate |
| `SUPERSEDED` | A later experiment replaces it. `superseded_by` is required |

## Workflow

### Step 1: Scope

Agree four things with the user. Keep each to one line.
1. The question.
2. The decision that depends on the answer.
3. The change and the baseline.
4. The size.

### Step 2: Create the folder and write the plan

1. Run `omrs experiments new` (or copy the templates by hand). Check that `experiment.json` says `PLANNED`.
2. Quick: fill the plan half of `report.md`.
3. Standard and Confirmatory: fill all six sections of `protocol.md`. Fill `plan.json`: `question`, `decision`, `hypotheses`, `decision_rule`, `stats`, `metrics`, `gates` and `frozen`. The `frozen` list records each fixed value, with its input SHA-256 and the git commit. `plan.json` has no `status` key.
4. Confirmatory: commit `protocol.md` and `plan.json` before the first run. That commit is the preregistration.

### Step 3: Write the scripts

Follow `references/eval-runner-pattern.md`. The runner:
- reads the ground truth and stops if it is empty,
- appends a run record when it starts (see Step 4),
- runs each cell on the same items (a paired design),
- saves raw rows per item to `output/`,
- writes a checkpoint after each cell, and supports `--resume`.

Put pure scoring logic in a small module with a `test_*.py` beside it.

### Step 4: Run

1. Set `status` to `ACTIVE` in `experiment.json`.
2. Each run start appends one line to `output/run-records.jsonl`, through the helper in `experiments/_lib/run_record.py`. The line holds the UTC start time, git commit, dirty-tree flag, `plan.json` SHA-256 and the command. Earlier lines never change.
3. Run the commands from the plan. If the run stops, re-run with `--resume`. A resume also appends a run record.
4. The checker warns when a run record's plan SHA-256 differs from the current `plan.json`. That means the plan changed after a run. Record it as an amendment.
5. A save of `protocol.md` or the report from the web app appends one line to `edits.jsonl` in the experiment folder. Git tracks it. Commit it with the edited file. The checker warns (`edit-log-invalid`) when a line does not load.

### Step 5: Summarise

Follow `references/summarise-pattern.md`. The summariser reads `stats`, `metrics` and `gates` from `plan.json` and calls the shared statistics at that level (`references/stats-levels.md`). It writes `output/summary.json` and the tables for `report.md`. It runs only the tests named in the plan. Anything else is labelled exploratory.

### Step 6: Report and close

1. Write `report.md` from the template. Start with the Answer box. Follow `references/writing-guide.md`.
2. Set `status` to `PASS`, `FAIL`, `INCONCLUSIVE` or `MEASURED` in `experiment.json`. Write the one-line `finding`.
3. Write the follow-up in the `Next step` line of the Answer box, or "none".
4. Standard and Confirmatory: write `analysis.py` from `references/analysis-pattern.md`.
5. Add the ADR, OpenSpec change or task the experiment informs to `refs` in `experiment.json`. Link the experiment from that document.
6. Run `omrs experiments index --write`, then `omrs experiments check`. Fix every error.

### Step 7: Keep the data

`output/` is not in git. Before a git worktree is removed, copy each experiment's `output/` to the local data store that the repository `AGENTS.md` names. Record a SHA-256 checksum for each copy and check it before removal. Do not upload `output/` to a public host.

## Statistics module

`references/stats.py` and `references/test_stats.py` hold the paired statistics that the summariser pattern calls (`stats.compare`). In OMRS, `experiments/_lib/stats.py` already exists and holds a different contract (per-query rows and cell records). Do not overwrite it. Ask the user where the paired statistics module goes before you copy it.

## Keep from earlier practice

- Gates and thresholds written before the run, and never moved after it.
- Experiment-local storage under `output/`. Raw JSON saved next to the Markdown.
- Checkpoint and resume.
- One `report.md` per experiment. Old `results.md` and `discussion.md` files stay as they are.
- `analysis.py` in Jupytext percent format. `analysis.ipynb` is gitignored.
- Operator review pages use the Experiment 34 layout (`references/review-page-pattern.md`).

## References

The six `template-*` files are byte-for-byte copies of the templates in `src/omrs/core/experiment_records/templates/`. `tests/unit/test_experiment_skill_drift.py` fails when they differ. Change the package template first, then copy it here.

| File | Package template | Use |
| --- | --- | --- |
| `references/template-protocol.md` | `protocol.md` | Six-section plan for Standard and Confirmatory |
| `references/template-plan.json` | `plan.json` | Frozen machine-readable plan (no `status`) |
| `references/template-report.md` | `report.md` | Report with the Answer box |
| `references/template-report-quick.md` | `report-quick.md` | Quick experiment: plan and report in one file |
| `references/template-experiments-agents.md` | `experiments-agents.md` | `experiments/AGENTS.md` for a new project |
| `references/template-exp-readme.md` | `exp-readme.md` | `EXP_README.md` for a new project, with the index markers |
| `references/writing-guide.md` | none | Report writing rules and optional protocol sections |
| `references/stats-levels.md` | none | Basic, medium and expert statistics, and how to explain them |
| `references/stats.py`, `references/test_stats.py` | none | Paired statistics for the summariser |
| `references/eval-runner-pattern.md` | none | Runner shape |
| `references/summarise-pattern.md` | none | Summariser shape |
| `references/analysis-pattern.md` | none | `analysis.py` shape |
| `references/review-page-pattern.md` | none | Operator review pages |

## Set up `experiments/` in a new project

1. Create `experiments/` and `experiments/_lib/` with an empty `__init__.py`.
2. Copy `references/template-experiments-agents.md` to `experiments/AGENTS.md`.
3. Run `(cd experiments && ln -s AGENTS.md CLAUDE.md)`.
4. Copy `references/template-exp-readme.md` to `experiments/EXP_README.md`.
5. Do not overwrite an existing `AGENTS.md`, `EXP_README.md` or `_lib/` file. Show the user the difference and ask first.
