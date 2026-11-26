"""Checks on kinds_recheck35.py, the claim-kind recheck of the freeze check (owner, 2026-11-26).

Rules under test: ``prepare`` drops every gate-2 claim that is now a prompt example and
keeps the owner's labels of the rest; ``score`` gives the gate figures (same definitions
as ``refusals35.gate``) and recall and precision per kind, marks the result as
informational and exits 0 whatever the score; a sample claim with no saved kind (a
missing or failed call) exits 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent.parent.parent)]
import claimkinds35  # noqa: E402
import kinds_recheck35 as kr  # noqa: E402

CLAIMS = [
    ("q1", "The sources do not say.", "refusal"),
    ("q2", "Revenue rose 5%.", "factual"),
    ("q3", "Sales fell, but the sources do not say why.", "mixed"),
    ("q4", "The margin was 45%.", "factual"),
    ("q5", "No source gives the date.", "refusal"),
]


def _item(qid: str, claim: str) -> dict:
    key = claimkinds35.claim_key(qid, claim)
    return {"item_id": key, "claim_key": key, "claim": claim, "question": f"Q {qid}?",
            "stratum": "bioasq/plain", "flagged": False}  # fmt: skip


@pytest.fixture
def gate2(tmp_path: Path) -> Path:
    folder = tmp_path / "gate2"
    folder.mkdir()
    items = [_item(q, c) for q, c, _ in CLAIMS]
    strata = [{"stratum": "bioasq/plain", "fraction": 0.5, "taken": 5, "available": 10}]
    (folder / "sample.json").write_text(json.dumps({"seed": 1, "n": 5, "strata": strata,
                                                    "items": items}))  # fmt: skip
    labels = {i["item_id"]: kind for i, (_, _, kind) in zip(items, CLAIMS, strict=True)}
    (folder / "claim_kinds-L1.json").write_text(
        json.dumps({"set": "claim_kinds", "labeller": "L1", "labels": labels})
    )
    examples = [{"qid": "q4", "question": "Q q4?", "claim": "The margin was 45%.",
                 "kind": "factual"}]  # fmt: skip
    (tmp_path / "examples.json").write_text(json.dumps(examples))
    return folder


def _prepare(gate2: Path) -> Path:
    out = gate2.parent / "recheck-input.json"
    assert kr.main(["prepare", "--gate2", str(gate2), "--examples",
                    str(gate2.parent / "examples.json"), "--out", str(out)]) == 0  # fmt: skip
    return out


def _kinds(folder: Path, kinds: dict[str, str]) -> None:
    rows = [{"claim_key": k, "kind": v, "version": "v1"} for k, v in kinds.items()]
    (folder / "sample-kinds.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _score(inp: Path, folder: Path) -> int:
    return kr.main(["score", "--input", str(inp), "--out-dir", str(folder)])


def test_prepare_drops_the_prompt_examples_and_keeps_their_labels_out(gate2: Path) -> None:
    found = json.loads(_prepare(gate2).read_text())
    example = claimkinds35.claim_key("q4", "The margin was 45%.")
    assert example not in {i["claim_key"] for i in found["sample"]["items"]}
    assert len(found["sample"]["items"]) == 4 and found["excluded"] == [example]
    assert set(found["labels"]) == {i["item_id"] for i in found["sample"]["items"]}


def test_score_gives_the_gate_figures_and_each_kind_and_never_fails_on_the_score(
    gate2: Path, tmp_path: Path
) -> None:
    inp = _prepare(gate2)
    out = tmp_path / "recheck"
    assert kr.main(["split", "--input", str(inp), "--out-dir", str(out)]) == 0
    sample = json.loads((out / "sample.json").read_text())
    truth = {i["claim_key"]: json.loads(inp.read_text())["labels"][i["item_id"]]
             for i in sample["items"]}  # fmt: skip
    wrong = dict(truth)
    refusal_keys = [k for k, v in truth.items() if v == "refusal"]
    wrong[refusal_keys[0]] = "factual"  # one refusal missed
    _kinds(out, wrong)
    assert _score(inp, out) == 0
    summary = json.loads((out / "recheck-summary.json").read_text())
    assert summary["informational"] is True and "optimistic" in summary["note"]
    assert summary["gate"]["classifier"]["recall"] == pytest.approx(0.5)
    assert summary["gate"]["classifier"]["precision"] == pytest.approx(1.0)
    assert summary["per_kind"]["refusal"]["recall"] == pytest.approx(0.5)
    assert summary["per_kind"]["factual"]["precision"] == pytest.approx(0.5)
    assert summary["per_kind"]["mixed"] == {"recall": 1.0, "precision": 1.0, "human": 1,
                                            "predicted": 1}  # fmt: skip
    assert summary["calls"] == 4 and summary["unreadable_count"] == 0


def test_a_claim_with_no_saved_kind_fails_the_check(gate2: Path, tmp_path: Path) -> None:
    inp = _prepare(gate2)
    out = tmp_path / "recheck"
    assert kr.main(["split", "--input", str(inp), "--out-dir", str(out)]) == 0
    items = json.loads((out / "sample.json").read_text())["items"]
    _kinds(out, {i["claim_key"]: "factual" for i in items[:-1]})
    assert _score(inp, out) == 1
    assert not (out / "recheck-summary.json").exists()
