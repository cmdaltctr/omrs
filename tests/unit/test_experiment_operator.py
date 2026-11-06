"""The Operator line of a new experiment (change cuts-follow-ups, D4).

``omrs experiments new --operator TEXT`` writes TEXT into the Operator line of
every template file it creates. Without it the placeholder stays. The checker
reports ``operator-placeholder`` (a warning) for a ``report.md`` or
``protocol.md`` whose Operator line still holds a placeholder in angle brackets.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from omrs.core.experiment_records.check import check_experiments
from omrs.core.experiment_records.record import Category, Size
from omrs.core.experiment_records.scaffold import ScaffoldError, create_experiment
from omrs.transports.cli import app as cli_app

runner = CliRunner()
OPERATOR = "OMRS maintainer, with a coding agent"
LINE = re.compile(r"^- \*\*Operator\*\*: (?P<value>.*)$", re.MULTILINE)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "experiments"
    path.mkdir()
    return path


def _create(root: Path, size: Size, operator: str | None = None) -> Path:
    return create_experiment(
        root,
        slug="demo",
        title="Demo",
        category=Category.INGESTION,
        size=size,
        day=date(2026, 11, 6),
        operator=operator,
    )


def _values(folder: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in ("report.md", "protocol.md"):
        if (folder / name).is_file():
            match = LINE.search((folder / name).read_text(encoding="utf-8"))
            assert match, f"{name} has no Operator line"
            found[name] = match.group("value")
    return found


# ── the creator ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("size", [Size.QUICK, Size.STANDARD, Size.CONFIRMATORY])
def test_operator_goes_into_every_template_file(root: Path, size: Size) -> None:
    values = _values(_create(root, size, OPERATOR))
    assert values
    assert set(values.values()) == {OPERATOR}


def test_standard_size_fills_both_report_and_protocol(root: Path) -> None:
    assert set(_values(_create(root, Size.STANDARD, OPERATOR))) == {"report.md", "protocol.md"}


@pytest.mark.parametrize("size", [Size.QUICK, Size.STANDARD])
def test_without_the_option_the_placeholder_stays(root: Path, size: Size) -> None:
    values = _values(_create(root, size))
    assert values
    assert all("<" in value and ">" in value for value in values.values())


@pytest.mark.parametrize("bad", ["", "   ", "two\nlines", "a\rb"])
def test_a_blank_or_multi_line_operator_is_refused(root: Path, bad: str) -> None:
    with pytest.raises(ScaffoldError):
        _create(root, Size.QUICK, bad)
    assert list(root.iterdir()) == []


# ── the command ──────────────────────────────────────────────────────────


def _new(root: Path, *extra: str) -> Any:
    return runner.invoke(
        cli_app,
        [
            "experiments",
            "new",
            "demo",
            str(root),
            "--title",
            "Demo",
            "--category",
            "ingestion",
            "--size",
            "Standard",
            "--date",
            "2026-11-06",
            *extra,
        ],
    )


def test_new_takes_the_operator_option(root: Path) -> None:
    result = _new(root, "--operator", OPERATOR)
    assert result.exit_code == 0, result.stderr
    (folder,) = list(root.iterdir())
    assert set(_values(folder).values()) == {OPERATOR}


def test_new_without_the_option_keeps_the_placeholder(root: Path) -> None:
    result = _new(root)
    assert result.exit_code == 0, result.stderr
    (folder,) = list(root.iterdir())
    assert all("<" in value for value in _values(folder).values())


def test_new_refuses_a_blank_operator(root: Path) -> None:
    result = _new(root, "--operator", " ")
    assert result.exit_code == 1
    assert list(root.iterdir()) == []


# ── the checker ──────────────────────────────────────────────────────────


def _write_record(root: Path, name: str, report: str, protocol: str | None = None) -> None:
    folder = root / name
    folder.mkdir()
    record = {
        "format": "omrs-experiment/1",
        "number": name.partition("-")[0],
        "title": "Demo",
        "date": name[-10:],
        "category": "retrieval",
        "size": "Quick",
        "status": "PASS",
        "superseded_by": None,
        "finding": "Found.",
    }
    (folder / "experiment.json").write_text(json.dumps(record), encoding="utf-8")
    (folder / "report.md").write_text(report, encoding="utf-8")
    if protocol is not None:
        (folder / "protocol.md").write_text(protocol, encoding="utf-8")


def _codes(root: Path) -> list[tuple[str, str, str]]:
    return [
        (f.code, f.severity, f.message)
        for f in check_experiments(root)
        if f.code == "operator-placeholder"
    ]


def test_checker_warns_for_a_placeholder_operator_line(root: Path) -> None:
    _write_record(root, "1-demo-2026-11-06", "# R\n\n- **Operator**: <person>, with <agent>\n")
    ((code, severity, message),) = _codes(root)
    assert (code, severity) == ("operator-placeholder", "warning")
    assert "report.md" in message


def test_checker_reports_report_and_protocol_separately(root: Path) -> None:
    line = "- **Operator**: <who ran it>\n"
    _write_record(root, "1-demo-2026-11-06", f"# R\n\n{line}", f"# P\n\n{line}")
    messages = [message for _, _, message in _codes(root)]
    assert len(messages) == 2
    assert any("report.md" in m for m in messages)
    assert any("protocol.md" in m for m in messages)


def test_checker_is_quiet_for_a_filled_operator_line(root: Path) -> None:
    _write_record(root, "1-demo-2026-11-06", f"# R\n\n- **Operator**: {OPERATOR}\n")
    assert _codes(root) == []


def test_checker_ignores_a_file_with_no_operator_line(root: Path) -> None:
    _write_record(root, "1-demo-2026-11-06", "# R\n\nNo header line.\n")
    assert _codes(root) == []


def test_checker_ignores_angle_brackets_below_the_header(root: Path) -> None:
    body = "# R\n\n## Notes\n\n- **Operator**: <not in the header block>\n"
    _write_record(root, "1-demo-2026-11-06", body)
    assert _codes(root) == []


def test_a_placeholder_does_not_fail_a_normal_check(root: Path) -> None:
    from omrs.core.experiment_records.check import has_failures

    _write_record(root, "1-demo-2026-11-06", "# R\n\n- **Operator**: <person>\n")
    findings = [f for f in check_experiments(root) if f.code == "operator-placeholder"]
    assert findings
    assert not has_failures(findings, strict=False)
