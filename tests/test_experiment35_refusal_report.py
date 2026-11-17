"""Experiment 35 refusal report on a joined fixture folder (task 8.9).

Fixture: one dataset, setups S1 and S2, runs 1 and 2, questions q1 to q3.
Claims: F1, F2, F3 factual (F2 is "mixed" in S1 run 2), R1 and R2 refusals.

S1 run 1: q1 [F1, R1], q2 [F2], q3 [R2]; chat: q1 s,u; q2 u; q3 u; clef: q1 s,s; q2 u; q3 s.
S1 run 2: same, but chat says q2 s.
S2 run 1: q1 [F1]; q2 missing answer; q3 [F3] with no chat row (unjudged).
S2 run 2: q1 [F1], q2 [F2], q3 [F3]; every verdict s.

Every expected number below is worked out by hand in its test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.stats_d6 import wilson
from tests._exp35_fixtures import load
from tests._exp35_label_fixtures import answer_row, judge_row, write_rows

report = load("refusalreport35")
bootstrap35 = load("bootstrap35")
claimkinds35 = load("claimkinds35")

TEXT = {
    "F1": "Alpha is beta",
    "F2": "Delta is epsilon",
    "F3": "Eta is theta",
    "R1": "The sources do not cover gamma",
    "R2": "The sources do not cover zeta",
}
KIND = {"F1": "factual", "F2": "factual", "F3": "factual", "R1": "refusal", "R2": "refusal"}
S1, S2 = "e4b-c512-roff-hoff", "e4b-c1024-roff-hoff"

# setup -> run -> qid -> list of (claim, chat verdict, clef verdict); None answer = missing
SPEC: dict[str, dict[int, dict[str, Any]]] = {
    S1: {
        1: {
            "q1": [("F1", "s", "s"), ("R1", "u", "s")],
            "q2": [("F2", "u", "u")],
            "q3": [("R2", "u", "s")],
        },
        2: {
            "q1": [("F1", "s", "s"), ("R1", "u", "s")],
            "q2": [("F2", "s", "u")],
            "q3": [("R2", "u", "s")],
        },
    },
    S2: {
        1: {"q1": [("F1", "s", "s")], "q2": None, "q3": [("F3", None, "s")]},
        2: {"q1": [("F1", "s", "s")], "q2": [("F2", "s", "s")], "q3": [("F3", "s", "s")]},
    },
}
VERDICT = {"s": "supported", "u": "unsupported"}


def _build(tmp_path: Path, *, kinds_version: str = "v1", drop_kind: tuple | None = None) -> Path:
    out = tmp_path / "out"
    (out).mkdir(parents=True)
    (out / "join.json").write_text(json.dumps({"ok": True}))
    for setup, runs in SPEC.items():
        for run, per_q in runs.items():
            folder = out / "bioasq" / "answer" / setup / f"run{run}"
            answers, chat, clef, kinds = [], [], [], []
            for qid, claims in per_q.items():
                if claims is None:
                    answers.append({"qid": qid, "status": "error", "answer": None, "missing": True})
                    continue
                row = answer_row(qid, [TEXT[c] for c, _, _ in claims])
                answers.append(row)
                if all(v is not None for _, v, _ in claims):
                    chat.append(judge_row(qid, [VERDICT[v] for _, v, _ in claims], "chat"))
                clef.append(judge_row(qid, [VERDICT[v] for _, _, v in claims], "clef_flash"))
                for i, (c, _, _) in enumerate(claims):
                    if drop_kind == (setup, run, qid, c):
                        continue
                    kind = "mixed" if (setup, run, c) == (S1, 2, "F2") else KIND[c]
                    key = claimkinds35.claim_key(qid, claimkinds35.answer_claims(row)[i])
                    kinds.append(
                        {
                            "claim_key": key,
                            "qid": qid,
                            "index": i,
                            "kind": kind,
                            "version": kinds_version,
                        }
                    )
            write_rows(folder / "answer.jsonl", answers)
            write_rows(folder / "judge-chat.jsonl", chat)
            write_rows(folder / "judge-clef_flash.jsonl", clef)
            write_rows(folder / "claim-kinds.jsonl", kinds)
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"pass": True, "version": "v1"}))
    return out


def _run(tmp_path: Path, **kw: Any) -> dict[str, Any]:
    out = _build(tmp_path, **kw)
    report.write_report(out, gate_path=tmp_path / "gate.json", n_boot=200)
    return json.loads((out / "refusals.json").read_text())


# --- refusals -------------------------------------------------------------------------------


def test_refuses_without_a_passing_join(tmp_path: Path) -> None:
    out = _build(tmp_path)
    (out / "join.json").write_text(json.dumps({"ok": False}))
    with pytest.raises(report.ReportError, match="join"):
        report.write_report(out, gate_path=tmp_path / "gate.json", n_boot=200)


def test_refuses_without_a_frozen_classifier_version(tmp_path: Path) -> None:
    out = _build(tmp_path)
    (tmp_path / "gate.json").write_text(json.dumps({"pass": False, "version": "v1"}))
    with pytest.raises(report.ReportError, match="classifier"):
        report.write_report(out, gate_path=tmp_path / "gate.json", n_boot=200)


def test_refuses_kinds_from_another_classifier_version(tmp_path: Path) -> None:
    out = _build(tmp_path, kinds_version="v0")
    with pytest.raises(report.ReportError, match="version"):
        report.write_report(out, gate_path=tmp_path / "gate.json", n_boot=200)


# --- kinds per run ---------------------------------------------------------------------------


def test_counts_claim_texts_with_different_kinds_in_different_runs(tmp_path: Path) -> None:
    assert _run(tmp_path)["kind_disagreements"] == {"bioasq": 1}  # F2: factual and mixed


# --- primary faithfulness and missing outcomes -----------------------------------------------


def _cell(result: dict[str, Any], table: str, checker: str, setup: str) -> dict[str, Any]:
    return result["faithfulness"][table][checker]["bioasq"][setup]


def test_primary_faithfulness_uses_factual_and_mixed_claims_with_complete_cases(
    tmp_path: Path,
) -> None:
    r = _run(tmp_path)
    # chat S1: q1 (1 + 1) / 2 = 1; q2 (0 + 1) / 2 = 0.5; q3 refusals only, no factual claim.
    s1 = _cell(r, "primary", "chat", S1)
    assert s1["mean"] == pytest.approx(0.75)
    assert (s1["n"], s1["excluded_no_claim"], s1["excluded_unjudged"]) == (2, 1, 0)
    # chat S2: q1 1; q2 run 1 missing (no factual claim), run 2 1 -> 1; q3 run 1 unjudged -> out.
    s2 = _cell(r, "primary", "chat", S2)
    assert s2["mean"] == pytest.approx(1.0)
    assert (s2["n"], s2["excluded_no_claim"], s2["excluded_unjudged"]) == (2, 0, 1)
    # clef S1: q1 1; q2 0; q3 no factual claim.
    assert _cell(r, "primary", "clef_flash", S1)["mean"] == pytest.approx(0.5)
    assert _cell(r, "primary", "clef_flash", S2)["mean"] == pytest.approx(1.0)
    assert s1["low"] <= s1["mean"] <= s1["high"]


def test_no_claim_answers_scored_1_and_scored_0(tmp_path: Path) -> None:
    r = _run(tmp_path)
    # S1: q3 scores 1 -> (1 + 0.5 + 1) / 3; scores 0 -> (1 + 0.5 + 0) / 3.
    assert _cell(r, "no_claim_scored_1", "chat", S1)["mean"] == pytest.approx(2.5 / 3)
    assert _cell(r, "no_claim_scored_0", "chat", S1)["mean"] == pytest.approx(1.5 / 3)
    # S2: q2 run 1 (missing answer) scores 0 -> q2 0.5; q1 1; q3 unjudged stays out.
    assert _cell(r, "no_claim_scored_0", "chat", S2)["mean"] == pytest.approx(0.75)
    assert _cell(r, "no_claim_scored_0", "chat", S2)["n"] == 2


def test_unjudged_row_scored_0_in_its_sensitivity_table(tmp_path: Path) -> None:
    r = _run(tmp_path)
    # S2 q3: run 1 unjudged -> 0, run 2 1 -> 0.5; q1 1; q2 1.
    cell = _cell(r, "unjudged_scored_0", "chat", S2)
    assert cell["mean"] == pytest.approx(2.5 / 3)
    assert cell["n"] == 3


def test_all_claims_faithfulness_is_secondary_robustness(tmp_path: Path) -> None:
    r = _run(tmp_path)
    # chat S1, all claims: q1 0.5 and 0.5; q2 0 and 1; q3 0 and 0.
    assert _cell(r, "all_claims", "chat", S1)["mean"] == pytest.approx(1 / 3)
    assert r["faithfulness_status"]["all_claims"] == "secondary robustness"
    assert r["faithfulness_status"]["primary"] == "primary"


def test_per_checker_bounds_change_only_that_checkers_refusal_verdicts(tmp_path: Path) -> None:
    bounds = _run(tmp_path)["bounds"]["chat"]["bioasq"][S1]
    # high: R1 and R2 supported -> q1 1, q2 0.5, q3 1; low: as given -> q1 0.5, q2 0.5, q3 0.
    assert bounds["high"] == pytest.approx(2.5 / 3)
    assert bounds["low"] == pytest.approx(1 / 3)
    clef = _run(tmp_path / "again")["bounds"]["clef_flash"]["bioasq"][S1]
    # clef high: q1 1, q2 0, q3 1; low: q1 0.5, q2 0, q3 0.
    assert clef["high"] == pytest.approx(2 / 3)
    assert clef["low"] == pytest.approx(0.5 / 3)


# --- refusal figures -------------------------------------------------------------------------


def test_refusal_rate_per_setup_is_primary_descriptive(tmp_path: Path) -> None:
    rate = _run(tmp_path)["refusal_rate"]["bioasq"]
    assert (rate[S1]["refusals"], rate[S1]["claims"]) == (4, 8)
    assert rate[S1]["rate"] == pytest.approx(0.5)
    assert (rate[S2]["refusals"], rate[S2]["claims"]) == (0, 5)
    assert rate[S1]["status"] == "primary descriptive"
    assert rate[S1]["low"] < 0.5 < rate[S1]["high"]
    assert rate[S1]["testable"] is True


def test_checker_unsupported_rate_on_refusals_and_kappa_against_glm(tmp_path: Path) -> None:
    checks = _run(tmp_path)["refusal_checks"]["bioasq"]
    assert checks["unsupported_on_refusals"]["chat"]["rate"] == pytest.approx(1.0)
    assert checks["unsupported_on_refusals"]["clef_flash"]["rate"] == pytest.approx(0.0)
    # Refusals: chat all unsupported, clef all supported -> chance agreement 0, kappa 0.
    assert checks["kappa_clef_flash_vs_chat"]["refusal"] == pytest.approx(0.0)
    # Factual and mixed: 6 (s,s), 1 (u,u), 1 (s,u): po 7/8, pe 44/64 -> kappa 0.6.
    assert checks["kappa_clef_flash_vs_chat"]["factual_and_mixed"] == pytest.approx(0.6)


def test_unclassified_claim_counts_as_factual_and_is_counted(tmp_path: Path) -> None:
    r = _run(tmp_path, drop_kind=(S1, 1, "q1", "R1"))
    assert r["unclassified_claims"]["bioasq"][S1] == 1
    # R1 now counts as factual in S1 run 1: q1 run 1 (1 + 0) / 2 = 0.5, run 2 1 -> 0.75.
    assert _cell(r, "primary", "chat", S1)["mean"] == pytest.approx((0.75 + 0.5) / 2)
    # Left out in the sensitivity table: back to the first value.
    assert _cell(r, "unclassified_left_out", "chat", S1)["mean"] == pytest.approx(0.75)


# --- bootstrap intervals by question (pre-registration sections 6 and 11.2) -------------------


def _ratio(sample: list[tuple[int, int]]) -> float:
    total = sum(t for _, t in sample)
    return sum(h for h, _ in sample) / total if total else float("nan")


def _expected(per_question: list[tuple[str, tuple[int, int]]], n: int = 200) -> Any:
    return bootstrap35.bootstrap_by_question(per_question, _ratio, n=n, seed=20261136, fill=None)


def test_seed_is_a_named_constant_and_the_command_line_has_no_seed_option(tmp_path: Path) -> None:
    assert report.SEED == 20261136
    result = _run(tmp_path)
    assert result["seed"] == 20261136
    out, gate = tmp_path / "out", tmp_path / "gate.json"
    with pytest.raises(SystemExit):
        report.main(["--out-dir", str(out), "--gate", str(gate), "--seed", "5"])


def test_refusal_rate_interval_is_a_bootstrap_by_question(tmp_path: Path) -> None:
    rate = _run(tmp_path)["refusal_rate"]["bioasq"][S1]
    # S1 over both runs: q1 4 claims 2 refusals, q2 2 claims 0, q3 2 claims 2.
    expected = _expected([("q1", (2, 4)), ("q2", (0, 2)), ("q3", (2, 2))])
    assert rate["low"] == pytest.approx(expected.lower)
    assert rate["high"] == pytest.approx(expected.upper)
    assert rate["undefined"] == expected.undefined
    assert (rate["low"], rate["high"]) != pytest.approx(wilson(4, 8))  # not Wilson over claims


def test_unsupported_rate_on_refusals_is_a_bootstrap_by_question(tmp_path: Path) -> None:
    out = _build(tmp_path)
    report.write_report(out, gate_path=tmp_path / "gate.json")  # the default is 10,000 resamples
    result = json.loads((out / "refusals.json").read_text())
    assert result["n_boot"] == 10_000
    checks = result["refusal_checks"]["bioasq"]["unsupported_on_refusals"]
    # Refusal claims sit in q1 (R1, twice) and q3 (R2, twice); q2 has none but is a question.
    chat = _expected([("q1", (2, 2)), ("q2", (0, 0)), ("q3", (2, 2))], n=10_000)
    assert chat.testable
    assert checks["chat"]["rate"] == pytest.approx(1.0)
    assert checks["chat"]["low"] == pytest.approx(chat.lower)
    assert checks["chat"]["high"] == pytest.approx(chat.upper)
    clef = _expected([("q1", (0, 2)), ("q2", (0, 0)), ("q3", (0, 2))], n=10_000)
    assert checks["clef_flash"]["rate"] == pytest.approx(0.0)
    assert checks["clef_flash"]["high"] == pytest.approx(clef.upper)
    assert checks["chat"]["undefined"] == chat.undefined


def test_rate_interval_fails_closed() -> None:
    qids = ["q1", "q2", "q3"]
    # One question holds the only hit: a third of the resamples miss it (over 5%): not testable.
    thin = report._rate([("q1", True)], qids, n_boot=200)
    assert thin["testable"] is False
    assert (thin["low"], thin["high"]) == (None, None)
    assert thin["rate"] == pytest.approx(1.0)
    # No claim at all: the rate is undefined.
    empty = report._rate([], qids, n_boot=200)
    assert (empty["rate"], empty["low"], empty["high"]) == (None, None, None)
    assert empty["testable"] is False
