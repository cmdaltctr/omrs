## MODIFIED Requirements

### Requirement: The experiments folder guide stands alone

`experiments/AGENTS.md` SHALL state the rules for experiment folders in the repository, including the record file, the seven status values, naming, reserved numbers, run records and the commands to check and index. It SHALL state that a finished or converted experiment changes only `experiment.json`, and that a tool may add only the git-ignored derived files `analysis.ipynb`, `analysis.marimo.py` and `__marimo__/` to it. It SHALL NOT link to files outside the repository. `experiments/CLAUDE.md` SHALL be a link to it.

#### Scenario: Guide links stay inside the repository

- **WHEN** the links in `experiments/AGENTS.md` are resolved
- **THEN** each one points to a path inside the repository

#### Scenario: Derived notebook files are ignored by git

- **WHEN** `git check-ignore` runs in this repository for `analysis.marimo.py` and `__marimo__/session/x.json` inside an experiment folder
- **THEN** git reports both paths as ignored
