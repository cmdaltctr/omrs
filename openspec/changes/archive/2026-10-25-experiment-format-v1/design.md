# Design

## Context

See proposal.md for the problem. Facts that shape the approach:

- `experiments/` holds 50 experiment folders: 49 start with a number, and `leiden-vs-louvain-2026-08-14` has none. `_lib/`, `ARCHIVED/` and `example/` are not experiments.
- 18 folders have a `plan.json`. Their keys differ, and 7 have no `status`. `experiments/_lib/checkpoint_validity.py` hashes `plan.json` into each run's identity, so any write to `plan.json` breaks resume checks.
- The `EXP_README.md` index has 45 rows with five columns: `#`, `Experiment`, `Date`, `Status`, `Key Finding / Purpose`. Status values in it: `PASS` 21, `FAIL` 12, `PARTIAL` 3, `REBUILT` 3, `COMPLETE` 2, `SUPERSEDED` 2, `INCONCLUSIVE` 1, `PLANNED` 1.
- `omrs.core.experiments` already exists. It holds the approved *experiment contexts* that sandbox notebook runs (design D10 of the web workspace). That is a different thing from a research experiment record.
- The wheel excludes every file named `AGENTS.md` or `CLAUDE.md` at any depth (`pyproject.toml`, `[tool.hatch.build.targets.wheel] exclude`).
- `pydantic` is a core dependency. `jsonschema` is in the lock file only as a dependency of `mcp`. It is not a declared dependency.
- No file under `src/omrs/` may exceed 500 lines.

## Goals / Non-Goals

**Goals:**

- One record model that the CLI, the later web change and the skill all follow.
- A move of the old folders that adds files only, can be audited, and keeps the original status text.
- A format that can grow: a version string in every file, and readers that refuse versions they do not know.

**Non-Goals:**

- Rewrite old protocols, plans or reports to the new templates.
- Prove that a plan was committed before its run. That needs git history and belongs to the web change. This change records the data (run records) that such a check needs.
- Support other projects such as OMMS. The format is general, but only the OMRS `experiments/` folder is moved now.

## Decisions

### D1. A separate package: `omrs.core.experiment_records`

Records live in a new package, not inside `omrs.core.experiments`.

- Why: `core.experiments` means sandbox contexts. Putting records there would join two ideas with the same word. The later web change will connect them on purpose, through a context that points at a record folder.
- Alternative: `core.experiments.records`. Rejected: the parent package's import contract and docstring describe sandbox rules, and the two would change for different reasons.
- The package is pure: it reads and writes files under a directory it is given. It imports no web framework, no `subprocess` and no store. An import-linter contract enforces this. Git facts for run records come from the caller.

Planned modules, each under 500 lines:

| Module | Contents |
|---|---|
| `record.py` | `ExperimentRecord` pydantic model, `Status`, `Category`, `Size`, `MigrationNote`, `Refs`, load and dump helpers, format constants |
| `naming.py` | folder name pattern, number parsing and natural sort, slug rules |
| `scan.py` | detect experiment folders, load records, list top-level `output/` names |
| `check.py` | `Finding` model and the checker rules |
| `index.py` | render the table, read and replace the marked block |
| `reserved.py` | `reserved.json` model and loader |
| `scaffold.py` | next number, follow-up letter, create a folder from templates |
| `run_record.py` | `RunRecord` model and an append function that takes git facts as arguments |
| `templates.py` | read the packaged templates through `importlib.resources` |

### D2. pydantic is the source of the rules; the JSON Schema is generated

`ExperimentRecord.model_json_schema()` produces the schema. The shipped file `schema/experiment.v1.schema.json` is that output, written with sorted keys. A test fails when the file and the generated schema differ.

- Why: one source of truth, no new dependency, and external tools (editors, other languages) still get a standard schema.
- Alternative: write the schema by hand and validate with `jsonschema`. Rejected: it adds a declared core dependency and creates two sources of truth.
- `model_config = ConfigDict(extra="forbid", frozen=True)` makes unknown keys an error.
- A model validator holds the cross-field rules: `superseded_by` if and only if `SUPERSEDED`; category and size required unless `migration` is set.

