"""What the join derives from saved answer runs (tasks 6.1, 15.9, 16.29; H-28).

* :func:`answer_scores`: one answer-score record per dataset, setup, run and
  question, with the keys ``factorial35`` reads (``faithfulness_glm_factual``,
  ``ragas_answer_correctness``, ``run``, ``cut_tokens``, ``qid``, ``doc_id``),
  ``evidence_tokens`` (the realised total ``reporttables35`` reads)
  and the uncited-segment sensitivity value.
* :func:`returned_models`: per hosted role, rows whose returned model differs
  from the requested one.
* :func:`rebuild_traces`: a trace line that a stop lost is rebuilt from its row.

Scoring rules (pre-registration sections 6 and 12):

- ``faithfulness_glm_factual``: GLM-5.3 (``judge-chat``) supported share of the
  answer's cited claims whose saved kind is not ``refusal`` (an unclassified
  claim counts as factual). Kinds are used only under a passed classifier gate
  (``kindgate35``); without one every cited claim counts (registered fallback).
  An ``unparseable`` verdict is returned content, so it counts not supported;
  ``unparseable_verdicts`` counts them. ``None`` when the answer has no such
  claim, or its checker row is missing.
- ``faithfulness_glm_factual_uncited`` (sensitivity): the same supported
  count over cited factual claims plus uncited segments whose saved kind
  (``claim-kinds.jsonl`` rows with ``uncited: true``) is not ``refusal``.
- ``ragas_answer_correctness``: ``metrics.ragas_answer_correctness.score`` of
  the Ragas row. An answer still missing, or with no text, scores 0.
- ``unjudged``: the metric keys whose checker row or Ragas metric closed
  missing on an answer that exists. Such a value is ``None`` but is not a
  no-claim run: the analysis drops the whole question-setup cell and counts it.
- ``not_defined``: ``ragas_answer_correctness`` when its Ragas call returned no
  defined score (NaN or no number; ``not_defined`` in the Ragas row). That is
  returned content, so it is neither unjudged nor 0: the run has no value and
  is left out of the run mean, as a no-claim run is for faithfulness.
- ``doc_id``: the question's gold document (FinanceBench), from the caller.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import claimkinds35
import kindgate35
import segments35
from outputs35 import read_rows

from omrs.core.answer.verify import split_claims

#: Row file of a run folder to its hosted role (``plan.json`` ``runtime.references``).
ROLE_FILES = {
    "answer.jsonl": "answer",
    "ragas.jsonl": "ragas-judge",
    "judge-chat.jsonl": "judge-glm",
    "claim-kinds.jsonl": "claim-classifier",
}
#: Row file to the trace ``stage`` its rows carry (``search35``, ``answers35``, ``judges35``).
TRACED = {
    "search.jsonl": "search",
    "answer.jsonl": "answer",
    "judge-chat.jsonl": "judge-chat",
    "judge-clef_flash.jsonl": "judge-clef_flash",
}
REFUSAL = "refusal"
UNPARSEABLE = "unparseable"
CORRECT = "ragas_answer_correctness"
FAITH_KEYS = ("faithfulness_glm_factual", "faithfulness_glm_factual_uncited")


def _share(supported: int, total: int) -> float | None:
    return supported / total if total else None


def _faithfulness(
    answer: Mapping[str, Any], judge: Mapping[str, Any], kinds: Mapping[str, Any]
) -> tuple[float | None, float | None, int]:
    """Return the two faithfulness values and the count of unparseable verdicts."""
    qid = str(answer["qid"])
    evidence = len(answer.get("evidence") or [])
    claims = split_claims(answer.get("answer") or "", evidence)
    verdicts = {v["index"]: v.get("verdict") for v in judge.get("verdicts") or []}
    factual = [
        i
        for i, (text, _) in enumerate(claims)
        if kinds.get((claimkinds35.claim_key(qid, text), False)) != REFUSAL
    ]
    # Returned content is final (section 12): an unparseable verdict counts not supported.
    supported = sum(verdicts.get(i) == "supported" for i in factual)
    unparseable = sum(verdicts.get(i) == UNPARSEABLE for i in factual)
    uncited = [
        t
        for t in segments35.uncited_segments(answer.get("answer") or "", evidence)
        if kinds.get((claimkinds35.claim_key(qid, t), True)) != REFUSAL
    ]
    shares = _share(supported, len(factual)), _share(supported, len(factual) + len(uncited))
    return *shares, unparseable


def _correctness(answer: Mapping[str, Any], row: Mapping[str, Any] | None) -> float | None:
    """Return the correctness, or None when no score was saved (see ``_unjudged``).

    An answer with no text scores 0: Ragas gets no text, as for a missing answer.
    """
    if answer.get("missing") or not answer.get("answer"):
        return 0.0
    metric = ((row or {}).get("metrics") or {}).get(CORRECT) or {}
    return metric.get("score")


def _unjudged(answer: Mapping[str, Any], judge: Any, ragas: Any) -> list[str]:
    """Return the metrics whose checker or Ragas call closed missing (section 12)."""
    if answer.get("missing"):
        return []
    found = []
    if judge is None or judge.get("missing"):
        found += list(FAITH_KEYS)
    closed = {u["metric"] for u in (ragas or {}).get("unjudged") or [] if u.get("closed")}
    if answer.get("answer") and (ragas is None or CORRECT in closed):
        found.append(CORRECT)
    return found


def _not_defined(ragas: Mapping[str, Any] | None) -> list[str]:
    """Return the metric keys whose Ragas call returned no defined score (NaN or no number)."""
    metric = ((ragas or {}).get("metrics") or {}).get(CORRECT) or {}
    return [CORRECT] if metric.get("not_defined") else []


def answer_scores(
    run_dir: Path,
    dataset: str,
    setup: str,
    run: int,
    documents: Mapping[str, str] | None = None,
    *,
    kinds_version: str | None,
) -> list[dict[str, Any]]:
    """Return the answer-score records of one answer run, in answer order.

    Args:
        run_dir: The answer run folder.
        dataset: Dataset name.
        setup: Answer setup name.
        run: Run number.
        documents: FinanceBench only: question ID to its gold document. The
            record's ``doc_id`` comes from here, never from the answer row (a
            closed-missing row has none).
        kinds_version: The passed classifier gate's version (``kindgate35.gate_version``);
            None applies the registered fallback: no kind filter.

    Raises:
        kindgate35.KindGateError: A saved kind has another version.
    """
    judges = {str(r["qid"]): r for r in read_rows(run_dir / "judge-chat.jsonl")}
    ragas = {str(r["qid"]): r for r in read_rows(run_dir / "ragas.jsonl")}
    kinds = kindgate35.saved_kinds(run_dir, kinds_version)
    records = []
    for answer in read_rows(run_dir / "answer.jsonl"):
        qid = str(answer["qid"])
        judge = judges.get(qid)
        unjudged = _unjudged(answer, judge, ragas.get(qid))
        judged = not answer.get("missing") and FAITH_KEYS[0] not in unjudged
        faith, sensitivity, unparseable = (
            _faithfulness(answer, judge, kinds) if judged else (None, None, 0)
        )
        segments, uncited = segments35.segment_counts(
            answer.get("answer") or "", len(answer.get("evidence") or [])
        )
        records.append(
            {
                "dataset": dataset,
                "setup": setup,
                "run": run,
                "qid": qid,
                "doc_id": (documents or {}).get(qid),
                "cut_tokens": answer.get("cut_tokens"),
                "evidence_tokens": answer.get("evidence_tokens"),
                "faithfulness_glm_factual": faith,
                "faithfulness_glm_factual_uncited": sensitivity,
                CORRECT: _correctness(answer, ragas.get(qid)),
                "unjudged": unjudged,
                "not_defined": [] if answer.get("missing") else _not_defined(ragas.get(qid)),
                "unparseable_verdicts": unparseable,
                "segments": segments,
                "uncited_segments": uncited,
            }
        )
    return records


def marked_runs(
    records: Sequence[Mapping[str, Any]], field: str, metrics: Sequence[str]
) -> dict[str, dict[str, dict[str, int]]]:
    """Return per dataset, setup and metric the runs whose ``field`` list names the metric."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    for r in records:
        per = out.setdefault(r["dataset"], {}).setdefault(r["setup"], dict.fromkeys(metrics, 0))
        for metric in r.get(field) or ():
            per[metric] += 1
    return out


