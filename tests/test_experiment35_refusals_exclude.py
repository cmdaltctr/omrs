"""Experiment 35 re-gate sample: ``refusals35.py sample --exclude`` (owner decision 2026-11-24).

The first gate sample failed on refusal recall. The owner approved a new sample with a
new seed from the same session answers. It must hold no claim of the first sample and
no claim used as a prompt example, in the sample or in the example pool. An exclude
file is a saved ``sample.json`` (its items' claim keys) or a prompt-example list (each
``qid`` and ``claim``). ``sample.json`` records the file names and the dropped count.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import load
from tests.test_experiment35_refusals import _folders, _questions

refusals35 = load("refusals35")
claimkinds35 = load("claimkinds35")
claimcontext35 = load("claimcontext35")


def _main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, out: Path, *extra: str, n: int = 100
) -> None:
    folders = _folders(tmp_path / "src")
    monkeypatch.setattr(refusals35, "_questions", lambda _names: _questions(folders))
    argv = ["sample", "--seed", "20261142", "--n", str(n), "--out-dir", str(out)]
    argv += [f"--folder={d}={p}" for d, p in folders.items()]
    assert refusals35.main([*argv, *extra]) == 0


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_excluded_keys_reads_a_sample_file_and_an_examples_list(tmp_path: Path) -> None:
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps({"items": [{"claim_key": "k1"}, {"claim_key": "k2"}]}))
    examples = tmp_path / "examples.json"
    examples.write_text(json.dumps([{"qid": "q1", "claim": "c1", "kind": "refusal"}]))
    found = claimcontext35.excluded_keys([sample, examples])
    assert found == {"k1", "k2", claimkinds35.claim_key("q1", "c1")}


def test_an_exclude_file_of_another_shape_is_refused(tmp_path: Path) -> None:
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"labels": {}}))
    with pytest.raises(claimcontext35.SampleError, match="other.json"):
        claimcontext35.excluded_keys([other])


def test_sample_exclude_drops_the_first_sample_and_the_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "gate"
    _main(tmp_path, monkeypatch, first)
    pool = _read(first / "examples-pool.json")
    examples = tmp_path / "classify-examples.json"
    chosen = [{"qid": c["qid"], "claim": c["claim"], "kind": "factual"} for c in pool[:2]]
    examples.write_text(json.dumps(chosen))
    second = tmp_path / "gate2"
    _main(
        tmp_path,
        monkeypatch,
        second,
        "--exclude",
        str(first / "sample.json"),
        "--exclude",
        str(examples),
        n=60,  # the fixture leaves about 27 claims per dataset; a quota is not refilled
    )
    drawn = _read(second / "sample.json")
    banned = {i["claim_key"] for i in _read(first / "sample.json")["items"]}
    banned |= {claimkinds35.claim_key(e["qid"], e["claim"]) for e in chosen}
    kept = {i["claim_key"] for i in drawn["items"]}
    kept |= {c["claim_key"] for c in _read(second / "examples-pool.json")}
    assert len(banned) == 102 and not banned & kept
    assert len(kept) == 205 - 102  # every other claim is in the sample or the pool
    assert len(drawn["items"]) == 60 and drawn["seed"] == 20261142
    assert drawn["excluded"] == {"files": ["sample.json", "classify-examples.json"], "claims": 102}


def test_a_sample_without_exclude_records_no_excluded_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "gate"
    _main(tmp_path, monkeypatch, out)
    assert "excluded" not in _read(out / "sample.json")
