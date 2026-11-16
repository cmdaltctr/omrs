"""Experiment 35 classifier gate: sample, labelling page and gate (tasks 8.3, 8.4 and 8.6).

Rules under test: the sample reads valid smoke claims only and refuses the
first FreshStack smoke folder (its index holds only the overlay runbook);
about a third comes from each dataset, half flagged by the pre-freeze regular
expression and half not, and a short stratum gives all its claims while the
other stratum fills the gap; stratum sizes and fractions are recorded; the
same seed gives the same claims in the same order; the sample holds no kind
and no verdict; the claims outside the sample go to the prompt-example pool.
The page is blind and offline. The gate scores stratum-weighted agreement and
refusal recall, with unweighted values, against hand-worked numbers.
"""

from __future__ import annotations

import asyncio
import json
import re
import string
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load
from tests._exp35_label_fixtures import write_rows, write_run

refusals35 = load("refusals35")
claimkinds35 = load("claimkinds35")
labelpage35 = load("labelpage35")

ARMS = ("arm-alpha", "arm-beta")


def _word(i: int) -> str:
    letters = string.ascii_lowercase
    return letters[i // 26 % 26] + letters[i % 26] + letters[i // 676 % 26]


def _smoke(
    root: Path, dataset: str, flagged: int, plain: int, *, overlay_only: bool = False
) -> Path:
    """One smoke folder: claims spread over 2 arms x 2 runs (run 2 repeats run 1)."""
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
            write_run(folder / arm / f"run{run}", part)
        files = ["zzqj-9097-runbook.md"] if overlay_only else ["doc-a.md", "zzqj-9097-runbook.md"]
        write_rows(
            folder / arm / "index" / "ingest.jsonl", [{"file": f, "status": "ok"} for f in files]
        )
    return folder


def _questions(folders: dict[str, Path]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for dataset, folder in folders.items():
        qids = {
            json.loads(line)["qid"]
            for p in folder.glob("*/run1/answer.jsonl")
            for line in p.read_text().splitlines()
        }
        out[dataset] = {q: f"question {q}?" for q in qids}
    return out


def _folders(tmp_path: Path) -> dict[str, Path]:
    return {
        "bioasq": _smoke(tmp_path, "bioasq", 30, 30),
        "financebench": _smoke(tmp_path, "financebench", 5, 60),
        "freshstack": _smoke(tmp_path / "rerun", "freshstack", 40, 40),
    }


def _draw(tmp_path: Path, seed: int = 20261112) -> dict[str, Any]:
    folders = _folders(tmp_path)
    claims = refusals35.smoke_claims(folders, _questions(folders))
    return refusals35.draw_sample(claims, seed=seed, n=100)


# --- 8.3 sample ------------------------------------------------------------------------------


def test_invalid_first_freshstack_smoke_folder_is_refused(tmp_path: Path) -> None:
    folders = {"freshstack": _smoke(tmp_path / "first", "freshstack", 4, 4, overlay_only=True)}
    with pytest.raises(refusals35.SampleError, match="overlay runbook"):
        refusals35.smoke_claims(folders, _questions(folders))


def test_claims_are_deduplicated_across_arms_and_runs(tmp_path: Path) -> None:
    folders = _folders(tmp_path)
    claims = refusals35.smoke_claims(folders, _questions(folders))
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


def test_page_shows_question_and_claim_with_four_choices(tmp_path: Path) -> None:
    text, data = _page(tmp_path)
    assert len(data["items"]) == 100
    assert set(data["items"][0]) == {"item_id", "question", "claim"}
    assert [c[0] for c in data["choices"]] == ["factual", "refusal", "mixed", "cant_tell"]
    assert "Can't tell" in text


def test_page_holds_no_kind_verdict_stratum_setup_or_network_address(tmp_path: Path) -> None:
    text, _ = _page(tmp_path)
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

    async def call(messages: list[dict[str, str]]) -> str:
        return "refusal" if "do not cover" in messages[-1]["content"] else "factual"

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


def test_gate_cli_writes_gate_json(tmp_path: Path) -> None:
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
