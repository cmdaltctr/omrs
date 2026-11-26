"""Experiment 35 budget projection and drop record (task 6.5; pre-registration section 17).

All inputs are synthetic files in a tmp folder.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import FOLDER, load

budget35 = load("budget35")

TIME = "2026-11-20T10:00:00+00:00"


def _rates(**changes: object) -> dict:
    rates: dict = {
        "pod_usd_per_hour": 1.0,
        "pod_hours_per_answer": 0.0,
        "hosted_per_answer": {"answer": {"calls_per_answer": 1.0, "usd_per_call": 0.0}},
        "answers_done": {},
        "other_work": [
            {"item": "length-controlled check", "pod_hours": 10.0, "calls": 0, "usd_per_call": 0,
             "drop_step": 2},
            {"item": "closed-book run, RAG prompt", "pod_hours": 20.0, "calls": 0,
             "usd_per_call": 0, "drop_step": 3},
            {"item": "oracle run", "pod_hours": 5.0, "calls": 100, "usd_per_call": 0.01,
             "drop_step": None},
        ],
    }  # fmt: skip
    rates.update(changes)
    return rates


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _project(tmp_path: Path, rates: dict, billing: list[list[dict]] | None = None) -> int:
    args = ["project", "--rates", str(_write(tmp_path / "rates.json", rates)),
            "--out", str(tmp_path / "out")]  # fmt: skip
    for i, rows in enumerate(billing or []):
        args += ["--billing", str(_write(tmp_path / f"bill{i}.json", rows))]
    return budget35.main(args, now=lambda: TIME)


def _checks(tmp_path: Path) -> list[dict]:
    return json.loads((tmp_path / "out" / "budget-check.json").read_text())["checks"]


def _drops(tmp_path: Path) -> list[dict]:
    path = tmp_path / "out" / "drops.json"
    return json.loads(path.read_text())["drops"] if path.exists() else []


def test_the_projection_counts_the_fifteen_answer_setups(tmp_path: Path) -> None:
    hosted = {"answer": {"calls_per_answer": 2.0, "usd_per_call": 0.001}}
    _project(tmp_path, _rates(hosted_per_answer=hosted, other_work=[]))
    check = _checks(tmp_path)[-1]
    assert check["answer_setups"] == 15
    assert sum(check["remaining_answers"].values()) == 15 * 3 * 1160
    assert check["projection_usd"] == pytest.approx(15 * 3 * 1160 * 0.002)


def test_spent_comes_from_the_billing_exports_and_done_answers_leave_the_projection(
    tmp_path: Path,
) -> None:
    hosted = {"answer": {"calls_per_answer": 1.0, "usd_per_call": 0.01}}
    rates = _rates(hosted_per_answer=hosted, other_work=[], answers_done={"bioasq": 45 * 707})
    billing = [[{"provider": "runpod", "usd": 100.0}], [{"provider": "openrouter", "usd": 23.5}]]
    _project(tmp_path, rates, billing)
    check = _checks(tmp_path)[-1]
    assert check["spent_usd"] == pytest.approx(123.5)
    assert check["remaining_answers"]["bioasq"] == 0
    assert check["projection_usd"] == pytest.approx(123.5 + 45 * (150 + 203 + 100) * 0.01)


def test_a_projection_under_the_ceiling_writes_no_drop(tmp_path: Path) -> None:
    assert _project(tmp_path, _rates()) == 0
    check = _checks(tmp_path)[-1]
    assert check["ceiling_usd"] == 1716.0
    assert check["projection_usd"] == pytest.approx(10 + 20 + 5 + 1.0)
    assert check["drop_step"] is None
    assert _drops(tmp_path) == []


def test_over_the_ceiling_the_next_drop_step_is_recorded_once(tmp_path: Path) -> None:
    rates = _rates(pod_hours_per_answer=0.04)  # 52,200 answers x 0.04 h = 2,088 h
    _project(tmp_path, rates)
    assert _checks(tmp_path)[-1]["drop_step"] == 1
    drops = _drops(tmp_path)
    assert [d["step"] for d in drops] == [1]
    assert drops[0]["time"] == TIME
    assert drops[0]["projection_usd"] == pytest.approx(2088 + 36)
    assert "1716" in drops[0]["reason"]
    # Legal answers leave: 45 x 1,060 x 0.04 = 1,908 h plus 36 h is still over, so step 2.
    _project(tmp_path, rates)
    assert [d["step"] for d in _drops(tmp_path)] == [1, 2]
    assert _checks(tmp_path)[-1]["remaining_answers"].get("legal") is None


def test_a_second_call_under_the_ceiling_after_a_drop_adds_nothing(tmp_path: Path) -> None:
    rates = _rates(pod_hours_per_answer=0.034)  # 1,774.8 h; without Legal 1,621.8 h
    _project(tmp_path, rates)
    _project(tmp_path, rates)
    assert [d["step"] for d in _drops(tmp_path)] == [1]
    assert len(_checks(tmp_path)) == 2
    assert _checks(tmp_path)[-1]["drop_step"] is None


def test_drop_steps_two_and_three_remove_their_work_and_then_the_run_stops(
    tmp_path: Path,
) -> None:
    rates = _rates(pod_usd_per_hour=400.0)  # other work alone is 14,001 dollars
    codes = [_project(tmp_path, rates) for _ in range(4)]
    assert [d["step"] for d in _drops(tmp_path)] == [1, 2, 3]
    assert codes == [0, 0, 0, budget35.EXIT_STOP]
    assert [c["projection_usd"] for c in _checks(tmp_path)] == pytest.approx(
        [14_001, 14_001, 10_001, 2_001]
    )
    last = _checks(tmp_path)[-1]
    assert last["stop"] is True
    assert last["drop_step"] is None


def test_the_budget_tool_does_not_use_the_prefreeze_cost_code() -> None:
    source = (FOLDER / "budget35.py").read_text(encoding="utf-8")
    assert "measure_lib" not in source


# --- the drop record the join, label sampler and report read ---------------------------------


def test_no_drop_record_needs_every_answer_dataset(tmp_path: Path) -> None:
    assert budget35.read_drops(tmp_path) == frozenset()
    every = ("financebench", "freshstack", "bioasq", "legal")
    assert budget35.answer_datasets(frozenset()) == every


def test_a_recorded_drop_step_one_removes_legal_answers(tmp_path: Path) -> None:
    _project(tmp_path, _rates(pod_hours_per_answer=0.04))
    steps = budget35.read_drops(tmp_path / "out")
    assert steps == frozenset({1})
    assert budget35.answer_datasets(steps) == ("financebench", "freshstack", "bioasq")
