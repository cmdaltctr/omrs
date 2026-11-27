"""Hosted-call items of the Experiment 35 compute table (task 16.20; prereg sections 17, 21).

Each function reads saved files only; a value that is not defined reads
:data:`NOT_DEFINED`.

- :func:`hosted_usage`: per stage (the output kind, for example ``answer`` or
  ``closedbook-own``) and role, the rows, calls, error rows, harness resends
  (``resent_calls``), calls closed as missing after the resend cap, and the
  tokens and cost. The answer and Ragas rows record tokens and cost per call.
  The GLM-5.3 claim checks and the claim classifier record none, so their
  tokens and cost come from the provider billing exports (amendment A18 item 35).
  A sum is defined only when every call reported the figure.
- :func:`billing_by_provider`: the ``usd`` of the billing rows per provider.
- :func:`energy_estimate`: closed GPU pod hours times the board power of the
  RTX 4090 (450 W), in kWh (Strubell et al. 2019; Lacoste et al. 2019).
- :func:`record_stop` and :func:`stops`: every rate-limit and ``out_of_credit``
  stop (``stops.jsonl``, written by ``run_arms.py``).
- :func:`returned_models`: the returned-model counts per role from ``join.json``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from outputs35 import read_rows

NOT_DEFINED = "not defined"
#: RTX 4090 board power in watts (NVIDIA specification), the only GPU type (protocol 9.3).
BOARD_WATTS = 450
#: Row file, its role, its summary file, and where its tokens and cost come from.
ROLES = (
    ("answer.jsonl", "answer", "answer-summary.json", "rows"),
    ("ragas.jsonl", "ragas-judge", "ragas-summary.json", "rows"),
    ("judge-chat.jsonl", "judge-glm", "judge-chat-summary.json", "billing export"),
    ("claim-kinds.jsonl", "claim-classifier", "claimkinds-summary.json", "billing export"),
)


def _calls(role: str, row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the hosted calls one row holds, each with its figures and error."""
    if role == "ragas-judge":
        return list(row.get("calls") or [])
    if role == "judge-glm":
        return [v.get("call") or {} for v in row.get("verdicts") or []]
    return [row]


def _is_error(call: Mapping[str, Any]) -> bool:
    return call.get("status") == "error" or bool(call.get("error"))


def _first(call: Mapping[str, Any], names: Sequence[str]) -> float | None:
    return next((call[n] for n in names if isinstance(call.get(n), (int, float))), None)


def _total(calls: Sequence[Mapping[str, Any]], *names: str) -> float | str:
    values = [_first(c, names) for c in calls]
    if not values or None in values:
        return NOT_DEFINED
    return round(sum(v for v in values if v is not None), 12)


def _empty(stage: str, role: str, source: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "role": role,
        "source": source,
        "rows": 0,
        "calls": [],
        "error_rows": 0,
        "resent_calls": 0,
        "closed_missing": 0,
        "summaries_missing": 0,
    }


def hosted_usage(out: Path) -> dict[str, Any]:
    """Return per stage and role the hosted calls, errors, resends, tokens and cost."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for name, role, summary_name, source in ROLES:
        for path in sorted(out.glob(f"*/*/*/run*/{name}")):
            stage = path.parts[-4]
            per = found.setdefault((stage, role), _empty(stage, role, source))
            for row in read_rows(path):
                if row.get("missing"):
                    continue
                calls = _calls(role, row)
                per["rows"] += 1
                per["calls"].extend(calls)
                per["error_rows"] += any(_is_error(c) for c in calls)
            summary_path = path.parent / summary_name
            if summary_path.is_file():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                per["resent_calls"] += int(summary.get("resent_calls") or 0)
                per["closed_missing"] += len(summary.get("closed_missing") or [])
            else:
                per["summaries_missing"] += 1
    rows = []
    for _, per in sorted(found.items()):
        calls = per.pop("calls")
        by_rows = per["source"] == "rows"
        rows.append(
            {
                **per,
                "calls": len(calls),
                "resent_calls": NOT_DEFINED if per["summaries_missing"] else per["resent_calls"],
                "input_tokens": _total(calls, "input_tokens") if by_rows else NOT_DEFINED,
                "output_tokens": _total(calls, "output_tokens") if by_rows else NOT_DEFINED,
                "cost_usd": _total(calls, "cost_usd", "reported_cost_usd")
                if by_rows
                else NOT_DEFINED,
            }
        )
    return {"roles": rows}


def billing_by_provider(paths: Iterable[Path]) -> dict[str, float] | str:
    """Return the billed ``usd`` per provider, else "not defined" without billing files."""
    totals: dict[str, float] = {}
    for path in paths:
        for row in json.loads(path.read_text(encoding="utf-8")):
            provider = str(row["provider"])
            totals[provider] = round(totals.get(provider, 0.0) + float(row["usd"]), 12)
    return dict(sorted(totals.items())) if totals else NOT_DEFINED


def energy_estimate(compute: Mapping[str, Any] | str) -> dict[str, Any] | str:
    """Return the closed GPU pod hours times the board power, in kWh."""
    if not isinstance(compute, Mapping):
        return NOT_DEFINED
    hours = sum(float(s["closed_pod_hours"]) for s in compute["stages"])
    return {"gpu_hours": hours, "board_watts": BOARD_WATTS, "kwh": hours * BOARD_WATTS / 1000}


def record_stop(args: Any, stop: BaseException) -> None:
    """Append one stop to ``<out-dir>/stops.jsonl`` (``run_arms.py`` calls it on exit code 5)."""
    folder = Path(args.out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    line = {
        "kind": getattr(stop, "kind", "rate_limit"),
        "stage": args.stage,
        "dataset": args.dataset,
        "setup": getattr(args, "setup", None) or getattr(args, "index", None),
        "message": str(stop),
        "at": datetime.now(UTC).isoformat(),
    }
    with (folder / "stops.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def stops(out: Path) -> list[dict[str, Any]]:
    """Return every rate-limit and ``out_of_credit`` stop the runner saved."""
    return read_rows(out / "stops.jsonl")


def returned_models(out: Path) -> dict[str, Any] | str:
    """Return the returned-model counts per role from ``join.json``, else "not defined"."""
    path = out / "join.json"
    if not path.is_file():
        return NOT_DEFINED
    return json.loads(path.read_text(encoding="utf-8")).get("returned_model", NOT_DEFINED)
