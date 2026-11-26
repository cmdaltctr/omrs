"""Experiment 35 claim-kind gate (review B2; pre-registration sections 11.1 and 12).

No claim-kind result is used until classifier gate 3 passes (``gate.json``
``pass: true`` with a matching version). Until then the registered fallback
applies: every cited claim counts, and rows 12, 13, 16 and 17 are "not testable".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests import _exp35_join_fixtures as jfx
from tests import _exp35_mainrun_fixtures as mfx
from tests._exp35_fixtures import load, open_half_b

join35 = load("join35")
kindgate35 = load("kindgate35")
labels35 = load("labels35")
factorial35 = load("factorial35")

FAITH = "faithfulness_glm_factual"


def _gate(tmp_path: Path, passed: bool, version: str = "v") -> Path:
    path = tmp_path / "gate" / "gate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pass": passed, "version": version}))
    return path


@pytest.mark.parametrize(
    ("body", "version"),
    [(None, None), ({"pass": False, "version": "v"}, None), ({"pass": True, "version": "v"}, "v")],
)
def test_only_a_passed_gate_gives_a_version(tmp_path: Path, body, version) -> None:
    path = tmp_path / "gate.json"
    if body is not None:
        path.write_text(json.dumps(body))
    assert kindgate35.gate_version(path) == version


# --- the join -----------------------------------------------------------------------------


def _refusal_first_claim(out: Path) -> None:
    claimkinds35 = load("claimkinds35")
    for path in out.glob("*/answer/*/run*/claim-kinds.jsonl"):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            if row["claim_key"] == claimkinds35.claim_key(row["qid"], "Fact one."):
                row["kind"] = "refusal"
        jfx.write_rows(path, rows)


def _join(tmp_path: Path, gate: Path | None) -> tuple[dict, list[dict]]:
    out, experiment = tmp_path / "out", tmp_path / "exp"
    pods = jfx.build(out, experiment)
    _refusal_first_claim(out)
    report = join35.join(
        out,
        experiment=experiment,
        records=pods,
        search_setups=jfx.SETUPS,
        answer_setups=jfx.SETUPS,
        datasets=jfx.DATASETS,
        requested=jfx.REQUESTED,
        gate=gate,
    )
    lines = (out / "answer-scores.jsonl").read_text().splitlines()
    return report, [json.loads(line) for line in lines]


def test_a_passed_gate_leaves_out_refusal_claims(tmp_path: Path) -> None:
    report, scores = _join(tmp_path, _gate(tmp_path, True))
    assert {s[FAITH] for s in scores} == {None}  # the one cited claim is a refusal
    assert report["claim_kinds"]["pass"] is True and report["claim_kinds"]["version"] == "v"


@pytest.mark.parametrize("passed", [False, None])
def test_without_a_passed_gate_every_cited_claim_counts(tmp_path: Path, passed) -> None:
    gate = None if passed is None else _gate(tmp_path, passed)
    report, scores = _join(tmp_path, gate)
    assert {s[FAITH] for s in scores} == {1.0}  # kinds unused: the refusal kind is ignored
    assert report["claim_kinds"] == {
        "gate": None if gate is None else str(gate),
        "pass": False,
        "version": None,
        "rule": kindgate35.FALLBACK,
    }


def test_a_kind_of_another_version_refuses_under_a_passed_gate(tmp_path: Path) -> None:
    with pytest.raises(kindgate35.KindGateError, match="version"):
        _join(tmp_path, _gate(tmp_path, True, version="other"))


# --- the faithfulness gate pool -----------------------------------------------------------


def test_the_pool_needs_kinds_of_the_passed_version_only(tmp_path: Path) -> None:
    out = tmp_path / "out"
    questions = mfx.build(out)
    labels35.require_kinds(out, None)  # fallback: no kind file needed
    pool = labels35.faithfulness_claims(out, questions, None)
    mfx.write_kinds(out, lambda q, i: "refusal")  # fixture version v1
    assert len(labels35.faithfulness_claims(out, questions, None)) == len(pool)  # kinds ignored
    labels35.require_kinds(out, "v1")
    assert labels35.faithfulness_claims(out, questions, "v1") == []
    with pytest.raises(kindgate35.KindGateError):
        labels35.require_kinds(out, "v2")


# --- the confirmatory analysis ------------------------------------------------------------


def test_a_passed_gate_fails_the_join_of_a_run_without_its_kinds_file(tmp_path: Path) -> None:
    # PR 227 review: a missing file must not read as "no refusals" under a passed gate.
    out, experiment = tmp_path / "out", tmp_path / "exp"
    pods = jfx.build(out, experiment)
    gone = sorted(out.glob("*/answer/*/run*/claim-kinds.jsonl"))[0]
    gone.unlink()
    report = join35.join(
        out,
        experiment=experiment,
        records=pods,
        search_setups=jfx.SETUPS,
        answer_setups=jfx.SETUPS,
        datasets=jfx.DATASETS,
        requested=jfx.REQUESTED,
        gate=_gate(tmp_path, True),
    )
    assert report["ok"] is False
    assert any("claim-kinds.jsonl" in f for f in report["failures"])
    assert not (out / "answer-scores.jsonl").exists()


def test_the_claimkinds_stage_writes_its_file_for_a_run_with_no_claims(tmp_path: Path) -> None:
    # The join check above needs the file even when a run has no claims to classify.
    import asyncio

    claimkinds35 = load("claimkinds35")
    (tmp_path / "answer.jsonl").write_text(json.dumps({"qid": "q1", "answer": ""}) + "\n")
    code = asyncio.run(
        claimkinds35.claimkinds_stage(
            tmp_path, {"q1": "Q?"}, None, prompt="p", version="v", env_check=lambda _: None
        )
    )
    assert code == 0 and (tmp_path / "claim-kinds.jsonl").is_file()


def test_a_passed_gate_accepts_empty_kinds_files_from_runs_with_no_claims(tmp_path: Path) -> None:
    out, experiment = tmp_path / "out", tmp_path / "exp"
    pods = jfx.build(out, experiment)
    for path in out.glob("*/answer/*/run*/claim-kinds.jsonl"):
        path.write_text("")
    report = join35.join(
        out,
        experiment=experiment,
        records=pods,
        search_setups=jfx.SETUPS,
        answer_setups=jfx.SETUPS,
        datasets=jfx.DATASETS,
        requested=jfx.REQUESTED,
        gate=_gate(tmp_path, True),
    )
    assert not any("claim-kinds.jsonl" in f for f in report["failures"])
    assert (out / "answer-scores.jsonl").exists()


def _confirm(tmp_path: Path, gate: Path | None, joined_version: str | None) -> dict:
    base = load("factorial35")
    from tests.test_experiment35_factorial import FAST, _answers, _search

    (tmp_path / "faithfulness-gate.json").write_text(json.dumps({"not_testable_rows": []}))
    (tmp_path / "correctness-gate.json").write_text(
        json.dumps({"result": {"not_testable_rows": {}}})
    )
    open_half_b(tmp_path)
    kinds = {"pass": joined_version is not None, "version": joined_version}
    (tmp_path / "join.json").write_text(json.dumps({"ok": True, "claim_kinds": kinds}))
    return base.write_confirmatory(
        tmp_path / "factorial.json",
        _search(),
        _answers(),
        label_dir=tmp_path,
        root=tmp_path,
        kind_gate=gate,
        **FAST,
    )


def test_a_failed_gate_makes_the_faithfulness_rows_not_testable(tmp_path: Path) -> None:
    result = _confirm(tmp_path, _gate(tmp_path, False), None)
    for dataset in ("bioasq", "financebench", "freshstack"):
        rows = {r["row"]: r for r in result["datasets"][dataset]}
        assert all(rows[n]["not_testable"] for n in (12, 13, 16, 17))
        assert not rows[14]["not_testable"]
        if dataset != "bioasq":  # BioASQ's family holds rows 1 to 8 only
            assert rows[12]["holm_p"] == 1.0 and rows[16]["holm_p"] == 1.0
    saved = json.loads((tmp_path / "factorial.json").read_text())
    assert saved["classifier_gate"]["pass"] is False
    assert saved["classifier_gate"]["not_testable_rows"] == [12, 13, 16, 17]


def test_a_passed_gate_keeps_the_faithfulness_rows(tmp_path: Path) -> None:
    result = _confirm(tmp_path, _gate(tmp_path, True), "v")
    rows = {r["row"]: r for r in result["datasets"]["freshstack"]}
    assert not rows[12]["not_testable"]


@pytest.mark.parametrize(("passed", "joined"), [(True, None), (False, "v")])
def test_refuses_answer_scores_joined_under_another_kind_rule(
    tmp_path: Path, passed: bool, joined: str | None
) -> None:
    with pytest.raises(kindgate35.KindGateError, match="join35.py --gate"):
        _confirm(tmp_path, _gate(tmp_path, passed), joined)
    assert not (tmp_path / "factorial.json").exists()
