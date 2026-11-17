"""Experiment 35 ``select35.py`` command (protocol section 5 step 3b, pre-registration 14.2).

The command reads the half-A scores, the sealed index fingerprints and
``halves.json`` from saved files and writes ``<out>/selection.json``. A refusal
prints one clear line and exits 2.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests._exp35_fixtures import fake_plan, load, make_gguf

select35 = load("select35")
datasets35 = load("datasets35")

HALVES = {"financebench": {"f1": "A"}, "freshstack": {"s1": "A"}, "bioasq": {"b1": "A"}}
DIMENSIONS = {"0.6b": 1024, "4b": 2560, "8b": 4096}


def _inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Write half-A scores, fingerprints, halves and plan; return the command line."""
    out = tmp_path / "out"
    for name in select35.SEARCH_SETUPS:
        for dataset, questions in HALVES.items():
            path = out / "scores" / "A" / dataset / f"{name}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            row = {"dataset": dataset, "setup": name, "qid": next(iter(questions))}
            path.write_text(json.dumps({**row, "ndcg_at_10": 0.5}) + "\n", encoding="utf-8")
    for embedder in select35.EMBEDDERS:
        for chunk in select35.CHUNKS:
            for dataset in HALVES:
                path = out / dataset / f"e{embedder}-c{chunk}" / "index-fingerprint.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                body = {"chunks": 10, "embedding_dimension": DIMENSIONS[embedder]}
                path.write_text(json.dumps(body), encoding="utf-8")
    halves = tmp_path / "halves.json"
    halves.write_text(json.dumps({"seed": 1, "halves": HALVES}), encoding="utf-8")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(fake_plan()), encoding="utf-8")
    monkeypatch.setenv("SWEEP_GGUF_DIR", str(make_gguf(tmp_path / "gguf")))
    return ["--out-dir", str(out), "--halves", str(halves), "--plan", str(plan)]


def test_help_names_the_inputs(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        select35.main(["--help"])
    assert caught.value.code == 0
    text = capsys.readouterr().out
    for option in ("--out-dir", "--halves", "--plan"):
        assert option in text


def test_main_writes_selection_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    argv = _inputs(tmp_path, monkeypatch)
    assert select35.main(argv) == 0
    saved = json.loads((tmp_path / "out" / "selection.json").read_text(encoding="utf-8"))
    assert saved["cell"] == "e0.6b-c512-roff-hoff"
    assert saved["halves_sha256"] == datasets35.file_sha256(tmp_path / "halves.json")
    first = saved["configuration_hash"]
    assert select35.main(argv) == 0
    again = json.loads((tmp_path / "out" / "selection.json").read_text(encoding="utf-8"))
    assert again["configuration_hash"] == first


def test_main_exits_2_on_a_missing_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _inputs(tmp_path, monkeypatch)
    (tmp_path / "out" / "scores" / "A" / "bioasq" / "e4b-c1024-r4b-hon.jsonl").unlink()
    assert select35.main(argv) == 2
    assert "[error] setup e4b-c1024-r4b-hon on bioasq lacks" in capsys.readouterr().out
    assert not (tmp_path / "out" / "selection.json").exists()


def test_main_exits_2_on_a_missing_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _inputs(tmp_path, monkeypatch)
    (tmp_path / "out" / "bioasq" / "e8b-c2048" / "index-fingerprint.json").unlink()
    assert select35.main(argv) == 2
    assert "[error]" in capsys.readouterr().out
    assert not (tmp_path / "out" / "selection.json").exists()


def test_main_exits_2_without_the_model_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _inputs(tmp_path, monkeypatch)
    monkeypatch.delenv("SWEEP_GGUF_DIR")
    assert select35.main(argv) == 2
    assert "SWEEP_GGUF_DIR" in capsys.readouterr().out
    assert not (tmp_path / "out" / "selection.json").exists()
