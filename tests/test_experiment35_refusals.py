"""Experiment 35 classifier gate: sample, labelling page and gate (tasks 8.3, 8.4 and 8.6).

Rules under test (pre-freeze amendment 2026-11-23): the sample reads the valid
claims of a test pod session output folder (``<dataset>/answer/<setup>/run<n>``)
and refuses an answer folder whose trace record does not show reasoning
``none``; about a third comes from each dataset, half flagged by the pre-freeze
regular expression and half not, and a short stratum gives all its claims while
the other stratum fills the gap; stratum sizes and fractions are recorded; the
same seed gives the same claims in the same order; the sample holds no kind
and no verdict; the claims outside the sample go to the prompt-example pool.
The page is blind and offline. The gate scores stratum-weighted agreement,
refusal recall and refusal precision, with unweighted values and Wilson
intervals, against hand-worked numbers.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import string
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from experiments._lib.stats_d6 import wilson
from tests._exp35_fixtures import load
from tests._exp35_label_fixtures import write_rows, write_run

refusals35 = load("refusals35")
claimkinds35 = load("claimkinds35")
labelpage35 = load("labelpage35")

ARMS = ("arm-alpha", "arm-beta")


def _word(i: int) -> str:
    letters = string.ascii_lowercase
    return letters[i // 26 % 26] + letters[i % 26] + letters[i // 676 % 26]


def _session(
    root: Path, dataset: str, flagged: int, plain: int, *, reasoning: str = "none"
) -> Path:
    """One dataset folder of a test pod output: claims over 2 arms x 2 runs (run 2 repeats 1)."""
    folder = root / dataset
    sentences = [f"The sources do not cover {_word(i)}" for i in range(flagged)]
    sentences += [f"The value is {_word(i + 1000)}" for i in range(plain)]
    per_q = {
        f"{dataset[:2]}{i}": sentences[i * 3 : i * 3 + 3] for i in range((len(sentences) + 2) // 3)
    }
    half = len(per_q) // 2
    for a, arm in enumerate(ARMS):
        part = dict(
            list(per_q.items())[a * half : (a + 1) * half] if a == 0 else list(per_q.items())[half:]
        )
        for run in (1, 2):
            run_dir = folder / "answer" / arm / f"run{run}"
            write_run(run_dir, part)
            write_rows(
                run_dir / "traces.jsonl",
                [{"stage": "answer", "effective_settings": {"answer_reasoning": reasoning}}],
            )
    return folder


def _questions(folders: dict[str, Path]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for dataset, folder in folders.items():
        qids = {
            json.loads(line)["qid"]
            for p in folder.glob("answer/*/run1/answer.jsonl")
            for line in p.read_text().splitlines()
        }
        out[dataset] = {q: f"question {q}?" for q in qids}
    return out


def _folders(tmp_path: Path) -> dict[str, Path]:
    return {
        "bioasq": _session(tmp_path, "bioasq", 30, 30),
        "financebench": _session(tmp_path, "financebench", 5, 60),
        "freshstack": _session(tmp_path, "freshstack", 40, 40),
    }


def _draw(tmp_path: Path, seed: int = 20261112) -> dict[str, Any]:
    folders = _folders(tmp_path)
    claims = refusals35.session_claims(folders, _questions(folders))
    return refusals35.draw_sample(claims, seed=seed, n=100)


# --- 8.3 sample ------------------------------------------------------------------------------


def test_an_answer_folder_with_reasoning_other_than_none_is_refused(tmp_path: Path) -> None:
    folders = _folders(tmp_path)
    folders["bioasq"] = _session(tmp_path / "high", "bioasq", 5, 5, reasoning="high")
    with pytest.raises(refusals35.SampleError, match=r"run1: answer reasoning is 'high'"):
        refusals35.session_claims(folders, _questions(folders))


def test_an_answer_folder_with_no_trace_record_is_refused(tmp_path: Path) -> None:
    folders = _folders(tmp_path)
    (folders["bioasq"] / "answer" / ARMS[0] / "run1" / "traces.jsonl").unlink()
    with pytest.raises(refusals35.SampleError, match=r"traces\.jsonl"):
        refusals35.session_claims(folders, _questions(folders))


def test_a_folder_with_no_answer_files_is_refused(tmp_path: Path) -> None:
    folders = _folders(tmp_path)
    folders["bioasq"] = tmp_path / "old-layout" / "bioasq"  # <setup>/run<n> with no answer/ level
    write_run(folders["bioasq"] / ARMS[0] / "run1", {"bi0": ["The value is x"]})
    with pytest.raises(refusals35.SampleError, match="old-layout/bioasq"):
        refusals35.session_claims(folders, _questions(folders))


def test_each_claim_carries_its_first_answer_and_the_passages_it_cites(tmp_path: Path) -> None:
    folders = _folders(tmp_path)
    claims = refusals35.session_claims(folders, _questions(folders))
    first = claims[0]
    assert first["claim"].rstrip(".") + " [1]." in first["answer"]
    assert first["passages"] == [{"ordinal": 1, "text": f"passage for {first['qid']}"}]
    drawn = refusals35.draw_sample(claims, seed=20261112, n=100)
    assert all("answer" in i and "passages" in i for i in drawn["items"])


def test_context_keeps_the_first_answer_and_maps_cited_ordinals(tmp_path: Path) -> None:
    claimcontext35 = load("claimcontext35")
    row = {
        "qid": "q1",
        "answer": "Alpha is one [2]. Beta is two [1, 3].",
        "evidence": [
            {"ordinal": 1, "text": "p1"},
            {"ordinal": 2, "text": "p2"},
            {"ordinal": 3, "text": "p3"},
        ],
    }
    pairs = claimcontext35.claim_contexts(row)
    assert [c for c, _ in pairs] == claimkinds35.answer_claims(row)
    assert pairs[1][1] == [{"ordinal": 1, "text": "p1"}, {"ordinal": 3, "text": "p3"}]
    folder = tmp_path / "bioasq"
    for arm, extra in ((ARMS[0], "First extra"), (ARMS[1], "Second extra")):
        run_dir = folder / "answer" / arm / "run1"
        write_run(run_dir, {"bi0": ["Shared claim", extra]})
        write_rows(run_dir / "traces.jsonl", [{"effective_settings": {"answer_reasoning": "none"}}])
    found = refusals35.session_claims({"bioasq": folder}, {"bioasq": {"bi0": "q?"}})
    shared = next(c for c in found if c["claim"] == "Shared claim.")
    assert "First extra" in shared["answer"]  # sorted folder order: the first answer wins


def test_claims_are_deduplicated_across_arms_and_runs(tmp_path: Path) -> None:
    folders = _folders(tmp_path)
    claims = refusals35.session_claims(folders, _questions(folders))
    assert len(claims) == 60 + 65 + 80
    assert len({c["claim_key"] for c in claims}) == len(claims)


def test_strata_split_and_fill(tmp_path: Path) -> None:
    drawn = _draw(tmp_path)
    strata = {s["stratum"]: s for s in drawn["strata"]}
    assert {k: v["drawn"] for k, v in strata.items()} == {
        "bioasq/flagged": 17,
        "bioasq/plain": 17,
        "financebench/flagged": 5,  # too few: all of them
        "financebench/plain": 28,  # fills the gap to 33
        "freshstack/flagged": 17,
        "freshstack/plain": 16,
    }
    assert strata["financebench/flagged"]["size"] == 5
    assert strata["financebench/plain"]["size"] == 60
    assert strata["financebench/plain"]["fraction"] == pytest.approx(28 / 60)
    assert len(drawn["items"]) == 100


def test_same_seed_same_claims_same_order(tmp_path: Path) -> None:
    first = _draw(tmp_path / "a")
    second = _draw(tmp_path / "b")
    assert [i["claim_key"] for i in first["items"]] == [i["claim_key"] for i in second["items"]]
    other = _draw(tmp_path / "c", seed=7)
    assert [i["claim_key"] for i in other["items"]] != [i["claim_key"] for i in first["items"]]


def test_order_is_shuffled_across_strata(tmp_path: Path) -> None:
    items = _draw(tmp_path)["items"]
    assert [i["stratum"] for i in items] != sorted(i["stratum"] for i in items)


def test_written_sample_has_no_kind_and_no_verdict_and_a_pool(tmp_path: Path) -> None:
    drawn = _draw(tmp_path)
    out = tmp_path / "gate"
    refusals35.write_sample(out, drawn)
    text = (out / "sample.json").read_text()
    assert "kind" not in json.dumps(json.loads(text)["items"])
    assert "verdict" not in text
    pool = json.loads((out / "examples-pool.json").read_text())
    sample_keys = {i["claim_key"] for i in drawn["items"]}
    assert len(pool) == 205 - 100
    assert not sample_keys & {p["claim_key"] for p in pool}


# --- 8.4 page --------------------------------------------------------------------------------


def _page(tmp_path: Path) -> tuple[str, dict[str, Any]]:
    drawn = _draw(tmp_path)
    out = tmp_path / "gate"
    refusals35.write_sample(out, drawn)
    refusals35.write_claim_page(out)
    text = (out / "label-claim-kinds.html").read_text()
    blob = re.search(r'<script type="application/json" id="items">(.*?)</script>', text, re.S)
    assert blob is not None
    return text, json.loads(blob.group(1))


def test_page_shows_question_claim_answer_and_passages_with_four_choices(tmp_path: Path) -> None:
    text, data = _page(tmp_path)
    assert len(data["items"]) == 100
    item = data["items"][0]
    assert set(item) == {"item_id", "question", "claim", "answer", "passages"}
    assert item["claim"].rstrip(".") + " [1]." in item["answer"]
    assert [set(p) for p in item["passages"]] == [{"ordinal", "text"}]
    assert item["passages"][0]["text"].startswith("passage for ")
    assert [c[0] for c in data["choices"]] == ["factual", "refusal", "mixed", "cant_tell"]
    assert "Can't tell" in text


def test_page_holds_no_kind_verdict_stratum_setup_or_network_address(tmp_path: Path) -> None:
    text, data = _page(tmp_path)
    for item in data["items"]:  # the new context fields carry no hidden key
        assert [set(p) for p in item["passages"]] == [{"ordinal", "text"}] * len(item["passages"])
        assert isinstance(item["answer"], str)
    for banned in (
        "verdict",
        "flagged",
        "stratum",
        "arm-alpha",
        "arm-beta",
        "http",
        "fetch(",
        "XMLHttpRequest",
        "src=",
    ):
        assert banned not in text, banned


def test_page_saves_a_json_download_and_keeps_a_draft_inside_try(tmp_path: Path) -> None:
    text, _ = _page(tmp_path)
    assert "application/json" in text and ".download" in text
    uses = [m.start() for m in re.finditer("localStorage", text)]
    assert uses
    for at in uses:  # every browser-storage use sits inside a try block
        assert re.search(r"try \{[^}]*$", text[:at]), text[at - 60 : at]
    assert '<select id="labeller">' in text and "L1" in text and "L2" in text
    assert "name=" not in text.lower().replace("input.name", "")  # no name field


# --- 8.5 classifier run on the sample --------------------------------------------------------


def test_classify_sample_writes_one_kind_per_item(tmp_path: Path) -> None:
    drawn = _draw(tmp_path)
    out = tmp_path / "gate"
    refusals35.write_sample(out, drawn)

    async def call(messages: list[dict[str, str]]) -> SimpleNamespace:
        text = "refusal" if "do not cover" in messages[-1]["content"] else "factual"
        return SimpleNamespace(text=text)

    asyncio.run(refusals35.classify_sample(out, call, prompt="p", version="v9"))
    rows = [json.loads(line) for line in (out / "sample-kinds.jsonl").read_text().splitlines()]
    assert len(rows) == 100
    assert {r["version"] for r in rows} == {"v9"}


# --- 8.6 gate --------------------------------------------------------------------------------

# Two strata: flagged (size 10, 4 drawn, weight 2.5) and plain (size 90, 6 drawn, weight 15).
GATE_ITEMS = [
    # stratum, human label, classifier kind
    ("d/flagged", "refusal", "refusal"),
    ("d/flagged", "refusal", "refusal"),
    ("d/flagged", "mixed", "refusal"),
    ("d/flagged", "refusal", "factual"),
    ("d/plain", "factual", "factual"),
    ("d/plain", "factual", "factual"),
    ("d/plain", "refusal", "refusal"),
    ("d/plain", "mixed", "factual"),  # mixed and factual both count as not refusal
    ("d/plain", "cant_tell", "refusal"),
    ("d/plain", "factual", "unreadable"),  # a gate miss
]


def _gate(items: list[tuple[str, str, str]]) -> dict[str, Any]:
    sample = {
        "strata": [
            {"stratum": "d/flagged", "size": 10, "drawn": 4, "fraction": 0.4},
            {"stratum": "d/plain", "size": 90, "drawn": 6, "fraction": 6 / 90},
        ],
        "items": [
            {
                "item_id": f"k{i}",
                "claim_key": f"k{i}",
                "stratum": s,
                "flagged": s.endswith("flagged"),
            }
            for i, (s, _, _) in enumerate(items)
        ],
    }
    labels = {f"k{i}": h for i, (_, h, _) in enumerate(items)}
    kinds = {f"k{i}": k for i, (_, _, k) in enumerate(items)}
    return refusals35.gate(sample, labels, kinds, version="v1")


def test_gate_weighted_and_unweighted_figures() -> None:
    result = _gate(GATE_ITEMS)
    c = result["classifier"]
    assert c["weighted_agreement"] == pytest.approx(65 / 85)
    assert c["agreement"] == pytest.approx(6 / 9)
    assert c["weighted_recall"] == pytest.approx(20 / 22.5)
    assert c["recall"] == pytest.approx(3 / 4)
    assert c["precision"] == pytest.approx(3 / 4)
    assert c["weighted_precision"] == pytest.approx(20 / 22.5)
    assert result["refusal_count"] == 4
    assert result["cant_tell_count"] == 1
    assert result["unreadable_count"] == 1
    assert result["pass"] is False


def test_gate_scores_the_regular_expression_as_a_baseline() -> None:
    base = _gate(GATE_ITEMS)["baseline_regex"]
    assert base["weighted_agreement"] == pytest.approx(67.5 / 85)
    assert base["agreement"] == pytest.approx(7 / 9)
    assert base["weighted_recall"] == pytest.approx(7.5 / 22.5)
    assert base["recall"] == pytest.approx(3 / 4)


def test_gate_passes_only_when_both_thresholds_hold() -> None:
    perfect = [(s, h, "refusal" if h == "refusal" else "factual") for s, h, _ in GATE_ITEMS]
    assert _gate(perfect)["pass"] is True
    # High agreement, but weighted recall 20 / 22.5 (0.889) below 0.90.
    no_recall = [(s, h, "factual" if i == 3 else k) for i, (s, h, k) in enumerate(perfect)]
    result = _gate(no_recall)
    assert result["classifier"]["weighted_agreement"] >= 0.90
    assert result["pass"] is False


def _flat_gate(refusals: int, false_alarms: int, others: int) -> dict[str, Any]:
    """One stratum, weight 1. *refusals* human refusals all caught; *false_alarms* of the
    *others* non-refusals are called refusal by the classifier."""
    items = [("d/all", "refusal", "refusal")] * refusals
    items += [("d/all", "factual", "refusal")] * false_alarms
    items += [("d/all", "factual", "factual")] * (others - false_alarms)
    sample = {
        "strata": [{"stratum": "d/all", "size": len(items), "drawn": len(items), "fraction": 1.0}],
        "items": [
            {"item_id": f"k{i}", "claim_key": f"k{i}", "stratum": s, "flagged": False}
            for i, (s, _, _) in enumerate(items)
        ],
    }
    labels = {f"k{i}": h for i, (_, h, _) in enumerate(items)}
    kinds = {f"k{i}": k for i, (_, _, k) in enumerate(items)}
    return refusals35.gate(sample, labels, kinds, version="v1")


def test_the_gate_has_three_pass_marks() -> None:
    assert refusals35.THRESHOLDS == {"agreement": 0.90, "recall": 0.90, "precision": 0.90}


def test_gate_fails_on_precision_when_agreement_and_recall_pass() -> None:
    # 10 human refusals all caught, 3 of 90 other claims called refusal.
    result = _flat_gate(refusals=10, false_alarms=3, others=90)
    c = result["classifier"]
    assert c["weighted_agreement"] == pytest.approx(97 / 100)
    assert c["weighted_recall"] == pytest.approx(1.0)
    assert c["weighted_precision"] == pytest.approx(10 / 13)
    assert c["precision"] == pytest.approx(10 / 13)
    assert result["pass"] is False


def test_gate_passes_when_precision_reaches_the_mark() -> None:
    # 9 of 10 predicted refusals are real: 0.90 exactly.
    result = _flat_gate(refusals=9, false_alarms=1, others=90)
    assert result["classifier"]["weighted_precision"] == pytest.approx(0.90)
    assert result["pass"] is True


def test_gate_precision_is_weighted_by_the_inverse_sampling_fraction() -> None:
    # Weighted 20 / 22.5 against unweighted 3 / 4, from the hand-worked fixture.
    c = _gate(GATE_ITEMS)["classifier"]
    assert c["weighted_precision"] != pytest.approx(c["precision"])
    assert c["weighted_precision"] == pytest.approx(20 / 22.5)


def test_gate_fails_closed_when_precision_is_undefined(monkeypatch: pytest.MonkeyPatch) -> None:
    # The classifier never says refusal. Only the precision mark is active, so a pass
    # could only come from treating an undefined precision as good.
    monkeypatch.setattr(refusals35, "THRESHOLDS", {"precision": 0.90})
    result = _flat_gate(refusals=0, false_alarms=0, others=20)
    assert math.isnan(result["classifier"]["weighted_precision"])
    assert result["pass"] is False


def test_gate_fails_when_the_classifier_never_says_refusal() -> None:
    result = _gate([(s, h, "factual") for s, h, _ in GATE_ITEMS])
    assert math.isnan(result["classifier"]["precision"])
    assert result["pass"] is False
    assert result["intervals"]["precision"] is None


def test_gate_reports_wilson_intervals_on_the_unweighted_counts() -> None:
    result = _gate(GATE_ITEMS)
    box = result["intervals"]
    assert box["method"] == "wilson" and box["confidence"] == 0.95
    # agreement 6 of 9; recall 3 of 4 human refusals; precision 3 of 4 predicted refusals.
    assert box["agreement"] == {"successes": 6, "n": 9, **_bounds(6, 9)}
    assert box["recall"] == {"successes": 3, "n": 4, **_bounds(3, 4)}
    assert box["precision"] == {"successes": 3, "n": 4, **_bounds(3, 4)}


def _bounds(successes: int, n: int) -> dict[str, float]:
    low, high = wilson(successes, n, 0.95)
    return {"low": pytest.approx(low), "high": pytest.approx(high)}


def test_the_intervals_decide_nothing() -> None:
    # Perfect on 10 claims: point estimates 1.0 pass, Wilson lower bounds sit below 0.90.
    result = _flat_gate(refusals=5, false_alarms=0, others=5)
    assert result["pass"] is True
    assert result["intervals"]["agreement"]["low"] < 0.90
    assert result["intervals"]["recall"]["low"] < 0.90


def test_gate_cli_writes_gate_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    drawn = _draw(tmp_path)
    out = tmp_path / "gate"
    refusals35.write_sample(out, drawn)
    keys = [i["claim_key"] for i in drawn["items"]]
    flags = {i["claim_key"]: i["flagged"] for i in drawn["items"]}
    (out / "labels-L1.json").write_text(
        json.dumps(
            {
                "set": "claim_kinds",
                "labeller": "L1",
                "labels": {k: "refusal" if flags[k] else "factual" for k in keys},
            }
        )
    )
    write_rows(
        out / "sample-kinds.jsonl",
        [
            {"claim_key": k, "kind": "refusal" if flags[k] else "factual", "version": "v1"}
            for k in keys
        ],
    )
    assert (
        refusals35.main(["gate", "--out-dir", str(out), "--labels", str(out / "labels-L1.json")])
        == 0
    )
    gate = json.loads((out / "gate.json").read_text())
    assert gate["pass"] is True
    assert gate["version"] == "v1"
    assert "intervals" in gate and "wilson" in capsys.readouterr().out