### D3. Record fields

```json
{
  "format": "omrs-experiment/1",
  "number": "22",
  "title": "Raw-query Qwen3-Embedding-4B baseline",
  "date": "2026-09-07",
  "category": "retrieval",
  "size": "Standard",
  "status": "MEASURED",
  "superseded_by": null,
  "finding": "One line, no newline.",
  "refs": {"adrs": [], "changes": [], "tasks": []},
  "migration": {"from_status": "COMPLETE (measurement)", "source": "EXP_README.md", "date": "2026-10-25"}
}
```

- `number` is a string, so `5b` and `10.1` need no special type. Empty string means unnumbered.
- `date` is the date in the folder name (the day the experiment was planned).
- `refs` and `migration` are optional. `refs` gives the later web change its links to ADRs, OpenSpec changes and NiftyPM tasks, without free text parsing.
- Status lives here and nowhere else in new experiments. New `plan.json` files carry no `status` key.

### D4. Readers refuse unknown format versions

`format` must equal `omrs-experiment/1`. Another value raises a dedicated error that names the version. A later release adds `/2` with a converter. This is simpler and safer than "ignore what you do not know", which would let an old release drop a field when it writes.

### D5. The folder name is the identity; the number is a label

Old folders repeat `19` and `9a`. Identity by number would merge them. The folder name is unique in a directory, so it is the key. The checker treats a repeated number as an error only when neither folder carries a migration note.

Natural sort: split the number into the whole part, the letter, and the dotted part, then sort `5 < 5b < 6 < 10 < 10.1 < 10b`. Unnumbered folders come last, ordered by name.

### D6. Index table between markers, written without column padding

`index.py` replaces only the lines between `<!-- omrs:experiment-index:start -->` and `<!-- omrs:experiment-index:end -->`. Cells are not padded, so a new row changes one line and diffs stay small. `|` in a cell becomes `\|`, and line breaks are refused by the record model. After the experiment table, the block holds a `### Reserved numbers` table (`#`, `Reason`, `Reference`) built from `reserved.json`. Today the index has a hand-written row for experiment 35, which has no folder. Without this table, that row would disappear. The heading and table are left out when nothing is reserved. The "Standalone Benchmarks" and "Cross-References" tables stay hand-written.

### D7. Reserved numbers in a tracked file

`experiments/reserved.json` (`omrs-experiment-reservations/1`) lists `{number, reason, ref}`. It is tracked in git, so a reservation made in one worktree reaches the others on merge. The move seeds three entries: 35 (OpenSpec change `experiment-35-full-document-rag-benchmark`), 40 (NiftyPM task AIE-101), 41 (branch `feat/experiment-41-mlx-ocr-backends`).

- Alternative: scan other worktrees and branches with git. Rejected for this change: it needs `subprocess`, and reservations in NiftyPM would still be missed.

### D8. Run records as JSON Lines in `output/`

`output/run-records.jsonl` gets one line per run start. A runner written for format v1 calls the helper at each start, including `--resume`. Runners in converted folders do not call it, because their files are frozen records, so those folders can have no run records. JSON Lines is append-only, so resume runs never rewrite history. The file sits in the gitignored `output/`, next to the data it describes, and is copied with it to `DATA/omrs` under gotcha 15. `experiments/_lib/run_record.py` reads git facts with `git rev-parse HEAD` and `git status --porcelain`, then calls the core append function.

### D9. Templates ship in the package; the skill keeps a byte copy

`src/omrs/core/experiment_records/templates/` holds `protocol.md`, `report.md`, `report-quick.md`, `plan.json`, `experiments-agents.md` and `exp-readme.md`. `experiments-agents.md` is not named `AGENTS.md`, because the wheel excludes that name. The repository skill keeps copies under `.agents/skills/s-experiment/references/`. `tests/unit/test_experiment_skill_drift.py` holds an explicit file map and compares bytes. The skill's other reference files (statistics levels, runner patterns, writing style) are method, not format, and are not compared.

