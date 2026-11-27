"""Experiment 35 classifier gate reference label (A18, prereg 11.1 and 11.3).

The gate scores against the reference label: the agreed L1 and L2 label where
both labelled the claim, else L1's label. L2 labels only a staged subset of
the claim kinds, so the gate command takes the subset through ``--l2-items``.
A disagreement that discussion did not resolve becomes "can't tell" and is
left out of the scores.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import load
from tests._exp35_label_fixtures import write_rows
from tests.test_experiment35_refusals import _draw

refusals35 = load("refusals35")


def _setup(tmp_path: Path) -> tuple[Path, list[str], dict[str, bool]]:
    drawn = _draw(tmp_path)
    out = tmp_path / "gate"
    refusals35.write_sample(out, drawn)
    keys = [i["claim_key"] for i in drawn["items"]]
    flags = {i["claim_key"]: i["flagged"] for i in drawn["items"]}
    kinds = [
        {"claim_key": k, "kind": "refusal" if flags[k] else "factual", "version": "v1"}
        for k in keys
    ]
    write_rows(out / "sample-kinds.jsonl", kinds)
    return out, [i["item_id"] for i in drawn["items"]], flags


def _write(path: Path, labeller: str, labels: dict[str, str]) -> Path:
    path.write_text(json.dumps({"set": "claim_kinds", "labeller": labeller, "labels": labels}))
    return path


def _labels(out: Path, ids: list[str], flags: dict[str, bool]) -> tuple[Path, Path, Path, str]:
    drawn = json.loads((out / "sample.json").read_text())
    flagged = {i["item_id"]: flags[i["claim_key"]] for i in drawn["items"]}
    l1 = {i: "refusal" if flagged[i] else "factual" for i in ids}
    subset = [i for i in ids if flagged[i]][:3] + [i for i in ids if not flagged[i]][:2]
    odd = subset[0]  # L2 disagrees with L1 on this claim only
    l2 = {i: ("factual" if i == odd else l1[i]) for i in subset}
    files = (
        _write(out / "labels-L1.json", "L1", l1),
        _write(out / "labels-L2.json", "L2", l2),
        out / "l2-items.json",
    )
    files[2].write_text(json.dumps({"claim_kinds": subset}))
    return (*files, odd)


def _gate(out: Path, *extra: str) -> dict:
    argv = ["gate", "--out-dir", str(out), "--labels", str(out / "labels-L1.json")]
    argv += ["--labels", str(out / "labels-L2.json"), "--l2-items", str(out / "l2-items.json")]
    assert refusals35.main([*argv, *extra]) == 0
    return json.loads((out / "gate.json").read_text())


def test_gate_accepts_a_staged_l2_subset_and_counts_an_unresolved_disagreement(
    tmp_path: Path,
) -> None:
    out, ids, flags = _setup(tmp_path)
    _labels(out, ids, flags)
    gate = _gate(out)
    assert gate["labellers"] == ["L1", "L2"]
    assert gate["unresolved_count"] == 1
    assert gate["cant_tell_count"] == 1  # the disagreement is "can't tell", left out
    assert gate["scored"] == gate["labelled"] - 1


def test_a_resolved_label_replaces_the_disagreement(tmp_path: Path) -> None:
    out, ids, flags = _setup(tmp_path)
    *_, odd = _labels(out, ids, flags)
    resolved = out / "resolved.json"
    resolved.write_text(json.dumps({odd: "refusal"}))
    gate = _gate(out, "--resolved", str(resolved))
    assert gate["unresolved_count"] == 0 and gate["cant_tell_count"] == 0


def test_without_l2_items_a_partial_l2_file_is_refused(tmp_path: Path) -> None:
    out, ids, flags = _setup(tmp_path)
    _labels(out, ids, flags)
    argv = ["gate", "--out-dir", str(out), "--labels", str(out / "labels-L1.json")]
    with pytest.raises(labelpage35_error()):
        refusals35.main([*argv, "--labels", str(out / "labels-L2.json")])


def labelpage35_error() -> type[Exception]:
    return load("labelpage35").LabelError
