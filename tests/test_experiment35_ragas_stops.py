# ruff: noqa: S101
"""Experiment 35 Ragas stage: out-of-credit stop and closed-with-open metrics (task 7.2).

Rules under test (A5 R-3 and R-5, pre-registration section 12): an
out-of-credit reply (HTTP 402 with no ``Retry-After``) stops the stage with
exit code 5, leaves the metric open, does not count toward the cap and leaves
the answer's last partial row unchanged; ``--resume`` never resends a metric
saved there. An answer with one closed metric and one open metric stays
partial, and ``--resume`` sends a call for the open metric only.

Stub metrics and scripted seam; no Ragas, no router, no network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests._exp35_ragas_fixtures import (
    APIConnectionError,
    Router,
    Script,
    Status429,
    answer_row,
    ctx,
    parts,
    ragas35,
    rows,
    run,
    write_answers,
)

FIVE = list(ragas35.METRICS)
FAITH, RELEVANCY, PRECISION, RECALL, CORRECTNESS = FIVE


class Status402(Exception):
    """An out-of-credit reply as the openai client raises it: HTTP 402, no ``Retry-After``."""

    status_code = 402


def _setup(tmp_path: Path, qids: list[str]) -> Path:
    run_dir = tmp_path / "financebench" / "e4b-c512-roff-hoff" / "run1"
    write_answers(run_dir, [answer_row(q) for q in qids])
    return run_dir


def _resume(run_dir: Path, qids: list[str], script: Script, router: Router) -> int:
    c = ctx(run_dir, qids, router)
    c.resume = True
    return run(c, parts(script, router))


def _partial(run_dir: Path) -> list[dict[str, Any]]:
    text = (run_dir / "ragas.partial.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _sent(script: Script, qid: str) -> list[str]:
    return [p.split("|")[0] for p in script.prompts if p.split("|")[1] == qid]


def test_an_out_of_credit_reply_stops_with_code_5_and_leaves_the_partial_row(
    tmp_path: Path,
) -> None:
    run_dir = _setup(tmp_path, ["q1", "q2"])
    router = Router()
    lost = Script({(CORRECTNESS, "q1"): APIConnectionError})
    assert run(ctx(run_dir, ["q1", "q2"], router), parts(lost, router)) == ragas35.EXIT_OPEN
    partial_before = (run_dir / "ragas.partial.jsonl").read_bytes()
    errors_before = (run_dir / "ragas.metric-errors.jsonl").read_bytes()
    assert sorted(_partial(run_dir)[-1]["metrics"]) == sorted(set(FIVE) - {CORRECTNESS})

    broke = Script({(CORRECTNESS, "q1"): Status402})
    assert _resume(run_dir, ["q1", "q2"], broke, router) == ragas35.EXIT_RATE_LIMIT
    assert _sent(broke, "q1") == [CORRECTNESS]  # 402 is never retried, never resends a saved one
    assert _sent(broke, "q2") == []  # the stop sends nothing more
    assert (run_dir / "ragas.partial.jsonl").read_bytes() == partial_before
    assert (run_dir / "ragas.metric-errors.jsonl").read_bytes() == errors_before  # not a cap
    assert rows(run_dir) == [] and not (run_dir / ".done-ragas.json").exists()
    summary = json.loads((run_dir / "ragas-summary.json").read_text())
    assert summary["unjudged_open"] == {CORRECTNESS: 1} and summary["unjudged_closed"] == {}

    clean = Script()
    assert _resume(run_dir, ["q1", "q2"], clean, router) == 0
    assert set(_sent(clean, "q1")) == {CORRECTNESS}
    final = rows(run_dir)[0]
    assert sorted(final["metrics"]) == sorted(FIVE) and final["unjudged"] == []


def test_an_answer_with_one_closed_and_one_open_metric_stays_partial(tmp_path: Path) -> None:
    run_dir = _setup(tmp_path, ["q1"])
    router = Router()
    # Runs 1 and 2: faithfulness fails, then a rate-limit stop on context recall,
    # so answer correctness is never sent. Run 3: faithfulness fails a third time
    # (closed) and answer correctness fails once (open).
    held = {(FAITH, "q1"): APIConnectionError, (RECALL, "q1"): Status429}
    assert run(ctx(run_dir, ["q1"], router), parts(Script(held), router)) == ragas35.EXIT_RATE_LIMIT
    assert _resume(run_dir, ["q1"], Script(held), router) == ragas35.EXIT_RATE_LIMIT
    third = Script({(FAITH, "q1"): APIConnectionError, (CORRECTNESS, "q1"): APIConnectionError})
    assert _resume(run_dir, ["q1"], third, router) == ragas35.EXIT_OPEN

    last = _partial(run_dir)[-1]
    assert {u["metric"]: (u["errors"], u["closed"]) for u in last["unjudged"]} == {
        FAITH: (3, True),
        CORRECTNESS: (1, False),
    }
    assert rows(run_dir) == [] and not (run_dir / ".done-ragas.json").exists()

    clean = Script()
    assert _resume(run_dir, ["q1"], clean, router) == 0
    assert set(_sent(clean, "q1")) == {CORRECTNESS}
    final = rows(run_dir)[0]
    assert FAITH not in final["metrics"] and CORRECTNESS in final["metrics"]
    assert final["unjudged"] == [
        {"metric": FAITH, "errors": 3, "error": "APIConnectionError", "closed": True}
    ]
