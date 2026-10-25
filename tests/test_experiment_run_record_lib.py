"""``experiments/_lib/run_record.py`` reads git facts (experiment-format-v1, task 3.5).

The core append function takes git facts as arguments. This helper reads
them with ``git`` and passes them on. The test builds a temporary git
repository, so it never depends on the state of this checkout.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from experiments._lib.run_record import record_run_start


def _git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    result = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    _git(tmp_path, "init", "-q")
    folder = tmp_path / "experiments" / "43-ocr-text-quality-2026-10-26"
    folder.mkdir(parents=True)
    (folder / "plan.json").write_text('{"hypothesis": "x"}\n', encoding="utf-8")
    (tmp_path / ".gitignore").write_text("output/\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "--no-verify", "-m", "start")
    return tmp_path


def _lines(folder: Path) -> list[dict[str, object]]:
    text = (folder / "output" / "run-records.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def test_clean_tree_records_commit_and_plan_hash(repo: Path) -> None:
    folder = repo / "experiments" / "43-ocr-text-quality-2026-10-26"
    record = record_run_start(folder, command="uv run python run_eval.py")
    assert record.git_commit == _git(repo, "rev-parse", "HEAD")
    assert record.git_dirty is False
    assert len(record.plan_sha256) == 64
    (line,) = _lines(folder)
    assert line["git_commit"] == record.git_commit
    assert line["command"] == "uv run python run_eval.py"


def test_uncommitted_change_sets_dirty_flag(repo: Path) -> None:
    folder = repo / "experiments" / "43-ocr-text-quality-2026-10-26"
    (folder / "plan.json").write_text('{"hypothesis": "changed"}\n', encoding="utf-8")
    record = record_run_start(folder, command="resume")
    assert record.git_dirty is True


def test_command_defaults_to_the_process_arguments(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = repo / "experiments" / "43-ocr-text-quality-2026-10-26"
    monkeypatch.setattr("sys.argv", ["run_eval.py", "--resume", "two words"])
    record = record_run_start(folder)
    assert record.command == "run_eval.py --resume 'two words'"


def test_folder_outside_a_repository_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()
    with pytest.raises(RuntimeError, match="git"):
        record_run_start(folder, command="x")
    assert not (folder / "output").exists()
