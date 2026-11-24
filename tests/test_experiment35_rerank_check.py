"""Experiment 35 reranker rank check (task 15.10, M8; task 9.2 step 2a; G12): pool, draw, verdict.

``rerank_check35.py`` has five commands: ``pool`` builds the query-passage
pairs from the prepared datasets with seed 20261117 and two anchor pairs,
``draw`` takes 200 of them, ``llamacpp`` and ``reference`` score them (tests
in ``test_experiment35_rerank_scorers.py``), and ``verdict`` marks a reranker
file "not pinned" when the Spearman correlation is below 0.95, an anchor is
not near 1 or near 0, or a llama.cpp score is not a probability. No test sends
a network request.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import FOLDER, fake_plan, load, make_data_root

check = load("rerank_check35")
datasets35 = load("datasets35")
prepare35 = load("prepare35")

FILE = "Qwen3-Reranker-0.6B-Q8_0.gguf"
BUILD = 11941
START = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
RELEVANT, IRRELEVANT = check.ANCHOR_IDS


def _pool(n: int) -> list[dict[str, str]]:
    pairs = [{"pair_id": f"p{i:04d}", "query": f"q{i}", "passage": f"text {i}"} for i in range(n)]
    return pairs + [dict(anchor) for anchor in check.ANCHORS]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


# --- the command line ------------------------------------------------------------------


def test_the_cli_runs_as_a_script_and_lists_the_five_commands() -> None:
    found = subprocess.run(
        [sys.executable, str(FOLDER / "rerank_check35.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert found.returncode == 0, found.stderr
    for command in ("pool", "draw", "llamacpp", "reference", "verdict"):
        assert command in found.stdout


def test_importing_the_check_does_not_import_torch() -> None:
    code = (
        "import sys\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('torch', 'transformers'):\n"
        "            raise ImportError(name + ' imported at module import')\n"
        "sys.meta_path.insert(0, Block())\n"
        f"sys.path[:0] = [{str(FOLDER.parents[1])!r}, {str(FOLDER)!r}]\n"
        "import rerank_check35, rerank_scorers35\n"
        "print('imported' if 'torch' not in sys.modules else 'torch loaded')\n"
    )
    found = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False, timeout=120
    )
    assert found.returncode == 0, found.stderr
    assert found.stdout.strip() == "imported"


# --- pool: pairs from the prepared datasets --------------------------------------------


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fixture data folder and its prepared BioASQ and FreshStack passages."""
    root = make_data_root(tmp_path / "DATA")
    for name in ("bioasq", "freshstack"):
        rels = datasets35.EXPECTED_SHA256[name]
        monkeypatch.setitem(
            datasets35.EXPECTED_SHA256,
            name,
            {rel: datasets35.file_sha256(root / rel) for rel in rels},
        )
        prepare35.prepare(name, root, tmp_path / "passages", plan=fake_plan())
    monkeypatch.setenv(datasets35.DATA_DIR_ENV, str(root))
    monkeypatch.setattr(check, "POOL_QUERIES", 3)
    monkeypatch.setattr(check, "POOL_GOLD", 2)
    monkeypatch.setattr(check, "POOL_OTHERS", 3)
    return tmp_path / "passages"


def _build_pool(passages: Path, out: Path) -> list[dict[str, Any]]:
    argv = ["pool", "--dataset", "freshstack", "--dataset", "bioasq"]
    assert check.main([*argv, "--passages-dir", str(passages), "--out", str(out)]) == 0
    lines = (out / "pool.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_pool_is_the_same_twice_and_holds_gold_other_and_anchor_pairs(
    prepared: Path, tmp_path: Path
) -> None:
    pool = _build_pool(prepared, tmp_path / "a")
    assert _build_pool(prepared, tmp_path / "b") == pool
    assert check.SEED == 20261117
    assert [p["pair_id"] for p in pool[-2:]] == [RELEVANT, IRRELEVANT]
    assert len({p["pair_id"] for p in pool}) == len(pool)
    root = Path(os.environ[datasets35.DATA_DIR_ENV])
    gold = {
        (name, q.qid): set(q.relevant)
        for name in ("bioasq", "freshstack")
        for q in datasets35.load_questions(name, root)
    }
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for pair in pool[:-2]:
        groups.setdefault((pair["dataset"], pair["qid"]), []).append(pair)
    assert sorted({name for name, _ in groups}) == ["bioasq", "freshstack"]
    assert sum(1 for name, _ in groups if name == "bioasq") == 3
    for key, pairs in groups.items():
        kinds = [p["kind"] for p in pairs]
        assert kinds.count("other") == 3
        assert kinds.count("gold") == min(2, len(gold[key]))
        for pair in pairs:
            assert (pair["unit"] in gold[key]) is (pair["kind"] == "gold")
    summary = json.loads((tmp_path / "a" / "pool-summary.json").read_text(encoding="utf-8"))
    assert summary["seed"] == 20261117
    assert summary["pool_sha256"] == datasets35.file_sha256(tmp_path / "a" / "pool.jsonl")
    tree = datasets35.verify_tree(prepared / "bioasq")
    assert summary["datasets"]["bioasq"]["passages_tree_sha256"] == tree


