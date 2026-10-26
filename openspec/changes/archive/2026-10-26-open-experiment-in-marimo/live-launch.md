# Live marimo launch (task 10.4, design risk 5)

Date: 2026-10-26. Real marimo 0.25.1 from `uv tool` (`~/.local/bin/marimo`, Python 3.14), opened from the scratch server of `browser-check.md`. No test executable was used here.

`<worktree>` is this worktree. `<scratch>` is a folder in the session scratchpad.

## Environment before the open

| Item | Value |
| --- | --- |
| Project `.venv` | `<worktree>/.venv`, Python 3.14 (`version_info = 3.14` in `pyvenv.cfg`), no marimo, numpy 2.5.2 |
| marimo tool environment | marimo 0.25.1, no jupytext |
| `uv pip list --python .venv/bin/python` | 196 lines, saved to `<scratch>/pip-before.txt` |
| `git status --short` | empty |
| `<worktree>/.env` | absent (so a second, scratch project checks `.env`; see below) |

## Conversion

jupytext is not in marimo's tool environment, and OMRS installs nothing. So conversion was checked through its refusal:

- Open of experiment 34 (has `analysis.py`): 409 `converter_missing`. The page line names `uv tool install "marimo>=0.25.1,<0.26" --with jupytext`.
- `ls experiments/34-*/ | grep marimo` gives nothing, and `<scratch>/ws/run/convert/` is empty.
- Run by hand, `marimo convert analysis.py -o out.py` prints `Error: Converting py:percent format requires jupytext`. That is the text the server matches.
- A successful conversion is covered by the fake-executable tests only (`test_open_converts_once_returns_the_token_once_and_logs_no_token`, `tests/unit/test_workspace_experiment_editor_notebook.py`).

## Launch of this repository's experiment 14 (no `analysis.py`)

| # | Item | Result |
| --- | --- | --- |
| 1 | The open returns 201 `created`. marimo opens `experiments/14-liteparse-qasper-promotion-2026-06-29/analysis.marimo.py` on `127.0.0.1:2719` | Pass |
| 2 | Argv: `marimo edit <notebook> --headless --host 127.0.0.1 --port 2719 --token-password-file <launch folder>/access-token --skip-update-check --no-sandbox`. The token is in no argv (`ps`) and not in the server log (`grep -c` gives 0) | Pass |
| 3 | The private `.marimo.toml` (0600, in a 0700 launch folder) holds `[venv] path = "<worktree>/.venv"`, `writable = false`, `auto_instantiate = false` and `on_cell_change = "lazy"` | Pass |
| 4 | No cell ran on open: after sign-in, the code cells show the not-run state and the `experiment` cell has no output. Only the Markdown cell shows its text | Pass |
| 5 | The kernel process is `<worktree>/.venv/bin/python -m marimo._ipc.launch_kernel` | Pass |
| 6 | A new cell `import os, sys, numpy, omrs` runs. It returns `executable = <worktree>/.venv/bin/python`, `numpy = 2.5.2` and `omrs` from `<worktree>/src/omrs/__init__.py`. Running it did not run any other cell (lazy) | Pass |
| 7 | No `*_API_KEY` variable is in the kernel's `os.environ` | Pass |
| 8 | `git status --short` is empty after the open. `git status --ignored` lists only `analysis.marimo.py` and `__marimo__/` in the folder | Pass |
| 9 | Stop (Confirm stop on the page) ends the editor and the kernel (`ps` finds neither), and the launch folder is removed (`ls <scratch>/ws/run/editors` is empty) | Pass |
| 10 | `uv pip list --python .venv/bin/python` after Stop is identical to before (`diff` is empty, 196 lines) | Pass |

## `.env` check (scratch project)

This worktree has no `.env`, so a scratch project tested the rule. The project held a copy of experiment 14 without `analysis.py`, a `.venv` link to `<worktree>/.venv`, a minimal `pyproject.toml` and `.env` with one sentinel line, `OMRS_LIVECHECK_SENTINEL=dotenv-was-loaded`. That is not a real key. A cell printed `os.environ.get("OMRS_LIVECHECK_SENTINEL")`.

| Run | Private config | Sentinel in the kernel | Result |
| --- | --- | --- | --- |
| 1 (code as first built) | `[runtime] dotenv = []` | `"dotenv-was-loaded"` | **Fail**: marimo loaded the project `.env` |
| 2 (after the fix) | `[runtime] dotenv = ["<launch folder>/omrs-no-dotenv.env"]`, an empty 0600 file | `None` | Pass |

Cause of run 1: marimo 0.25.1 drops an empty user-layer list (`_drop_hollow_dotenv`, `marimo/_config/manager.py:670-679`). marimo 0.18 and earlier saved masked empty lists to disk, so marimo now reads `[]` as hidden, not as a choice. The project layer then gives its default, `<project>/.env`. Design D2 evidence 6 had read only the default path, so it missed this.

Fix (test-first): `build_launch_plan` with a kernel environment now writes an empty private file `omrs-no-dotenv.env` into the launch folder. `runtime.dotenv` names only that file, and a non-empty list survives the filter. The updated tests in `tests/unit/test_plugin_editor.py`, `tests/unit/test_process_launcher_editor.py` and `tests/unit/test_web_experiment_editor.py` failed on the old code and pass now. Design D2, ADR-099 and the notebooks guide say why `[]` is not used.

In run 2 the first output on screen was the session marimo had saved from run 1 (`__marimo__/session`). The cell was run again, and the fresh output is the one recorded. Stop from the Code editor list then ended that editor and removed its launch folder.

## Clean-up

- The scratch server and both marimo launches were stopped. `ps` finds no `marimo edit` or kernel process.
- The two Orca tabs were closed.
- The derived `analysis.marimo.py` and `__marimo__/` that this check made in experiment 14 were deleted. They were git-ignored.
