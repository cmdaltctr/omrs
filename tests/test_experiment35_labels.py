"""Experiment 35 labels for two labellers and the faithfulness gate (tasks 15.8 and 16.18).

Rules under test (pre-registration sections 11.2 and 11.3): the faithfulness
sample is 450 claims from crossed setups, 150 per chunk size, 50 per core
dataset within each, at most one claim per answer, from both halves; L1 labels
750 (700 after drop step 1); in the full plan L2 labels the same, in the
staged plan 30, 135 and all 200 first (365; 315 after drop step 1) and the
rest of a set when its subset kappa is below 0.70 or undefined; the gate
reference is the agreed label; the page shows no verdict, setup or chunk
size; the faithfulness gate needs kappa 0.60 with a lower bound of 0.40; the
GLM-5.3 specificity difference (2,048 minus 512) decides rows 12, 13, 16 and
17; undefined statistics fail closed; the gate file records its time.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from tests import _exp35_mainrun_fixtures as fx
from tests._exp35_fixtures import load

labels35 = load("labels35")
labelpage35 = load("labelpage35")

ROWS = [12, 13, 16, 17]


def _faith(tmp_path: Path, seed: int = 20261116) -> list[dict[str, Any]]:
    out = tmp_path / "out"
    questions = fx.build(out)
    return labels35.draw_faithfulness(labels35.faithfulness_claims(out, questions), seed=seed)


# --- 15.8 samples and counts -----------------------------------------------------------------


def test_faithfulness_sample_is_450_stratified_one_claim_per_answer(tmp_path: Path) -> None:
    items = _faith(tmp_path)
    assert len(items) == 450
    cells = Counter((i["chunk_size"], i["dataset"]) for i in items)
    assert set(cells.values()) == {50}
    assert {d for _, d in cells} == {"bioasq", "financebench", "freshstack"}  # core datasets only
    assert Counter(i["chunk_size"] for i in items) == {512: 150, 1024: 150, 2048: 150}
    answers = [(i["dataset"], i["setup"], i["run"], i["qid"]) for i in items]
    assert len(set(answers)) == 450  # at most one claim per answer
    assert not any("t20k" in i["setup"] for i in items)  # crossed setups only
    assert {int(i["qid"][1:]) % 2 for i in items} == {0, 1}  # both halves


def test_faithfulness_items_are_shuffled_across_cells(tmp_path: Path) -> None:
    sizes = [i["chunk_size"] for i in _faith(tmp_path)]
    assert sizes != sorted(sizes)


def test_checker_gate_needs_both_bars() -> None:
    boot = load("bootstrap35").BootResult
    assert labels35.checker_passes(boot(0.65, 0.40, 0.9, 10_000, 0, 10_000, True)) is True
    assert labels35.checker_passes(boot(0.65, 0.39, 0.9, 10_000, 0, 10_000, True)) is False
    assert labels35.checker_passes(boot(0.59, 0.45, 0.9, 10_000, 0, 10_000, True)) is False
    assert labels35.checker_passes(boot(0.90, 0.80, 0.9, 10_000, 600, 10_000, False)) is False


def test_same_seed_same_faithfulness_items(tmp_path: Path) -> None:
    first = [i["item_id"] for i in _faith(tmp_path / "a")]
    assert first == [i["item_id"] for i in _faith(tmp_path / "b")]
    assert first != [i["item_id"] for i in _faith(tmp_path / "c", seed=1)]


def test_label_counts_per_plan() -> None:
    full = {"claim_kinds": 100, "faithfulness": 450, "correctness": 200}
    dropped = {**full, "correctness": 150}
    assert labels35.label_counts(full, "full") == {"L1": 750, "L2": 750}
    assert labels35.label_counts(dropped, "full") == {"L1": 700, "L2": 700}
    assert labels35.label_counts(full, "staged") == {"L1": 750, "L2": 365}
    assert labels35.label_counts(dropped, "staged") == {"L1": 700, "L2": 315}


def _kind_items() -> list[dict[str, Any]]:
    return [{"item_id": f"k{i:03d}", "dataset": "bioasq", "qid": f"q{i}"} for i in range(100)]


def test_l2_items_full_and_staged(tmp_path: Path) -> None:
    faith = _faith(tmp_path)
    samples = {
        "claim_kinds": _kind_items(),
        "faithfulness": faith,
        "correctness": [{"item_id": f"c{i}"} for i in range(200)],
    }
    full = labels35.l2_items("full", samples)
    assert {k: len(v) for k, v in full.items()} == {
        "claim_kinds": 100,
        "faithfulness": 450,
        "correctness": 200,
    }
    staged = labels35.l2_items("staged", samples)
    assert {k: len(v) for k, v in staged.items()} == {
        "claim_kinds": 30,
        "faithfulness": 135,
        "correctness": 200,
    }
    chosen = [i for i in faith if i["item_id"] in set(staged["faithfulness"])]
    assert set(Counter((i["chunk_size"], i["dataset"]) for i in chosen).values()) == {15}
    assert staged == labels35.l2_items("staged", samples)  # seeded, same twice


def test_escalation_rule() -> None:
    items = [
        {
            "item_id": f"f{i}",
            "dataset": "bioasq",
            "qid": f"q{i}",
            "chunk_size": (512, 1024, 2048)[i % 3],
        }
        for i in range(30)
    ]
    l1 = {i["item_id"]: ("supported" if n % 2 else "not_supported") for n, i in enumerate(items)}
    assert labels35.escalate("faithfulness", items, l1, dict(l1)) is False
    # Three flips at 2,048: overall kappa 0.8 stays above 0.70, the level falls to 0.4.
    l2 = dict(l1)
    for n, i in enumerate(items):
        if i["chunk_size"] == 2048 and n < 9:
            l2[i["item_id"]] = (
                "supported" if l1[i["item_id"]] == "not_supported" else "not_supported"
            )
    assert labels35.escalate("faithfulness", items, l1, l2) is True
    # Undefined subset kappa (both mark every claim kind "factual") fails closed.
    kinds = [{"item_id": f"k{i}", "dataset": "bioasq", "qid": f"q{i}"} for i in range(30)]
    same = {i["item_id"]: "factual" for i in kinds}
    assert labels35.escalate("claim_kinds", kinds, same, dict(same)) is True


def test_reference_label_and_disagreement_rule() -> None:
    l1 = {"a": "supported", "b": "supported", "c": "supported", "d": "not_supported"}
    l2 = {"a": "supported", "b": "not_supported", "c": "not_supported"}
    labels, unresolved = labelpage35.reference_labels(l1, l2, {"b": "not_supported"})
    assert labels == {
        "a": "supported",
        "b": "not_supported",
        "c": "cant_tell",
        "d": "not_supported",
    }
    assert unresolved == 1


def test_faithfulness_page_is_blind(tmp_path: Path) -> None:
    items = _faith(tmp_path)
    label_dir = tmp_path / "labels"
    labels35.write_sample(label_dir, items)
    text = labels35.write_page(label_dir, "faithfulness").read_text()
    data = json.loads(re.search(r'id="items">(.*?)</script>', text, re.S).group(1))
    assert set(data["items"][0]) == {"item_id", "question", "claim", "passages"}
    assert data["items"][0]["passages"] == [f"passage for {items[0]['qid']}"]
    for banned in (
        "e4b-",
        "c512",
        "c1024",
        "2048",
        "chunk",
        "verdict",
        "unsupported",
        "score",
        "http",
    ):
        assert banned not in text, banned


def test_staged_l2_page_holds_only_the_subset(tmp_path: Path) -> None:
    items = _faith(tmp_path)
    label_dir = tmp_path / "labels"
    labels35.write_sample(label_dir, items)
    subset = labels35.l2_items("staged", {"faithfulness": items})["faithfulness"]
    text = labels35.write_page(label_dir, "faithfulness", only=subset).read_text()
    data = json.loads(re.search(r'id="items">(.*?)</script>', text, re.S).group(1))
    assert [i["item_id"] for i in data["items"]] == [
        i["item_id"] for i in items if i["item_id"] in set(subset)
    ]


def test_kappa_l1_against_l2_per_set_and_level() -> None:
    items = [
        {"item_id": f"f{i}", "dataset": d, "qid": f"q{i}", "chunk_size": c}
        for i, (d, c) in enumerate(
            (d, c) for d in ("bioasq", "freshstack") for c in (512, 2048) for _ in range(10)
        )
    ]
    l1 = {i["item_id"]: ("supported" if n % 2 else "not_supported") for n, i in enumerate(items)}
    result = labels35.kappa_l1_l2("faithfulness", items, l1, dict(l1), n=200)
    assert result["overall"]["estimate"] == pytest.approx(1.0)
    assert set(result["by_chunk_size"]) == {"512", "2048"}
    corr = labels35.kappa_l1_l2("correctness", items, l1, dict(l1), n=200)
    assert set(corr["by_dataset"]) == {"bioasq", "freshstack"}


# --- 16.18 faithfulness gate and differential-error rule -------------------------------------


def _gate_items(n_q: int = 10) -> list[dict[str, Any]]:
    return [
        {"item_id": f"{d}-{c}-{q}", "dataset": d, "qid": f"{c}-{q}", "chunk_size": c}
        for d in ("bioasq", "financebench", "freshstack")
        for c in (512, 1024, 2048)
        for q in range(n_q)
    ]


def _human(items: list[dict[str, Any]]) -> dict[str, str]:
    return {
        i["item_id"]: ("supported" if int(i["qid"].split("-")[1]) % 2 else "not_supported")
        for i in items
    }


def _checker(human: dict[str, str]) -> dict[str, str]:
    return {k: ("supported" if v == "supported" else "unsupported") for k, v in human.items()}


def _run_gate(items, human, verdicts) -> dict[str, Any]:
    return labels35.faithfulness_gate(
        items, human, verdicts, n=300, decided_at="2026-11-20T10:00:00+00:00"
    )


def test_faithfulness_gate_passes_when_checkers_agree() -> None:
    items = _gate_items()
    human = _human(items)
    result = _run_gate(items, human, {"chat": _checker(human), "clef_flash": _checker(human)})
    assert result["checkers"]["chat"]["pass"] is True
    assert result["checkers"]["chat"]["kappa"]["estimate"] == pytest.approx(1.0)
    assert set(result["checkers"]["chat"]["by_dataset"]) == {"bioasq", "financebench", "freshstack"}
    assert result["not_testable_rows"] == []
    assert result["decided_at"] == "2026-11-20T10:00:00+00:00"


def test_cant_tell_counts_as_not_supported_and_is_also_left_out() -> None:
    items = _gate_items()
    human = _human(items)
    verdicts = _checker(human)
    first = items[0]["item_id"]  # human not supported
    human[first] = "cant_tell"
    verdicts[first] = "supported"
    result = _run_gate(items, human, {"chat": verdicts, "clef_flash": verdicts})["checkers"]["chat"]
    assert result["kappa"]["estimate"] < 1.0
    assert result["kappa_cant_tell_left_out"]["estimate"] == pytest.approx(1.0)
    assert result["cant_tell"] == 1


def test_failed_glm_gate_makes_rows_not_testable_and_failed_clef_changes_nothing() -> None:
    items = _gate_items()
    human = _human(items)
    every_supported = {k: "supported" for k in human}
    glm_fails = _run_gate(items, human, {"chat": every_supported, "clef_flash": _checker(human)})
    assert glm_fails["checkers"]["chat"]["pass"] is False
    assert glm_fails["not_testable_rows"] == ROWS
    clef_fails = _run_gate(items, human, {"chat": _checker(human), "clef_flash": every_supported})
    assert clef_fails["checkers"]["clef_flash"]["validated"] is False
    assert clef_fails["not_testable_rows"] == []


def test_specificity_difference_excluding_zero_makes_rows_not_testable() -> None:
    items = _gate_items()
    human = _human(items)
    glm = _checker(human)
    for i in items:  # at 2,048 GLM-5.3 rejects every human-supported claim
        if i["chunk_size"] == 2048 and human[i["item_id"]] == "supported":
            glm[i["item_id"]] = "unsupported"
    result = _run_gate(items, human, {"chat": glm, "clef_flash": _checker(human)})
    diff = result["differential_error"]
    assert diff["specificity"]["chat"]["512"] == pytest.approx(1.0)
    assert diff["specificity"]["chat"]["2048"] == pytest.approx(0.0)
    assert diff["difference"]["estimate"] == pytest.approx(-1.0)
    assert diff["excludes_zero"] is True
    assert result["not_testable_rows"] == ROWS
    assert diff["sensitivity"]["chat"]["2048"] == pytest.approx(1.0)


def test_level_with_no_supported_claim_is_undefined_and_fails_closed() -> None:
    items = _gate_items()
    human = {k: ("not_supported" if "-512-" in k else v) for k, v in _human(items).items()}
    result = _run_gate(items, human, {"chat": _checker(human), "clef_flash": _checker(human)})
    assert result["differential_error"]["difference"]["testable"] is False
    assert result["not_testable_rows"] == ROWS


def test_over_5_percent_undefined_difference_resamples_fail_closed() -> None:
    items = _gate_items()
    human = _human(items)
    for i in items:  # only one question at 512 holds a supported claim
        if i["chunk_size"] == 512:
            human[i["item_id"]] = "supported" if i["item_id"] == "bioasq-512-1" else "not_supported"
    result = _run_gate(items, human, {"chat": _checker(human), "clef_flash": _checker(human)})
    diff = result["differential_error"]["difference"]
    assert diff["estimate"] == pytest.approx(0.0)
    assert diff["undefined"] > 15
    assert diff["kept"] == 300 - diff["undefined"]  # undefined differences are left out
    assert diff["testable"] is False
    assert result["not_testable_rows"] == ROWS


def test_analysis_refuses_before_the_gate_files_exist(tmp_path: Path) -> None:
    with pytest.raises(labels35.GateMissing, match="faithfulness-gate.json"):
        labels35.require_gates(tmp_path)
    (tmp_path / "faithfulness-gate.json").write_text(
        json.dumps({"decided_at": "t", "not_testable_rows": ROWS})
    )
    with pytest.raises(labels35.GateMissing, match="correctness-gate.json"):
        labels35.require_gates(tmp_path)
    (tmp_path / "correctness-gate.json").write_text(
        json.dumps(
            {
                "decided_at": "t",
                "result": {"not_testable_rows": {"freshstack": [14, 15, 18, 19]}},
            }
        )
    )
    rows = labels35.require_gates(tmp_path)
    assert rows == {
        "bioasq": {12, 13, 16, 17},
        "financebench": {12, 13, 16, 17},
        "freshstack": {12, 13, 14, 15, 16, 17, 18, 19},
    }


def test_faithgate_cli_reads_saved_verdicts_and_writes_the_gate(tmp_path: Path) -> None:
    items = _faith(tmp_path)
    label_dir = tmp_path / "labels"
    labels35.write_sample(label_dir, items)
    # Fixture verdicts: claim 0 supported, claim 1 unsupported; the labeller agrees.
    labels = {i["item_id"]: "supported" if i["index"] == 0 else "not_supported" for i in items}
    for who in ("L1", "L2"):
        (label_dir / f"labels-faithfulness-{who}.json").write_text(
            json.dumps({"set": "faithfulness", "labeller": who, "labels": labels})
        )
    assert (
        labels35.main(
            [
                "faithgate",
                "--out-dir",
                str(tmp_path / "out"),
                "--label-dir",
                str(label_dir),
                "--n",
                "200",
            ]
        )
        == 0
    )
    gate = json.loads((label_dir / "faithfulness-gate.json").read_text())
    assert gate["decided_at"]
    assert gate["checkers"]["chat"]["pass"] is True
