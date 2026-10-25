# Experiment <number>: <title>

- **Folder**: `<number>-<slug>-<YYYY-MM-DD>`
- **Record**: [experiment.json](experiment.json) holds the category, size and status.
- **Date run**: <YYYY-MM-DD>
- **Operator**: <who ran it>
- **Plan**: [protocol.md](protocol.md) · [plan.json](plan.json)
- **Source of every number**: `output/summary.json` <and other files>

## Answer

- **Question**: <one sentence, as in the plan>
- **Answer**: <Yes | No | Unclear>. <One short reason with the key number.>
- **Decision**: <what we do now, for example "Keep the baseline. Do not change the default.">
- **How sure**: <Low | Medium | High>. <One reason, for example "76 junk pages; the 95% range stays above the limit".>
- **Next step**: <one line, or "none">

## What we tested

<One plain sentence: the change and the baseline. One sentence: the decision it informs. One line: the data (unit, count, source).>

## Results

<One plain sentence on what the table shows.>

| Arm | n | <primary metric> (95% range) | <guardrail metric> | Gate |
| --- | ---: | --- | --- | :---: |
| Baseline | | | | |
| Candidate | | | | |

<One plain sentence per row that matters, written by the summariser at the plan's stats level.>

### Hypotheses

| Hypothesis | Null | Result | Plain meaning |
| --- | --- | --- | --- |
| H1 (primary) | <H0> | <supported or not supported, with the test and value> | <one sentence> |

### Amendments and deviations

<"None", or one line per amendment in plan.json: what changed and why.>

### Exploratory findings

<Anything not in the plan. Label each finding as exploratory. It cannot change the answer.>

## Why it happened

1. <Mechanism: why the candidate won or lost, pointing at the tables.>
2. <Surprises: an honest explanation, or "unexplained".>

## Limits

1. <One sentence each: sample size, saturation, label quality, what this does not prove.>

## What it means for you

<At most three lines. What changes, what does not, what to do next. No new data.>

## Artefacts

| File | Contents |
| --- | --- |
| `output/summary.json` | Aggregated metrics, statistics and gates |
| `output/<raw>.json` | Raw per-item results |
| `output/run-records.jsonl` | One line per run start: time, git commit, plan SHA-256 |
| `analysis.py` | Tables and plots from the JSON |