The personal copy in `~/.agents/skills/s-experiment/` is outside the repository. CI cannot see it, and the test does not read it.

### D10. CLI group `omrs experiments`

`src/omrs/transports/cli/experiments.py` adds a Typer sub-app (`app.add_typer(experiments_app, name="experiments")`, as `config.py` does) with three commands. All output goes to stderr (gotcha 5), including `--json` output, which uses `typer.echo(..., err=True)` as `list.py` does.

| Command | Effect |
|---|---|
| `omrs experiments check [DIR] [--strict] [--json]` | Read-only. Exit 1 on errors (and warnings with `--strict`). |
| `omrs experiments index [DIR] [--write]` | Without `--write`, print the table and exit 1 when the file is stale. With `--write`, replace the marked block. |
| `omrs experiments new SLUG --title T --category C --size S [--follow-up N] [--date D] [DIR]` | Create a folder, print its path. |

`DIR` defaults to `./experiments`.

### D11. The move is a one-off script in the change folder

`openspec/changes/experiment-format-v1/migration/convert.py` builds each `experiment.json` from the folder name and the index row, and writes `migration/report.md` listing every judgement it made. It does not ship and is archived with the change. There is no `omrs experiments migrate` command, so no migration code stays in the product.

Status mapping (original text kept in `migration.from_status`):

| Index value | New status | Reason |
|---|---|---|
| `PASS…`, `FAIL…`, `INCONCLUSIVE…`, `PLANNED…`, `SUPERSEDED…` | same word | Same meaning |
| `COMPLETE (measurement)` | `MEASURED` | No gate was set |
| `COMPLETE` with a stated verdict | that verdict | The text decides |
| `PARTIAL…` | `INCONCLUSIVE` | It ran, but did not answer the question |
| `REBUILT…` | `ACTIVE` | Work is still open |
| no index row | the status line in `report.md` or `results.md`, else `INCONCLUSIVE` | Listed in the move report for review |

`SUPERSEDED` rows need `superseded_by`. The script takes the target from a fixed table in the script, each entry backed by text in the folders. Today two rows say "SUPERSEDED D17", and the D17 factorial runs in `10b-reranker-pool-size-corrected-2026-06-29` (its `protocol.md` line 1). When a `SUPERSEDED` row has no entry, the script stops and lists the row. It never guesses.

Category and size: the script infers category from the folder title with a fixed keyword table, and leaves it empty when no keyword matches. Size is `Standard` when the folder has `protocol.md` and `plan.json`, `Quick` when it has neither, and empty otherwise. Every inferred value is listed in the move report.

Title and finding come from the index row text, unchanged. A folder without a row gets its title from the first heading of `report.md`, `results.md`, `README.md` or `protocol.md`, in that order.

## Risks / Trade-offs

- [The move assigns a status by rule, and a rule can be wrong for one experiment] → The original text stays in `migration.from_status`, and the move report lists every non-trivial mapping for the user to review. A wrong status is a one-line fix.
- [Category inference by keyword can be wrong] → Empty is allowed on converted records. Every inferred value is in the move report.
- [The regenerated index changes many lines because padding goes away] → One large, mechanical diff now. Later diffs are one line per experiment.
- [Two copies of the templates] → The drift test fails on any difference in the repository copy. The personal copy is the user's to keep in step.
- [A future field needs a new format version] → D4 makes the version explicit, so old releases refuse new files instead of damaging them.
- [`report.md` status lines are free text] → The checker reads only a `Status` line in the header block. A missed line yields no finding, never a wrong error.

## Migration Plan

1. Back up the tracked files of `experiments/` to `DATA/omrs/backups/experiments-pre-format-v1-2026-10-25/` with a SHA-256 receipt. (Done before this change was written.)
2. Merge the core package and CLI first, with tests.
3. Run `migration/convert.py`. Review `migration/report.md`. Fix the listed items.
4. Add the index markers around the existing table, then run `omrs experiments index --write`.
5. Run `omrs experiments check`. It must report no errors.

Rollback: revert the commits. The backup holds the tracked state at `9bf671b3`. No data outside git changes.
