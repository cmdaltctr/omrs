"""The experiment folder creator (experiment-format-v1, task 5.2, spec "New experiment folders").

The tests use the real packaged templates.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from omrs.core.experiment_records.record import Category, Size, Status, load_record
from omrs.core.experiment_records.reserved import Reservation
from omrs.core.experiment_records.scaffold import (
    ScaffoldError,
    create_experiment,
    follow_up_number,
    next_number,
)
from omrs.core.experiment_records.scan import scan_experiments
from omrs.core.experiment_records.templates import TEMPLATE_NAMES, read_template

_DAY = date(2026, 10, 26)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "experiments"
    path.mkdir()
    return path


def _folders(root: Path, *names: str) -> None:
    for name in names:
        (root / name).mkdir()


def _reserved(*numbers: str) -> list[Reservation]:
    return [Reservation(number=n, reason="planned", ref="x") for n in numbers]


def _new(root: Path, **kwargs: object) -> Path:
    options: dict[str, object] = {
        "slug": "ocr-text-quality",
        "title": "OCR text quality",
        "category": Category.INGESTION,
        "size": Size.STANDARD,
        "day": _DAY,
    }
    options.update(kwargs)
    return create_experiment(root, **options)  # type: ignore[arg-type]


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
        for p in sorted(root.rglob("*"))
    }


def test_every_template_loads() -> None:
    for name in TEMPLATE_NAMES:
        assert read_template(name).strip()


def test_unknown_template_is_refused() -> None:
    with pytest.raises(KeyError, match="nope"):
        read_template("nope.md")


def test_next_number_follows_the_highest_folder(root: Path) -> None:
    _folders(root, "41-a-2026-01-01", "42-b-2026-01-01", "10.1-c-2026-01-01", "42a-d-2026-01-01")
    assert next_number(scan_experiments(root), ()) == "43"


def test_next_number_skips_a_reservation(root: Path) -> None:
    _folders(root, "42-b-2026-01-01")
    assert next_number(scan_experiments(root), _reserved("43")) == "44"
    assert next_number(scan_experiments(root), _reserved("43", "44")) == "45"


def test_next_number_ignores_reservations_below_the_highest(root: Path) -> None:
    _folders(root, "42-b-2026-01-01")
    assert next_number(scan_experiments(root), _reserved("35", "40", "41")) == "43"


def test_next_number_in_an_empty_directory_is_one(root: Path) -> None:
    assert next_number((), ()) == "1"


def test_follow_up_letters_count_up(root: Path) -> None:
    _folders(root, "38-base-2026-01-01")
    assert follow_up_number("38", scan_experiments(root), ()) == "38a"
    _folders(root, "38a-next-2026-01-02")
    assert follow_up_number("38", scan_experiments(root), ()) == "38b"


def test_follow_up_skips_a_reserved_letter(root: Path) -> None:
    _folders(root, "38-base-2026-01-01")
    assert follow_up_number("38", scan_experiments(root), _reserved("38a")) == "38b"


@pytest.mark.parametrize("base", ["38a", "10.1", "x", ""])
def test_follow_up_needs_a_plain_number(root: Path, base: str) -> None:
    with pytest.raises(ScaffoldError, match="plain number"):
        follow_up_number(base, (), ())


def test_follow_up_of_an_unknown_experiment_is_refused(root: Path) -> None:
    with pytest.raises(ScaffoldError, match="38"):
        follow_up_number("38", (), ())


def test_standard_experiment_files(root: Path) -> None:
    _folders(root, "42-b-2026-01-01")
    folder = _new(root)
    assert folder == root / "43-ocr-text-quality-2026-10-26"
    assert sorted(p.name for p in folder.iterdir()) == [
        "experiment.json",
        "plan.json",
        "protocol.md",
        "report.md",
    ]
    record = load_record(folder / "experiment.json")
    assert record.status is Status.PLANNED
    assert (record.number, record.title, record.date) == ("43", "OCR text quality", _DAY)
    assert (record.category, record.size) == (Category.INGESTION, Size.STANDARD)
    assert record.superseded_by is None
    assert record.migration is None


def test_template_placeholders_are_filled(root: Path) -> None:
    _folders(root, "42-b-2026-01-01")
    folder = _new(root)
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    assert plan["experiment_id"] == "43-ocr-text-quality-2026-10-26"
    assert "status" not in plan
    report = (folder / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# Experiment 43: OCR text quality\n")
    assert "`43-ocr-text-quality-2026-10-26`" in report
    protocol = (folder / "protocol.md").read_text(encoding="utf-8")
    assert "<number>" not in protocol
    assert "<title>" not in protocol


def test_title_with_quotes_keeps_plan_valid_json(root: Path) -> None:
    folder = _new(root, title='The "quoted" run')
    json.loads((folder / "plan.json").read_text(encoding="utf-8"))


def test_quick_experiment_has_record_and_report_only(root: Path) -> None:
    folder = _new(root, size=Size.QUICK, slug="quick-look")
    assert sorted(p.name for p in folder.iterdir()) == ["experiment.json", "report.md"]
    report = (folder / "report.md").read_text(encoding="utf-8")
    quick = read_template("report-quick.md")
    assert report.splitlines()[0] == "# Experiment 1: OCR text quality"
    assert report.splitlines()[3:] == quick.splitlines()[3:]
    assert load_record(folder / "experiment.json").size is Size.QUICK


def test_confirmatory_has_the_standard_files(root: Path) -> None:
    folder = _new(root, size=Size.CONFIRMATORY)
    assert sorted(p.name for p in folder.iterdir()) == [
        "experiment.json",
        "plan.json",
        "protocol.md",
        "report.md",
    ]


def test_follow_up_creates_a_lettered_folder(root: Path) -> None:
    _folders(root, "38-base-2026-01-01")
    folder = _new(root, follow_up="38", slug="retry")
    assert folder.name == "38a-retry-2026-10-26"
    assert load_record(folder / "experiment.json").number == "38a"


def test_reserved_number_is_skipped(root: Path) -> None:
    _folders(root, "42-b-2026-01-01")
    (root / "reserved.json").write_text(
        json.dumps(
            {
                "format": "omrs-experiment-reservations/1",
                "reservations": [{"number": "43", "reason": "r", "ref": "x"}],
            }
        ),
        encoding="utf-8",
    )
    assert _new(root).name.startswith("44-")


def test_existing_folder_is_refused_and_nothing_written(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _folders(root, "42-b-2026-01-01")
    first = _new(root)
    (first / "report.md").write_text("my notes\n", encoding="utf-8")
    # Another process took the number between the scan and the write.
    monkeypatch.setattr("omrs.core.experiment_records.scaffold.next_number", lambda *_: "43")
    before = _snapshot(root)
    with pytest.raises(ScaffoldError, match="already exists"):
        _new(root, title="Again")
    assert _snapshot(root) == before


def test_existing_file_with_the_name_is_refused(root: Path) -> None:
    (root / "1-ocr-text-quality-2026-10-26").write_text("a file", encoding="utf-8")
    before = _snapshot(root)
    with pytest.raises(ScaffoldError, match="already exists"):
        _new(root)
    assert _snapshot(root) == before


@pytest.mark.parametrize("slug", ["OCR", "ocr text", "ocr--x", "-ocr", ""])
def test_bad_slug_is_refused_and_nothing_written(root: Path, slug: str) -> None:
    with pytest.raises(ScaffoldError, match="slug"):
        _new(root, slug=slug)
    assert list(root.iterdir()) == []


def test_bad_title_is_refused_and_nothing_written(root: Path) -> None:
    with pytest.raises(ScaffoldError, match="title"):
        _new(root, title="two\nlines")
    assert list(root.iterdir()) == []


def test_missing_root_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ScaffoldError, match="not a directory"):
        _new(tmp_path / "missing")


def test_failed_write_removes_only_the_new_folder(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _folders(root, "42-b-2026-01-01")
    (root / "42-b-2026-01-01" / "notes.md").write_text("keep\n", encoding="utf-8")
    before = _snapshot(root)
    real_open = Path.open

    def failing_open(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == "plan.json" and args[:1] == ("x",):
            raise OSError("disk full")
        return real_open(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(OSError, match="disk full"):
        _new(root)
    monkeypatch.undo()
    assert _snapshot(root) == before


@pytest.mark.parametrize(
    ("options", "field"),
    [({"title": "two\nlines"}, "title"), ({"title": ""}, "title"), ({"slug": "Bad Slug"}, "slug")],
)
def test_refusal_message_is_one_plain_line(root: Path, options: dict[str, str], field: str) -> None:
    with pytest.raises(ScaffoldError) as caught:
        _new(root, **options)
    message = str(caught.value)
    assert field in message
    assert "\n" not in message
    assert "pydantic" not in message
