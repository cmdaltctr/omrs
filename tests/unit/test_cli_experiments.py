"""``omrs experiments check|index|new`` (experiment-format-v1, task 6.1, design D10).

Every command prints to stderr only, including ``--json`` output (gotcha 5:
stdout is the MCP protocol channel). The commands need no engine, so the
runtime is never built for them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from omrs.core.experiment_records.index import INDEX_END, INDEX_START, render_index
from omrs.core.experiment_records.reserved import load_reservations
from omrs.core.experiment_records.scan import scan_experiments
from omrs.transports.cli import app as cli_app

runner = CliRunner()

_GOOD = "1-good-2026-05-12"


def _record(name: str, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "omrs-experiment/1",
        "number": name.partition("-")[0],
        "title": "Good experiment",
        "date": name[-10:],
        "category": "retrieval",
        "size": "Quick",
        "status": "PASS",
        "superseded_by": None,
        "finding": "Found.",
    }
    data.update(overrides)
    return data


def _make(root: Path, name: str, **overrides: Any) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "experiment.json").write_text(
        json.dumps(_record(name, **overrides)), encoding="utf-8"
    )
    (folder / "report.md").write_text("# Report\n", encoding="utf-8")
    return folder


def _sync(root: Path) -> None:
    block = render_index(scan_experiments(root), load_reservations(root))
    (root / "EXP_README.md").write_text(
        f"# E\n{INDEX_START}\n{block}{INDEX_END}\n", encoding="utf-8"
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "experiments"
    _make(path, _GOOD)
    _sync(path)
    return path


@pytest.fixture(autouse=True)
def _no_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a command builds the engine."""

    def refuse() -> None:
        raise RuntimeError("the experiments commands must not build the engine")

    monkeypatch.setattr("omrs.compose.ensure_runtime_setup", refuse)


def _run(*args: str) -> Any:
    return runner.invoke(cli_app, ["experiments", *args])


def test_check_clean_directory_exits_zero(root: Path) -> None:
    result = _run("check", str(root))
    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    assert "No problems" in result.stderr


def test_check_error_exits_one(root: Path) -> None:
    (root / "2-bare-2026-05-12").mkdir()
    result = _run("check", str(root))
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "record-missing" in result.stderr
    assert "2-bare-2026-05-12" in result.stderr


def test_check_warning_fails_only_in_strict_mode(root: Path) -> None:
    _make(root, "2-std-2026-05-12", size="Standard")
    _sync(root)
    assert _run("check", str(root)).exit_code == 0
    result = _run("check", str(root), "--strict")
    assert result.exit_code == 1
    assert "files-missing" in result.stderr


def test_check_json_goes_to_stderr(root: Path) -> None:
    (root / "2-bare-2026-05-12").mkdir()
    result = _run("check", str(root), "--json")
    assert result.exit_code == 1
    assert result.stdout == ""
    findings = json.loads(result.stderr)
    assert findings == [
        {
            "severity": "error",
            "code": "record-missing",
            "folder": "2-bare-2026-05-12",
            "message": findings[0]["message"],
        }
    ]


def test_check_json_clean_is_an_empty_list(root: Path) -> None:
    result = _run("check", str(root), "--json")
    assert result.exit_code == 0
    assert json.loads(result.stderr) == []


def test_check_missing_directory_exits_one(tmp_path: Path) -> None:
    result = _run("check", str(tmp_path / "missing"))
    assert result.exit_code == 1
    assert "not a directory" in result.stderr


def test_check_defaults_to_experiments_folder(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(root.parent)
    assert _run("check").exit_code == 0


def test_index_current_exits_zero(root: Path) -> None:
    result = _run("index", str(root))
    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    assert "[Good experiment](./1-good-2026-05-12/)" in result.stderr
    assert "up to date" in result.stderr


def test_index_stale_exits_one_and_writes_nothing(root: Path) -> None:
    _make(root, "2-later-2026-05-13")
    before = (root / "EXP_README.md").read_bytes()
    result = _run("index", str(root))
    assert result.exit_code == 1
    assert "2-later-2026-05-13" in result.stderr
    assert "--write" in result.stderr
    assert (root / "EXP_README.md").read_bytes() == before


def test_index_write_replaces_the_block(root: Path) -> None:
    _make(root, "2-later-2026-05-13")
    result = _run("index", str(root), "--write")
    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    assert "2-later-2026-05-13" in (root / "EXP_README.md").read_text(encoding="utf-8")
    assert _run("index", str(root)).exit_code == 0


def test_index_write_without_markers_exits_one(root: Path) -> None:
    (root / "EXP_README.md").write_text("# E\n", encoding="utf-8")
    result = _run("index", str(root), "--write")
    assert result.exit_code == 1
    assert INDEX_START in result.stderr
    assert (root / "EXP_README.md").read_text(encoding="utf-8") == "# E\n"


def test_index_without_readme_exits_one(root: Path) -> None:
    (root / "EXP_README.md").unlink()
    result = _run("index", str(root), "--write")
    assert result.exit_code == 1
    assert "EXP_README.md" in result.stderr


def _new(root: Path, *extra: str) -> Any:
    return _run(
        "new",
        "ocr-text-quality",
        str(root),
        "--title",
        "OCR text quality",
        "--category",
        "ingestion",
        "--size",
        "Standard",
        "--date",
        "2026-10-26",
        *extra,
    )


def test_new_creates_folder_and_prints_path(root: Path) -> None:
    result = _new(root)
    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    folder = root / "2-ocr-text-quality-2026-10-26"
    assert (folder / "experiment.json").is_file()
    assert (folder / "plan.json").is_file()
    assert str(folder) in result.stderr.replace("\n", "")


def test_new_follow_up(root: Path) -> None:
    result = _new(root, "--follow-up", "1")
    assert result.exit_code == 0, result.stderr
    assert (root / "1a-ocr-text-quality-2026-10-26").is_dir()


def test_new_bad_slug_exits_one(root: Path) -> None:
    result = _run(
        "new", "Bad Slug", str(root), "--title", "T", "--category", "ingestion", "--size", "Quick"
    )
    assert result.exit_code == 1
    assert "slug" in result.stderr
    assert sorted(p.name for p in root.iterdir()) == [_GOOD, "EXP_README.md"]


def test_new_bad_date_exits_one(root: Path) -> None:
    result = _new(root, "--date", "2026-02-30")
    assert result.exit_code == 1
    assert "date" in result.stderr


def test_new_unknown_category_is_a_usage_error(root: Path) -> None:
    result = _run(
        "new", "ocr", str(root), "--title", "T", "--category", "chunking", "--size", "Quick"
    )
    assert result.exit_code == 2


@pytest.mark.parametrize("write", [False, True])
def test_index_non_utf8_readme_exits_one(root: Path, write: bool) -> None:
    (root / "EXP_README.md").write_bytes(b"# E\n\xff\n")
    result = _run("index", str(root), *(["--write"] if write else []))
    assert result.exit_code == 1
    assert "UTF-8" in result.stderr
    assert "Traceback" not in result.stderr
    assert (root / "EXP_README.md").read_bytes() == b"# E\n\xff\n"
