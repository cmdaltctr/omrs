"""Checker rules for ``publication`` experiments (reproducible-experiment-runtime, task 2.3, D3).

A ``publication`` experiment must be Confirmatory and must pin its local
models in a valid ``runtime`` block of ``plan.json``. An ``optimisation``
record and a record without a purpose get no finding from these rules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from omrs.core.experiment_records.check import Finding, check_experiments

_NAME = "44-embed-parity-2026-10-27"
_SHA = "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439"
_RUNTIME: dict[str, Any] = {
    "models": [
        {
            "role": "embedding",
            "repository": "Qwen/Qwen3-Embedding-0.6B-GGUF",
            "file": "Qwen3-Embedding-0.6B-Q8_0.gguf",
            "sha256": _SHA,
            "runtime": "llama.cpp",
            "build": 11671,
        }
    ],
    "tolerance": [{"metric": "recall_at_10", "max_abs_change": 0.01}],
}
_CODES = {
    "publication-not-confirmatory",
    "publication-plan-unreadable",
    "publication-runtime-missing",
    "publication-runtime-invalid",
}


def _make(
    root: Path, *, plan: object = None, plan_text: str | None = None, **overrides: Any
) -> None:
    folder = root / _NAME
    folder.mkdir(parents=True)
    record: dict[str, Any] = {
        "format": "omrs-experiment/1",
        "number": "44",
        "title": "Embedding parity",
        "date": "2026-10-27",
        "category": "retrieval",
        "size": "Confirmatory",
        "status": "PLANNED",
        "superseded_by": None,
        "finding": "",
    }
    record.update(overrides)
    (folder / "experiment.json").write_text(json.dumps(record), encoding="utf-8")
    for file in ("protocol.md", "report.md"):
        (folder / file).write_text("text\n", encoding="utf-8")
    if plan_text is not None:
        (folder / "plan.json").write_text(plan_text, encoding="utf-8")
    elif plan is not None:
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")


def _publication(root: Path) -> list[Finding]:
    return [f for f in check_experiments(root) if f.code in _CODES]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "experiments"
    path.mkdir()
    return path


def test_valid_publication_experiment_has_no_finding(root: Path) -> None:
    _make(root, purpose="publication", plan={"runtime": _RUNTIME})
    assert _publication(root) == []


def test_publication_of_standard_size_is_an_error(root: Path) -> None:
    _make(root, purpose="publication", size="Standard", plan={"runtime": _RUNTIME})
    (finding,) = _publication(root)
    assert finding.code == "publication-not-confirmatory"
    assert finding.severity == "error"
    assert finding.folder == _NAME
    assert _NAME in finding.message
    assert "Confirmatory" in finding.message


def test_publication_without_runtime_block_is_an_error(root: Path) -> None:
    _make(root, purpose="publication", plan={"hypothesis": "x"})
    (finding,) = _publication(root)
    assert finding.code == "publication-runtime-missing"
    assert finding.severity == "error"
    assert _NAME in finding.message
    assert "runtime" in finding.message


@pytest.mark.parametrize("plan_text", [None, "{not json", "[1, 2]"])
def test_publication_with_unreadable_plan_is_an_error(root: Path, plan_text: str | None) -> None:
    _make(root, purpose="publication", plan_text=plan_text)
    (finding,) = _publication(root)
    assert finding.code == "publication-plan-unreadable"
    assert finding.severity == "error"
    assert _NAME in finding.message
    assert "plan.json" in finding.message


def test_publication_with_invalid_runtime_block_is_an_error(root: Path) -> None:
    runtime = json.loads(json.dumps(_RUNTIME))
    runtime["models"][0].update(runtime="ollama", version="0.40.11")
    _make(root, purpose="publication", plan={"runtime": runtime})
    (finding,) = _publication(root)
    assert finding.code == "publication-runtime-invalid"
    assert finding.severity == "error"
    assert _NAME in finding.message
    assert "llama.cpp" in finding.message


@pytest.mark.parametrize("purpose", ["optimisation", None])
def test_optimisation_or_purposeless_record_gets_no_runtime_finding(
    root: Path, purpose: str | None
) -> None:
    extra = {} if purpose is None else {"purpose": purpose}
    _make(root, size="Standard", plan={"hypothesis": "x"}, **extra)
    assert _publication(root) == []


@pytest.mark.parametrize("purpose", ["optimisation", None])
def test_optimisation_or_purposeless_record_with_unreadable_plan_is_quiet(
    root: Path, purpose: str | None
) -> None:
    extra = {} if purpose is None else {"purpose": purpose}
    _make(root, plan_text="{not json", **extra)
    assert _publication(root) == []


def test_scaffolded_publication_experiment_is_flagged_until_pinned(root: Path) -> None:
    from datetime import date

    from omrs.core.experiment_records import Purpose
    from omrs.core.experiment_records.record import Category, Size
    from omrs.core.experiment_records.scaffold import create_experiment

    create_experiment(
        root,
        slug="embed-parity",
        title="Embedding parity",
        category=Category.RETRIEVAL,
        size=Size.CONFIRMATORY,
        day=date(2026, 10, 27),
        purpose=Purpose.PUBLICATION,
    )
    assert [f.code for f in _publication(root)] == ["publication-runtime-invalid"]
