"""Derived notebook files in an experiment folder are ignored by git (design D1).

The Library writes ``analysis.marimo.py`` beside ``analysis.py``, and marimo
writes its session cache below ``__marimo__/``. Both are derived files, so
this repository's ``.gitignore`` must ignore them in every experiment folder.
The test asks git itself, so it checks the real ignore rules.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_EXPERIMENTS = _REPO / "experiments"


def _experiment_folder() -> str:
    """Return the name of a real numbered experiment folder."""
    folders = sorted(p.name for p in _EXPERIMENTS.iterdir() if p.is_dir() and p.name[:1].isdigit())
    assert folders, "no numbered experiment folder exists, so this test checks nothing"
    return folders[0]


def _git_ignored(paths: list[str]) -> set[str]:
    """Return the subset of ``paths`` that git reports as ignored."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not installed")
    inside = subprocess.run(
        [git, "rev-parse", "--is-inside-work-tree"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git checkout")
    # --no-index also checks paths that are not in the index.
    result = subprocess.run(
        [git, "check-ignore", "--no-index", "--", *paths],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    return set(result.stdout.splitlines())


@pytest.mark.parametrize(
    "relative",
    ["analysis.marimo.py", "__marimo__/session/x.json", "analysis.ipynb"],
)
def test_derived_file_is_ignored(relative: str) -> None:
    path = f"experiments/{_experiment_folder()}/{relative}"
    assert _git_ignored([path]) == {path}, f"git does not ignore {path}"


def test_analysis_source_is_not_ignored() -> None:
    """Guard against an ignore rule so wide that it hides the tracked source."""
    path = f"experiments/{_experiment_folder()}/analysis.py"
    assert _git_ignored([path]) == set()