def test_pool_changes_with_the_seed(
    prepared: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = _build_pool(prepared, tmp_path / "a")
    monkeypatch.setattr(check, "SEED", check.SEED + 1)
    assert _build_pool(prepared, tmp_path / "b") != pool


def test_pool_caps_the_query_and_the_passage_text(
    prepared: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check, "MAX_CHARS", 9)
    pool = _build_pool(prepared, tmp_path / "a")
    assert max(len(p["query"]) for p in pool[:-2]) == 9
    assert max(len(p["passage"]) for p in pool[:-2]) == 9
    assert pool[-2:] == [dict(anchor) for anchor in check.ANCHORS]


# --- draw ------------------------------------------------------------------------------


def test_the_200_pairs_are_the_same_twice_and_ignore_pool_order() -> None:
    pool = _pool(600)
    first = check.draw_pairs(pool)
    assert len(first) == check.PAIRS + 2
    assert check.PAIRS == 200
    assert len({p["pair_id"] for p in first}) == 202
    assert check.draw_pairs(pool) == first
    assert check.draw_pairs(list(reversed(pool))) == first


def test_draw_keeps_both_anchors_outside_the_200() -> None:
    drawn = check.draw_pairs(_pool(200))
    assert [p["pair_id"] for p in drawn[:200]] == [f"p{i:04d}" for i in range(200)]
    assert drawn[200:] == [dict(anchor) for anchor in check.ANCHORS]
    with pytest.raises(ValueError, match="anchor"):
        check.draw_pairs(_pool(300)[:-1])


def test_draw_refuses_a_small_pool_and_a_repeated_pair_id() -> None:
    with pytest.raises(ValueError, match="199"):
        check.draw_pairs(_pool(199))
    with pytest.raises(ValueError, match="p0000"):
        check.draw_pairs([*_pool(300), _pool(1)[0]])


def test_draw_command_writes_the_pairs_file(tmp_path: Path) -> None:
    pool = _write_jsonl(tmp_path / "pool.jsonl", _pool(300))
    out = tmp_path / "out"
    assert check.main(["draw", "--pool", str(pool), "--out", str(out)]) == 0
    lines = (out / "pairs.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == check.draw_pairs(_pool(300))


# --- verdict ---------------------------------------------------------------------------


def _scores(values: list[float], relevant: float = 0.99, irrelevant: float = 0.01) -> dict:
    found = {f"p{i:04d}": v for i, v in enumerate(values)}
    return {**found, RELEVANT: relevant, IRRELEVANT: irrelevant}


def test_perfect_rank_agreement_is_pinned() -> None:
    result = check.verdict(
        _scores([i / 200 for i in range(200)]), _scores([i / 400 for i in range(200)])
    )
    assert result["spearman"] == pytest.approx(1.0)
    assert result["pairs"] == 200
    assert result["pinned"] is True
    assert result["status"] == "pinned"
    assert result["reasons"] == []


def test_spearman_below_095_marks_the_file_not_pinned() -> None:
    llama = [i / 200 for i in range(200)]
    # Reverse the order inside blocks of 40 ranks: Spearman 1 - 2 * 1599 / 39999, about 0.92.
    reference = list(llama)
    for start in range(0, 200, 40):
        reference[start : start + 40] = reference[start : start + 40][::-1]
    result = check.verdict(_scores(llama), _scores(reference))
    assert result["spearman"] == pytest.approx(1 - 2 * 1599 / 39999)
    assert result["spearman"] < 0.95
    assert result["pinned"] is False
    assert result["status"] == "not pinned"
    assert "Spearman" in result["reasons"][0]


@pytest.mark.filterwarnings("ignore:An input array is constant")
def test_constant_scores_are_not_pinned() -> None:
    result = check.verdict(_scores([0.5] * 200), _scores([i / 200 for i in range(200)]))
    assert result["spearman"] is None
    assert result["status"] == "not pinned"


def test_the_anchors_are_left_out_of_the_spearman() -> None:
    ranks = [i / 200 for i in range(200)]
    # Anchors that disagree between the sides would lower a Spearman that counted them.
    result = check.verdict(_scores(ranks, 0.999, 0.0001), _scores(ranks, 0.91, 0.09))
    assert result["spearman"] == pytest.approx(1.0)
    assert result["pinned"] is True


def test_anchors_outside_the_thresholds_mark_the_file_not_pinned() -> None:
    assert check.ANCHOR_RELEVANT_MIN == 0.9
    assert check.ANCHOR_IRRELEVANT_MAX == 0.1
    ranks = [i / 200 for i in range(200)]
    low = check.verdict(_scores(ranks, relevant=0.89), _scores(ranks))
    assert low["status"] == "not pinned"
    assert low["anchors"]["llamacpp"]["ok"] is False
    assert "llamacpp anchors" in low["reasons"][0]
    high = check.verdict(_scores(ranks), _scores(ranks, irrelevant=0.11))
    assert high["status"] == "not pinned"
    assert high["anchors"]["reference"]["ok"] is False
    edge = check.verdict(_scores(ranks, 0.9, 0.1), _scores(ranks, 0.9, 0.1))
    assert edge["pinned"] is True


def test_a_llamacpp_score_outside_0_1_marks_the_file_not_pinned() -> None:
    ranks = [i / 200 for i in range(200)]
    result = check.verdict(_scores([*ranks[:-1], 1.5]), _scores(ranks))
    assert result["spearman"] == pytest.approx(1.0)
    assert result["probabilities"] is False
    assert result["status"] == "not pinned"
    assert "12.2" in result["reasons"][0]


def _score_file(path: Path, side: str, scores: dict[str, float], **extra: Any) -> Path:
    body = {
        "side": side,
        "pairs_sha256": "c" * 64,
        "started_at": START.isoformat(),
        "finished_at": (START + timedelta(minutes=3)).isoformat(),
        "scores": [{"pair_id": k, "score": v} for k, v in scores.items()],
        **extra,
    }
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _llama_file(path: Path, scores: dict[str, float], **extra: Any) -> Path:
    identity = {"file": FILE, "repository": "ggml-org/x", "sha256": "a" * 64, "build": BUILD}
    return _score_file(path, "llamacpp", scores, **{**identity, **extra})


def _reference_file(path: Path, scores: dict[str, float], **extra: Any) -> Path:
    identity = {"hf_model": "Qwen/Qwen3-Reranker-0.6B", "hf_revision": "f" * 40}
    return _score_file(path, "reference", scores, **{**identity, **extra})


def test_verdict_command_writes_the_check_file_and_exits_3_when_not_pinned(
    tmp_path: Path,
) -> None:
    ranks = [i / 200 for i in range(200)]
    llama = _llama_file(tmp_path / "l.json", _scores(ranks))
    ref = _reference_file(tmp_path / "r.json", _scores(ranks))
    out = tmp_path / "out"
    argv = ["verdict", "--llamacpp", str(llama), "--reference", str(ref), "--out", str(out)]
    assert check.main(argv) == 0
    result = json.loads((out / f"{FILE}.rerank-check.json").read_text(encoding="utf-8"))
    assert result["status"] == "pinned"
    assert result["seed"] == 20261117
    assert result["sha256"] == "a" * 64
    assert result["hf_revision"] == "f" * 40
    assert len(result["scores"]) == 202
    assert set(result["scores"][0]) == {"pair_id", "llamacpp", "reference"}
    _llama_file(llama, _scores(ranks, relevant=0.5))
    assert check.main(argv) == 3
    result = json.loads((out / f"{FILE}.rerank-check.json").read_text(encoding="utf-8"))
    assert result["status"] == "not pinned"


def test_verdict_refuses_files_from_other_pairs_another_size_or_count(tmp_path: Path) -> None:
    ranks = [i / 200 for i in range(200)]
    llama = _llama_file(tmp_path / "l.json", _scores(ranks))
    out = tmp_path / "out"

    def run(reference: Path) -> int:
        argv = ["verdict", "--llamacpp", str(llama), "--reference", str(reference)]
        return int(check.main([*argv, "--out", str(out)]))

    assert run(_reference_file(tmp_path / "r1.json", _scores(ranks), pairs_sha256="d" * 64)) == 2
    other = _reference_file(tmp_path / "r2.json", _scores(ranks), hf_model="Qwen/Qwen3-Reranker-4B")
    assert run(other) == 2
    _llama_file(llama, _scores(ranks[:199]))
    assert run(_reference_file(tmp_path / "r3.json", _scores(ranks[:199]))) == 2
    assert not out.exists()
