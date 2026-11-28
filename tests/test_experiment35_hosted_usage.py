"""Experiment 35 compute-table items of task 16.20 (pre-registration sections 17 and 21).

Hosted tokens and cost per role, error rows per stage and role, harness resends
and closed calls, provider billing per provider (the source of GLM-5.3 and
classifier tokens and cost, amendment A18 item 35), an energy estimate, every
``out_of_credit`` stop and the returned model per role.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests._exp35_fixtures import load

hostedusage35 = load("hostedusage35")
ND = hostedusage35.NOT_DEFINED


def _rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _run(out: Path, kind: str = "answer", setup: str = "e4b-c512-r0.6b-hon", run: int = 1) -> Path:
    return out / "bioasq" / kind / setup / f"run{run}"


def _tree(out: Path) -> None:
    run = _run(out)
    _rows(
        run / "answer.jsonl",
        [
            {"qid": "1", "status": "ok", "input_tokens": 100, "output_tokens": 10, "cost_usd": 0.5},
            {"qid": "2", "status": "error", "error": "boom", "input_tokens": 50, "cost_usd": 0.25},
        ],
    )
    _json(run / "answer-summary.json", {"resent_calls": 2, "closed_missing": ["3"]})
    _rows(
        run / "ragas.jsonl",
        [
            {
                "qid": "1",
                "calls": [
                    {"error": "", "input_tokens": 7, "output_tokens": 3, "reported_cost_usd": 0.1},
                    {"error": "timeout", "input_tokens": 5, "output_tokens": 1},
                ],
            }
        ],
    )
    _rows(
        run / "judge-chat.jsonl",
        [
            {"qid": "1", "verdicts": [{"call": {"error": None}}, {"call": {"error": "x"}}]},
            {"qid": "2", "verdicts": [{"call": {"error": None}}]},
        ],
    )
    _json(run / "judge-chat-summary.json", {"resent_calls": 1, "closed_missing": []})
    _rows(
        run / "claim-kinds.jsonl",
        [
            {
                "claim_key": "a",
                "kind": "factual",
                "input_tokens": 9,
                "output_tokens": 1,
                "cost_usd": 0.02,
            }
        ],
    )
    _json(run / "claimkinds-summary.json", {"resent_calls": 0, "closed_missing": []})
    _rows(
        run / "answer.errors.jsonl",
        [
            {
                "id": "3",
                "error": "bad reply",
                "usage": {"input_tokens": 40, "output_tokens": 5, "cost_usd": 0.25},
            },
            {"id": "3", "error": "timeout"},
        ],
    )
    cb = _run(out, kind="closedbook-own")
    _rows(cb / "answer.jsonl", [{"qid": "1", "status": "ok", "input_tokens": 4, "cost_usd": 0.01}])


def _role(table: dict[str, Any], stage: str, role: str) -> dict[str, Any]:
    return next(r for r in table["roles"] if r["stage"] == stage and r["role"] == role)


def test_answer_and_ragas_tokens_and_cost_come_from_the_rows(tmp_path: Path) -> None:
    _tree(tmp_path)
    table = hostedusage35.hosted_usage(tmp_path)
    answer = _role(table, "answer", "answer")
    # Saved rows 150 tokens and $0.75, plus the billed failed attempt (40 tokens, $0.25).
    assert (answer["rows"], answer["input_tokens"], answer["cost_usd"]) == (2, 190, 1.0)
    assert answer["failed_attempts"] == 2 and answer["failed_attempts_without_usage"] == 1
    # One row reported no output tokens: the sum is not defined, never a silent undercount.
    assert answer["output_tokens"] == ND
    assert answer["source"] == "rows"
    ragas = _role(table, "answer", "ragas-judge")
    assert (ragas["calls"], ragas["input_tokens"], ragas["output_tokens"]) == (2, 12, 4)
    assert ragas["cost_usd"] == ND  # the failed call reported no cost
    closed = _role(table, "closedbook-own", "answer")
    assert (closed["rows"], closed["input_tokens"], closed["cost_usd"]) == (1, 4, 0.01)


def test_glm_cost_comes_from_billing_and_the_classifier_from_its_rows(tmp_path: Path) -> None:
    _tree(tmp_path)
    table = hostedusage35.hosted_usage(tmp_path)
    glm = _role(table, "answer", "judge-glm")
    assert glm["source"] == "billing export (Z.ai)"
    assert glm["input_tokens"] == glm["output_tokens"] == glm["cost_usd"] == ND
    assert glm["calls"] == 3
    kinds = _role(table, "answer", "claim-classifier")
    assert kinds["source"] == "rows"
    assert (kinds["input_tokens"], kinds["output_tokens"], kinds["cost_usd"]) == (9, 1, 0.02)


def test_error_rows_resends_and_closed_calls_per_stage_and_role(tmp_path: Path) -> None:
    _tree(tmp_path)
    table = hostedusage35.hosted_usage(tmp_path)
    assert _role(table, "answer", "answer")["error_rows"] == 1
    assert _role(table, "answer", "ragas-judge")["error_rows"] == 1
    assert _role(table, "answer", "judge-glm")["error_rows"] == 1
    assert _role(table, "answer", "claim-classifier")["error_rows"] == 0
    assert _role(table, "answer", "claim-classifier")["closed_missing"] == 0
    assert _role(table, "answer", "answer")["resent_calls"] == 2
    assert _role(table, "answer", "answer")["closed_missing"] == 1
    assert _role(table, "answer", "judge-glm")["resent_calls"] == 1
    # No summary file: the resends are not defined, not zero.
    assert _role(table, "answer", "ragas-judge")["resent_calls"] == ND


def test_billing_rows_sum_per_provider(tmp_path: Path) -> None:
    one, two = tmp_path / "a.json", tmp_path / "b.json"
    _json(one, [{"provider": "zai", "usd": 1.5}, {"provider": "openrouter", "usd": 2.0}])
    _json(two, [{"provider": "zai", "usd": 0.5}])
    assert hostedusage35.billing_by_provider([one, two]) == {"openrouter": 2.0, "zai": 2.0}
    assert hostedusage35.billing_by_provider([]) == ND


def test_energy_is_closed_gpu_hours_times_board_power() -> None:
    compute = {"stages": [{"closed_pod_hours": 2.0}, {"closed_pod_hours": 3.0}]}
    energy = hostedusage35.energy_estimate(compute)
    assert energy["board_watts"] == 450
    assert energy["kwh"] == 2.25
    assert hostedusage35.energy_estimate(ND) == ND


def test_stops_and_returned_models_are_carried(tmp_path: Path) -> None:
    assert hostedusage35.stops(tmp_path) == []
    _rows(tmp_path / "stops.jsonl", [{"kind": "out_of_credit", "stage": "answer"}])
    assert hostedusage35.stops(tmp_path) == [{"kind": "out_of_credit", "stage": "answer"}]
    assert hostedusage35.returned_models(tmp_path) == ND
    counts = {"answer": {"rows": 3, "differs": 1, "unknown": 0}}
    _json(tmp_path / "join.json", {"returned_model": counts})
    assert hostedusage35.returned_models(tmp_path) == counts


def test_the_report_tables_carry_the_hosted_items(tmp_path: Path) -> None:
    from tests._exp35_fixtures import open_half_b

    reporttables35 = load("reporttables35")
    open_half_b(tmp_path)
    _rows(tmp_path / "answer-scores.jsonl", [])
    # A closed-book answer file only: the other report tables read no closed-book rows.
    cb = _run(tmp_path, kind="closedbook-own")
    _rows(cb / "answer.jsonl", [{"qid": "1", "status": "ok", "input_tokens": 4, "cost_usd": 0.01}])
    _rows(tmp_path / "stops.jsonl", [{"kind": "out_of_credit", "stage": "answer"}])
    bill = tmp_path / "bill.json"
    _json(bill, [{"provider": "zai", "usd": 3.0}])
    records = tmp_path / "pod1.jsonl"
    _rows(
        records,
        [
            {"started_at": "2026-12-01T00:00:00Z", "command": "x --stage ingest"},
            {"started_at": "2026-12-01T02:00:00Z", "command": "x --stage seal"},
        ],
    )
    argv = ["--out-dir", str(tmp_path), "--records", str(records), "--billing", str(bill)]
    assert reporttables35.main(argv) == 0
    hosted = json.loads((tmp_path / "report-tables.json").read_text())["hosted"]
    assert _role(hosted["usage"], "closedbook-own", "answer")["input_tokens"] == 4
    assert hosted["billing_by_provider"] == {"zai": 3.0}
    assert hosted["energy"]["kwh"] == 0.9  # 2 closed GPU hours at 450 W
    assert hosted["stops"] == [{"kind": "out_of_credit", "stage": "answer"}]
    assert hosted["returned_model"] == ND  # no join.json


def test_closed_calls_are_not_defined_when_a_summary_is_missing(tmp_path: Path) -> None:
    _tree(tmp_path)
    table = hostedusage35.hosted_usage(tmp_path)
    assert _role(table, "answer", "ragas-judge")["closed_missing"] == ND
    assert _role(table, "answer", "judge-glm")["closed_missing"] == 0  # measured zero


def test_non_finite_billing_amounts_are_refused(tmp_path: Path) -> None:
    import pytest

    bad = tmp_path / "bad.json"
    _json(bad, [{"provider": "zai", "usd": "NaN"}])
    with pytest.raises(ValueError, match="not a finite amount"):
        hostedusage35.billing_by_provider([bad])