def unparseable_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Return per dataset and setup the unparseable verdicts over runs and questions."""
    out: dict[str, dict[str, int]] = {}
    for r in records:
        per = out.setdefault(r["dataset"], {})
        per[r["setup"]] = per.get(r["setup"], 0) + int(r["unparseable_verdicts"])
    return out


def uncited_share(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float | None]]:
    """Return ``uncited_segment_share`` per dataset and setup, pooled over runs and questions."""
    totals: dict[tuple[str, str], list[int]] = {}
    for r in records:
        pair = totals.setdefault((r["dataset"], r["setup"]), [0, 0])
        pair[0] += r["uncited_segments"]
        pair[1] += r["segments"]
    out: dict[str, dict[str, float | None]] = {}
    for (dataset, setup), (uncited, total) in sorted(totals.items()):
        out.setdefault(dataset, {})[setup] = _share(uncited, total)
    return out


def _returned(row: Mapping[str, Any]) -> list[str]:
    found = row.get("model_returned")
    if found is None:
        calls = [v.get("call") or {} for v in row.get("verdicts") or []]
        found = [c["model_returned"] for c in calls if c.get("model_returned")]
    return [found] if isinstance(found, str) else list(found or [])


def returned_models(
    run_dirs: Sequence[Path], requested: Mapping[str, str]
) -> dict[str, dict[str, int]]:
    """Count per role the rows whose returned model differs from the requested one (task 15.9).

    A row with no returned model is counted under ``unknown``.
    """
    counts = {role: {"rows": 0, "differs": 0, "unknown": 0} for role in ROLE_FILES.values()}
    for run_dir in run_dirs:
        for name, role in ROLE_FILES.items():
            for row in read_rows(run_dir / name):
                if row.get("missing"):
                    continue
                found = _returned(row)
                counts[role]["rows"] += 1
                if not found:
                    counts[role]["unknown"] += 1
                elif any(m != requested.get(role) for m in found):
                    counts[role]["differs"] += 1
    return counts


def _append(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def rebuild_traces(run_dir: Path, dataset: str) -> tuple[int, list[str]]:
    """Rebuild each lost trace line of a saved row; return the count and the failures.

    The run context fields come from the first trace line of the file. A row
    whose question is not in its stage key's ``qids`` is a failure.
    """
    path = run_dir / "traces.jsonl"
    lines = read_rows(path)
    context = (
        {
            k: lines[0].get(k)
            for k in (
                "benchmark_revision",
                "run_id",
                "arm",
                "repetition",
                "effective_settings",
                "model_identities",
            )
        }
        if lines
        else {}
    )
    seen = {(t.get("stage"), str(t.get("question_id"))) for t in lines}
    added: list[dict[str, Any]] = []
    failures: list[str] = []
    for name, stage in TRACED.items():
        key = run_dir / f"{name.removesuffix('.jsonl')}.key.json"
        items = set(json.loads(key.read_text(encoding="utf-8"))["qids"]) if key.exists() else set()
        for row in read_rows(run_dir / name):
            qid = str(row["qid"])
            if qid not in items:
                failures.append(f"{run_dir}: {name} row {qid} has no matching item in {key.name}")
            elif (stage, qid) not in seen:
                added.append(_trace_row(context, dataset, stage, row))
                seen.add((stage, qid))
    if added:
        _append(path, added)
    return len(added), failures


def _trace_row(
    context: Mapping[str, Any], dataset: str, stage: str, row: Mapping[str, Any]
) -> dict[str, Any]:
    from experiments._lib.trace import D8_FIELDS

    error = row.get("error") if row.get("missing") else None
    found = {
        **context,
        "dataset": dataset,
        "question_id": str(row["qid"]),
        "stage": stage,
        "status": "error" if error else "ok",
        "error": error,
    }
    return {name: found.get(name) for name in D8_FIELDS}
