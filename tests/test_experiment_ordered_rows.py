"""``experiments/_lib/ordered_rows.py``: rows that survive a stop (Exp 35 tasks 3.1, 3.3, 2.4).

Every test works on real files in ``tmp_path``. A stop is simulated the way a
killed process leaves things: an exception ends the stage, the open objects
are dropped, and a new ``RowFile`` with ``resume=True`` reads what is on disk.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from experiments._lib import ordered_rows as ordered_rows_module
from experiments._lib.hosted_calls import HostedGate, RateLimitStop
from experiments._lib.ordered_rows import ERROR_CAP, OrderedRows
from experiments._lib.trace import TraceWriter
from tests._exp35_fixtures import load

outputs35 = load("outputs35")

ORDER = ["q1", "q2", "q3", "q4"]
KEY = {"limit": None, "corpus_sample": None, "seed": 1, "qids": ORDER}


class _Stop(Exception):
    """The process stops here (a pod stop or a kill)."""


def _trace(folder: Path) -> TraceWriter:
    return TraceWriter(
        folder / "traces.jsonl",
        benchmark_revision="test",
        run_id="r",
        arm="a",
        repetition=1,
        effective_settings={},
        model_identities={},
    )


class _Stage:
    """One open stage: row file, trace writer and ordered rows."""

    def __init__(self, folder: Path, *, resume: bool, stage: str = "answer") -> None:
        self.log = outputs35.RowFile(folder, stage, KEY, resume=resume)
        self.trace = _trace(folder)
        self.rows = OrderedRows(self.log, ORDER, trace=self.trace)
        self.stage = stage

    def trace_row(self, qid: str, status: str = "ok") -> dict[str, Any]:
        return self.trace.row(stage=self.stage, dataset="d", question_id=qid, status=status)

    def submit(self, qid: str, answer: str) -> None:
        self.rows.submit(qid, {"qid": qid, "answer": answer}, self.trace_row(qid))

    def close(self) -> None:
        self.log.close()


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _qids(path: Path) -> list[str]:
    return [row.get("qid") or row.get("question_id") for row in _lines(path)]


Call = Callable[[str], Awaitable[Any]]


async def _run(
    folder: Path,
    call: Call,
    *,
    resume: bool,
    stop_after: str | None = None,
    stage: str = "answer",
    gate: HostedGate | None = None,
) -> _Stage:
    """A stage in miniature: dispatch, call, then submit, fail or stop.

    An error with no content stays pending (``fail``). Returned content is
    final. A ``RateLimitStop`` ends the stage with no row for that item.
    """
    st = _Stage(folder, resume=resume, stage=stage)
    try:
        for qid in st.rows.todo():
            st.rows.dispatch(qid)
            try:
                if gate is None:
                    result = await call(qid)
                else:
                    result = await gate.call(lambda qid=qid: call(qid))
            except RateLimitStop:
                return st
            except Exception as exc:  # noqa: BLE001 - a failed call has no content
                st.rows.fail(qid, f"{type(exc).__name__}: {exc}", st.trace_row(qid, "error"))
                continue
            if qid == stop_after:
                raise _Stop
            st.submit(qid, result)
        st.rows.finish({"rows": len(st.log.rows())})
        return st
    finally:
        st.close()


class _Calls:
    """A stub hosted call that counts its sends and plays a script per item."""

    def __init__(self, script: dict[str, Sequence[Any]] | None = None) -> None:
        self.sent: list[str] = []
        self.script = {k: list(v) for k, v in (script or {}).items()}

    async def __call__(self, qid: str) -> Any:
        self.sent.append(qid)
        steps = self.script.get(qid)
        step = steps.pop(0) if steps else f"answer {qid}"
        if isinstance(step, BaseException):
            raise step
        return step


# --- 3.1 ordered commit and the pending file -------------------------------------------


def test_results_finishing_3_1_2_are_committed_1_2_3(tmp_path: Path) -> None:
    st = _Stage(tmp_path, resume=False)
    for qid in ("q3", "q1", "q2", "q4"):
        st.rows.dispatch(qid)
        st.submit(qid, f"answer {qid}")
    assert _qids(st.log.path) == ORDER
    assert _qids(tmp_path / "traces.jsonl") == ORDER


def test_result_ahead_of_an_unfinished_item_is_in_pending_flushed_and_synced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = _Stage(tmp_path, resume=False)
    synced: list[int] = []
    real = os.fsync

    def spy(fd: int) -> None:
        synced.append(fd)
        real(fd)

    monkeypatch.setattr(ordered_rows_module.os, "fsync", spy)
    st.submit("q3", "answer q3")
    assert len(synced) == 1
    assert [e["id"] for e in _lines(tmp_path / "answer.pending.jsonl")] == ["q3"]
    assert _lines(st.log.path) == []


async def test_resume_commits_pending_in_order_and_calls_only_open_items(tmp_path: Path) -> None:
    st = _Stage(tmp_path, resume=False)
    st.submit("q3", "answer q3")
    st.submit("q4", "answer q4")
    st.close()  # the stop: q1 and q2 were in flight
    calls = _Calls()
    await _run(tmp_path, calls, resume=True)
    assert calls.sent == ["q1", "q2"]
    assert _qids(tmp_path / "answer.jsonl") == ORDER
    assert _qids(tmp_path / "traces.jsonl") == ORDER


async def test_done_marker_after_last_commit_then_pending_removed(tmp_path: Path) -> None:
    await _run(tmp_path, _Calls(), resume=False)
    marker = json.loads((tmp_path / ".done-answer.json").read_text(encoding="utf-8"))
    assert marker["rows"] == 4
    assert marker["resent_calls"] == 0
    assert not (tmp_path / "answer.pending.jsonl").exists()


def test_finish_writes_no_marker_while_an_item_is_open(tmp_path: Path) -> None:
    st = _Stage(tmp_path, resume=False)
    for qid in ("q1", "q2", "q4"):
        st.submit(qid, "x")
    assert st.rows.finish({}) is False
    assert not (tmp_path / ".done-answer.json").exists()
    assert (tmp_path / "answer.pending.jsonl").exists()


async def test_dispatch_record_is_synced_before_the_paid_call(tmp_path: Path) -> None:
    seen: list[list[str]] = []

    async def call(qid: str) -> str:
        seen.append([e["id"] for e in _lines(tmp_path / "answer.dispatch.jsonl")])
        return "x"

    await _run(tmp_path, call, resume=False)
    assert seen == [["q1"], ["q1", "q2"], ["q1", "q2", "q3"], ORDER]


async def test_call_cut_off_before_pending_write_is_resent_once(tmp_path: Path) -> None:
    first = _Calls()
    with pytest.raises(_Stop):
        await _run(tmp_path, first, resume=False, stop_after="q2")
    assert first.sent == ["q1", "q2"]
    assert _qids(tmp_path / "answer.jsonl") == ["q1"]
    # A refusal for q1 was saved: content never decides a resend.
    second = _Calls()
    st = await _run(tmp_path, second, resume=True)
    assert second.sent == ["q2", "q3", "q4"]
    assert st.rows.resent_calls == 1
    traces = {t["question_id"]: t["resent_calls"] for t in _lines(tmp_path / "traces.jsonl")}
    assert traces == {"q1": 0, "q2": 1, "q3": 0, "q4": 0}
    marker = json.loads((tmp_path / ".done-answer.json").read_text(encoding="utf-8"))
    assert marker["resent_calls"] == 1


async def test_result_in_pending_is_not_called_again(tmp_path: Path) -> None:
    st = _Stage(tmp_path, resume=False)
    st.rows.dispatch("q2")
    st.submit("q2", "")  # an empty answer is a result
    st.close()
    calls = _Calls()
    st = await _run(tmp_path, calls, resume=True)
    assert "q2" not in calls.sent
    assert st.rows.resent_calls == 0
    assert _lines(tmp_path / "answer.jsonl")[1] == {"qid": "q2", "answer": ""}


# --- 3.3 crash-safe trace rows ---------------------------------------------------------


def test_trace_writer_repairs_a_cut_last_line_on_open(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "traces.jsonl"
    path.write_text('{"stage": "search", "question_id": "q0"}\n{"stage": "sea', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        writer = _trace(tmp_path)
    assert "traces.jsonl" in caplog.text
    writer.write(stage="answer", dataset="d", question_id="q1")
    assert _qids(path) == ["q0", "q1"]


def test_stop_between_row_and_trace_is_completed_on_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    st = _Stage(tmp_path, resume=False)
    st.submit("q1", "a1")

    def stop(row: Any) -> None:
        raise _Stop

    monkeypatch.setattr(st.trace, "append", stop)
    with pytest.raises(_Stop):
        st.submit("q2", "a2")
    st.close()
    assert _qids(tmp_path / "answer.jsonl") == ["q1", "q2"]
    assert _qids(tmp_path / "traces.jsonl") == ["q1"]
    monkeypatch.undo()
    st = _Stage(tmp_path, resume=True)
    assert st.rows.todo() == ["q3", "q4"]
    assert _qids(tmp_path / "traces.jsonl") == ["q1", "q2"]
    assert _qids(tmp_path / "answer.jsonl") == ["q1", "q2"]


# --- 2.4 the resend rule and the error cap ---------------------------------------------


async def test_error_with_no_content_stays_pending_and_is_resent(tmp_path: Path) -> None:
    calls = _Calls({"q2": [TimeoutError("read timed out")]})
    st = await _run(tmp_path, calls, resume=False)
    assert _qids(tmp_path / "answer.jsonl") == ["q1"]
    assert [e["id"] for e in _lines(tmp_path / "answer.errors.jsonl")] == ["q2"]
    assert not (tmp_path / ".done-answer.json").exists()
    assert st.rows.closed_missing == []
    calls.sent.clear()
    st = await _run(tmp_path, calls, resume=True)
    assert calls.sent == ["q2"]
    assert _qids(tmp_path / "answer.jsonl") == ORDER
    assert st.rows.resent_calls == 1


async def test_returned_content_is_final(tmp_path: Path) -> None:
    calls = _Calls({"q1": [""], "q2": ["I cannot answer from the evidence."]})
    await _run(tmp_path, calls, resume=False)
    calls.sent.clear()
    await _run(tmp_path, calls, resume=True)
    assert calls.sent == []
    rows = _lines(tmp_path / "answer.jsonl")
    assert rows[0]["answer"] == "" and rows[1]["answer"].startswith("I cannot")


async def test_third_error_across_resumes_closes_the_item_as_missing(tmp_path: Path) -> None:
    calls = _Calls({"q2": [TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")]})
    await _run(tmp_path, calls, resume=False)
    await _run(tmp_path, calls, resume=True)
    assert not (tmp_path / ".done-answer.json").exists()
    st = await _run(tmp_path, calls, resume=True)
    assert calls.sent.count("q2") == ERROR_CAP == 3
    rows = _lines(tmp_path / "answer.jsonl")
    assert [r["qid"] for r in rows] == ORDER
    assert rows[1] == {"qid": "q2", "missing": True, "error": "TimeoutError: t3"}
    assert st.rows.closed_missing == ["q2"]
    marker = json.loads((tmp_path / ".done-answer.json").read_text(encoding="utf-8"))
    assert marker["closed_missing"] == ["q2"]
    assert marker["resent_calls"] == 2


class _Limited(Exception):
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        super().__init__(f"Error code: {status}")
        self.status_code = status
        self.response = type("R", (), {"headers": headers or {}})()


async def _no_sleep(seconds: float) -> None:
    return None


async def test_rate_limit_attempts_do_not_count_toward_the_cap(tmp_path: Path) -> None:
    gate = HostedGate("answer", 1, sleep=_no_sleep, rand=lambda: 0.5)
    calls = _Calls({"q2": [_Limited(429)] * 5 + ["late answer"]})
    st = await _run(tmp_path, calls, resume=False, gate=gate)
    assert _lines(tmp_path / "answer.jsonl")[1] == {"qid": "q2", "answer": "late answer"}
    assert not (tmp_path / "answer.errors.jsonl").exists()
    assert st.rows.resent_calls == 0


async def test_rate_limit_stop_and_out_of_credit_do_not_count_toward_the_cap(
    tmp_path: Path,
) -> None:
    gate = HostedGate("answer", 1, attempts=2, sleep=_no_sleep, rand=lambda: 0.5)
    calls = _Calls({"q2": [_Limited(429), _Limited(429), _Limited(402), _Limited(402)]})
    for _ in range(3):  # attempts used up, out of credit, out of credit
        await _run(tmp_path, calls, resume=True, gate=gate)
        assert _qids(tmp_path / "answer.jsonl") == ["q1"]
    st = await _run(tmp_path, calls, resume=True, gate=gate)
    assert not (tmp_path / "answer.errors.jsonl").exists()
    assert st.rows.closed_missing == []
    assert _qids(tmp_path / "answer.jsonl") == ORDER
    assert st.rows.resent_calls == 3


async def test_failed_search_saves_no_row_and_is_searched_again(tmp_path: Path) -> None:
    calls = _Calls({"q3": [ConnectionError("index closed")]})
    await _run(tmp_path, calls, resume=False, stage="search")
    assert _qids(tmp_path / "search.jsonl") == ["q1", "q2"]
    calls.sent.clear()
    st = await _run(tmp_path, calls, resume=True, stage="search")
    assert calls.sent == ["q3"]
    assert _qids(tmp_path / "search.jsonl") == ORDER
    assert st.rows.resent_calls == 1


async def test_one_answer_resent_twice_counts_two(tmp_path: Path) -> None:
    calls = _Calls({"q4": [TimeoutError("a"), TimeoutError("b")]})
    for resume in (False, True, True):
        st = await _run(tmp_path, calls, resume=resume)
    assert st.rows.resent_calls == 2
    trace = [t for t in _lines(tmp_path / "traces.jsonl") if t["question_id"] == "q4"]
    assert [t["resent_calls"] for t in trace] == [2]


async def test_stop_between_third_error_and_missing_row_is_not_sent_a_fourth_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue 216: the stop lands after the third error line, before the missing row."""
    calls = _Calls({"q2": [TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")]})
    await _run(tmp_path, calls, resume=False)
    await _run(tmp_path, calls, resume=True)

    def stop_before_the_row(self: OrderedRows, *args: Any, **kwargs: Any) -> None:
        raise _Stop

    with monkeypatch.context() as patch:
        patch.setattr(OrderedRows, "submit", stop_before_the_row)
        with pytest.raises(_Stop):
            await _run(tmp_path, calls, resume=True)
    assert len(_lines(tmp_path / "answer.errors.jsonl")) == ERROR_CAP
    assert _qids(tmp_path / "answer.jsonl") == ["q1"]
    calls.sent.clear()
    st = _Stage(tmp_path, resume=True)
    try:
        assert st.rows.todo() == []
    finally:
        st.close()
    assert calls.sent == []
    rows = _lines(tmp_path / "answer.jsonl")
    assert [r["qid"] for r in rows] == ORDER
    assert rows[1] == {"qid": "q2", "missing": True, "error": "TimeoutError: t3"}
    st = await _run(tmp_path, calls, resume=True)
    assert calls.sent == []
    assert st.rows.closed_missing == ["q2"]
    traces = [t for t in _lines(tmp_path / "traces.jsonl") if t["question_id"] == "q2"]
    assert [t["status"] for t in traces] == ["error"]
