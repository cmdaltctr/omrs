# ADR-097: Experiment Records Use a Versioned Format Shipped in omrs

- **Date:** 2026-10-25
- **Status:** Accepted
- **Deciders:** Maintainer
- **Related:** `openspec/specs/experiment-validity-gates/` (run identity and manifests), `openspec/specs/workspace-experiments/` (sandbox experiment contexts)
- **Change:** `openspec/changes/experiment-format-v1/` (design D1 to D11)

## Context

`experiments/` holds about 50 experiment folders. No written format exists
that a program can read. Only a personal agent skill described the layout,
and most folders do not follow it. A read-only check on 2026-10-25 found:

- Status is in up to four places: `plan.json`, `protocol.md`, the report
  and the `EXP_README.md` index. The values often disagree. Experiment 25
  says `PLANNED` in its plan and `PASS` in the index.
- Status uses values with no defined meaning: `COMPLETE`, `PARTIAL`,
  `REBUILT`, `FROZEN` and free sentences.
- The index has 45 rows for 51 numbered folders.
- Two numbers are used twice (`19`, `9a`). Reserved numbers are known only
  from OpenSpec, a task tracker and a branch name.

`plan.json` cannot hold the status. `experiments/_lib/checkpoint_validity.py`
puts the SHA-256 of `plan.json` into each run's identity. A status update in
`plan.json` therefore breaks every resume check for that experiment.

The web workspace will show and create experiments in a later change. It
needs a stable format first.

## Decision

1. **One record file per experiment.** Each folder gets `experiment.json`
   with `format: "omrs-experiment/1"`. It holds the facts that change after
   planning or that the index needs: number, title, date, category, size,
   status, `superseded_by`, a one-line finding, optional `refs` and an
   optional `migration` note.
2. **Status lives only in the record.** Seven values: `PLANNED`, `ACTIVE`,
   `PASS`, `FAIL`, `INCONCLUSIVE`, `MEASURED` (a measurement with no gate)
   and `SUPERSEDED` (which needs `superseded_by`). New `plan.json` files
   carry no `status` key. `plan.json` is frozen after the first run, and no
   tool writes to it.
3. **The format ships in the `omrs` package.** `omrs.core.experiment_records`
   holds a pydantic model, a JSON Schema generated from that model, the
   templates, a checker, an index renderer and a folder creator. The package
   is pure: it reads and writes files under a directory it is given, and an
   import-linter contract keeps `subprocess`, web frameworks and stores out.
4. **Readers refuse unknown versions.** A record with another `format`
   value fails with an error that names the version. A later format adds
   `/2` with a converter.
5. **The folder name is the identity.** Folders are named
   `<number>-<slug>-<YYYY-MM-DD>`. The number is a label and can repeat in
   old folders. `experiments/reserved.json` lists reserved numbers, and the
   folder creator skips them.
6. **Runs append run records.** Each run start appends one line to
   `output/run-records.jsonl`: UTC start time, git commit, dirty-tree flag,
   `plan.json` SHA-256 and the command. The checker warns when a run's plan
   hash differs from the current plan.
7. **The index is generated.** `omrs experiments index --write` replaces
   only the lines between two marker comments in `EXP_README.md`.
8. **The old folders move once, by a script that does not ship.** The
   script lives in the change folder and adds `experiment.json` files only.
   It keeps the original status text in `migration.from_status`.
9. **The repository keeps its own skill copy.** `.agents/skills/s-experiment/`
   carries byte copies of the package templates. A test fails when they
   differ.

## Consequences

### Positive

- One place to read and change an experiment's status.
- Resume checks stay valid, because status updates never touch `plan.json`.
- The CLI, the later web change and the skill all follow one model.
- External tools get a standard JSON Schema with no new dependency.
- A plan changed after a run is detectable from the run records.
- New index rows change one line each, so diffs stay small.

### Negative

- Two copies of the templates exist (package and skill). The drift test
  covers the repository copy only. A personal copy outside the repository
  must be kept in step by hand.
- The move assigns old statuses by rule. A rule can be wrong for one
  experiment. The original text stays in the migration note, and each
  non-trivial mapping is listed in the move report.
- The first regenerated index is one large mechanical diff, because column
  padding goes away.

### Neutral

- Old protocols, plans and reports keep their content. Old `plan.json`
  files can still carry a `status` key; the record value wins.
- Run records sit in the gitignored `output/` folder and are preserved with
  it before a worktree is removed.
- The format does not prove that a plan was committed before its run. That
  needs git history and belongs to the web change.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Write the JSON Schema by hand and validate with `jsonschema`** (design D2) | It adds a declared core dependency, and the schema and the code become two sources of truth that can drift. |
| **Keep status in `plan.json`** (design D3) | `plan.json` is hashed into each run's identity. Any status write breaks resume checks, and the plan would no longer be a frozen record of intent. |
| **Ship an `omrs experiments migrate` command** (design D11) | The move runs once. A command would keep migration code in the product for every later release. A script in the change folder is archived with the change. |
| **Put records in `omrs.core.experiments`** (design D1) | That package holds sandbox experiment contexts, a different idea with its own import rules. |
| **Find reserved numbers by scanning git branches and worktrees** (design D7) | It needs `subprocess` in a pure package, and reservations held in a task tracker would still be missed. |
| **Ignore unknown keys and versions** (design D4) | An old release would drop a field it does not know when it writes the file back. |

## References

- `src/omrs/core/experiment_records/` (model, schema, templates, checker, index, folder creator)
- `src/omrs/transports/cli/experiments.py` (`omrs experiments check | index | new`)
- `experiments/AGENTS.md`, `experiments/reserved.json`, `experiments/_lib/run_record.py`
- `.agents/skills/s-experiment/` and `tests/unit/test_experiment_skill_drift.py`
- [Experiment records guide](../guides/experiment-records.md)
