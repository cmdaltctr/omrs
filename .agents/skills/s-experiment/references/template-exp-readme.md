# Experiments

Each experiment answers one question about the system. Rules for agents are in [AGENTS.md](AGENTS.md).

## How to add an experiment

1. Run `uv run --no-sync omrs experiments new <slug> --title "<title>" --category <category> --size <size>`.
2. Write the plan in `protocol.md` and `plan.json`, or at the top of `report.md` for a Quick experiment.
3. Run the experiment. Each run appends a line to `output/run-records.jsonl`.
4. Write `report.md`. Set `status` and `finding` in `experiment.json`.
5. Run `uv run --no-sync omrs experiments index --write` to rebuild the index.
6. Run `uv run --no-sync omrs experiments check` and fix every error.

## Conventions

| Convention | Rule |
| --- | --- |
| **Naming** | `<number>-<slug>-<YYYY-MM-DD>`. The folder name is the identity. |
| **Record** | `experiment.json` (`omrs-experiment/1`) holds category, size, status and the finding. |
| **Status** | `PLANNED`, `ACTIVE`, `PASS`, `FAIL`, `INCONCLUSIVE`, `MEASURED` or `SUPERSEDED` (with `superseded_by`). |
| **Reserved numbers** | `reserved.json` lists numbers that have no folder yet. |
| **Plan** | `plan.json` is frozen after the first run. Changes go in its `amendments` list. |
| **Raw data** | Save machine-readable results (JSON) in `output/` next to the Markdown report. |

## Index

The table below is generated from the `experiment.json` files. Do not edit it by hand.

<!-- omrs:experiment-index:start -->
| # | Experiment | Date | Status | Key Finding / Purpose |
|---|---|---|---|---|
<!-- omrs:experiment-index:end -->
