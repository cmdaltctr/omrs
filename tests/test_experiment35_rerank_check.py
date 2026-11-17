"""Experiment 35 reranker rank check (task 15.10, M8) and its run record (task 16.35, H-31).

``rerank_check35.py`` draws 200 query-passage pairs with seed 20261117, scores
them with llama-server and with the transformers recipe, and marks a reranker
file "not pinned" when the Spearman correlation is below 0.95. Before any
scoring it calls ``guard_run`` with ``prefreeze=True``. The scorers and the
router reply are stubs; a temporary git repository gives the guard a commit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from experiments._lib import llamacpp_runtime
from experiments._lib.preflight import PreflightError
from tests._exp35_fixtures import load

from omrs.core.experiment_records.runtime_block import RuntimeBlock

check = load("rerank_check35")

FILE = "Qwen3-Reranker-0.6B-Q8_0.gguf"
WEIGHTS = b"reranker weights"
BUILD = 11941
START = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


def _pool(n: int) -> list[dict[str, str]]:
    return [{"pair_id": f"p{i:04d}", "query": f"q{i}", "passage": f"text {i}"} for i in range(n)]


# --- 15.10 draw ------------------------------------------------------------------------


def test_the_200_pairs_are_the_same_twice_and_ignore_pool_order() -> None:
    pool = _pool(600)
    first = check.draw_pairs(pool)
    assert len(first) == check.PAIRS == 200
    assert check.SEED == 20261117
    assert len({p["pair_id"] for p in first}) == 200
    assert check.draw_pairs(pool) == first
    assert check.draw_pairs(list(reversed(pool))) == first


def test_draw_refuses_a_small_pool_and_a_repeated_pair_id() -> None:
    with pytest.raises(ValueError, match="199"):
        check.draw_pairs(_pool(199))
    with pytest.raises(ValueError, match="p0000"):
        check.draw_pairs([*_pool(300), _pool(1)[0]])


def test_draw_command_writes_the_pairs_file(tmp_path: Path) -> None:
    pool = tmp_path / "pool.jsonl"
    pool.write_text("".join(json.dumps(p) + "\n" for p in _pool(300)), encoding="utf-8")
    out = tmp_path / "out"
    assert check.main(["draw", "--pool", str(pool), "--out", str(out)]) == 0
    lines = (out / "pairs.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == check.draw_pairs(_pool(300))


# --- 15.10 verdict ---------------------------------------------------------------------


def test_perfect_rank_agreement_is_pinned() -> None:
    llama = [i / 200 for i in range(200)]
    reference = [i / 400 for i in range(200)]
    result = check.verdict(FILE, llama, reference)
    assert result["spearman"] == pytest.approx(1.0)
    assert result["pinned"] is True
    assert result["status"] == "pinned"


def test_spearman_below_095_marks_the_file_not_pinned() -> None:
    llama = [float(i) for i in range(200)]
    # Reverse the order inside blocks of 40 ranks: Spearman 1 - 2 * 1599 / 39999, about 0.92.
    reference = [float(i) for i in range(200)]
    for start in range(0, 200, 40):
        block = reference[start : start + 40]
        reference[start : start + 40] = block[::-1]
    result = check.verdict(FILE, llama, reference)
    assert result["spearman"] == pytest.approx(1 - 2 * 1599 / 39999)
    assert result["spearman"] < 0.95
    assert result["pinned"] is False
    assert result["status"] == "not pinned"


@pytest.mark.filterwarnings("ignore:An input array is constant")
def test_constant_scores_are_not_pinned() -> None:
    result = check.verdict(FILE, [0.5] * 200, [float(i) for i in range(200)])
    assert result["spearman"] is None
    assert result["status"] == "not pinned"


def test_llamacpp_scores_send_one_pair_per_request() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    def post(url: str, body: dict[str, Any]) -> dict[str, Any]:
        sent.append((url, body))
        return {"results": [{"index": 0, "relevance_score": 0.25 * len(sent)}]}

    pairs = _pool(3)
    scores = check.llamacpp_scores(pairs, base_url="http://127.0.0.1:8080", model="rr", post=post)
    assert scores == [0.25, 0.5, 0.75]
    assert sent[0] == (
        "http://127.0.0.1:8080/v1/rerank",
        {"model": "rr", "query": "q0", "documents": ["text 0"]},
    )


# --- 16.35 run record and times --------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
        cwd=repo,
        capture_output=True,
        check=True,
    )


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An unfrozen, committed experiment folder."""
    for name in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "repo"
    path = repo / "experiments" / "35-full-rag-benchmark-2026-11-01"
    path.mkdir(parents=True)
    _git(repo, "init", "-q")
    (path / "plan.json").write_text('{"frozen": []}\n', encoding="utf-8")
    (path / "preregistration.md").write_text("# Pre-registration\n", encoding="utf-8")
    (repo / ".gitignore").write_text("output/\nweights/\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "--no-verify", "-m", "start")
    return path


@pytest.fixture
def router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    weights = tmp_path / "weights" / FILE
    weights.parent.mkdir()
    weights.write_bytes(WEIGHTS)

    def reply(base_url: str, path: str) -> Any:
        if path == "/props":
            return {"role": "router", "model_path": "none", "build_info": f"b{BUILD}-abc"}
        args = ["llama-server", "--model", str(weights), "--pooling", "rank"]
        return {"data": [{"id": "rr", "status": {"value": "loaded", "args": args}}]}

    monkeypatch.setattr(llamacpp_runtime, "_get_json", reply)


def _block(sha: str) -> RuntimeBlock:
    return check.candidate_block(
        build=BUILD, repository="ggml-org/Qwen3-Reranker-0.6B-GGUF", file=FILE, sha256=sha
    )


class _Scorers:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def llama(self, pairs: list[dict[str, Any]], **_: Any) -> list[float]:
        self.calls.append("llama")
        return [float(i) for i in range(len(pairs))]

    def reference(self, pairs: list[dict[str, Any]]) -> list[float]:
        self.calls.append("reference")
        return [float(i) for i in range(len(pairs))]


def _clock() -> Any:
    times = iter([START, START + timedelta(minutes=7)])
    return lambda: next(times)


def _run(folder: Path, block: RuntimeBlock, out: Path, scorers: _Scorers, **kwargs: Any) -> Any:
    return check.run_check(
        folder,
        block,
        check.draw_pairs(_pool(250)),
        base_url="http://127.0.0.1:9",
        model="rr",
        reference=scorers.reference,
        out=out,
        score=scorers.llama,
        now=_clock(),
        command="rerank_check35.py check",
        **kwargs,
    )


def test_check_refuses_to_start_when_the_runtime_check_fails(folder: Path, tmp_path: Path) -> None:
    def failing_guard(*args: Any, **kwargs: Any) -> Any:
        raise PreflightError("the SHA-256 differs from the plan")

    scorers = _Scorers()
    out = tmp_path / "out"
    with pytest.raises(PreflightError):
        _run(folder, _block("2" * 64), out, scorers, guard=failing_guard)
    assert scorers.calls == []
    assert not out.exists()


def test_check_with_a_wrong_file_hash_refuses_before_scoring(
    folder: Path, router: None, tmp_path: Path
) -> None:
    scorers = _Scorers()
    with pytest.raises(PreflightError, match="SHA-256"):
        _run(folder, _block("1" * 64), tmp_path / "out", scorers)
    assert scorers.calls == []
    assert not (folder / "output" / "run-records.jsonl").exists()


def test_check_writes_one_prefreeze_run_record_and_both_times(
    folder: Path, router: None, tmp_path: Path
) -> None:
    scorers = _Scorers()
    out = tmp_path / "out"
    _run(folder, _block(hashlib.sha256(WEIGHTS).hexdigest()), out, scorers)
    assert scorers.calls == ["llama", "reference"]
    (line,) = (folder / "output" / "run-records.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["prefreeze"] is True
    assert record["command"] == "rerank_check35.py check"
    assert record["runtime"]["models"] == [
        {"file": FILE, "sha256": hashlib.sha256(WEIGHTS).hexdigest()}
    ]
    result = json.loads((out / f"{FILE}.rerank-check.json").read_text(encoding="utf-8"))
    assert result["started_at"] == "2026-11-20T09:00:00+00:00"
    assert result["finished_at"] == "2026-11-20T09:07:00+00:00"
    assert result["status"] == "pinned"
    assert len(result["scores"]) == 200
    assert set(result["scores"][0]) == {"pair_id", "llamacpp", "reference"}
