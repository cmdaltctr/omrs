"""Experiment 35 reranker rank check: the llama.cpp and reference sides (task 15.10, G12).

``rerank_scorers35.py`` holds the two run steps behind ``rerank_check35.py
llamacpp`` and ``reference``. ``llamacpp`` calls ``guard_run`` with
``prefreeze=True`` before any scoring (task 16.35), starts the managed router
unless a base URL is given, and records the model identity. ``reference``
refuses while a llama.cpp server answers (an 8B reference and an 8B server do
not fit 24 GB together) and for 4B and 8B on the CPU without ``--allow-cpu``,
then writes one pre-freeze run record. The scorers, the router reply and the
server probe are stubs; a temporary git repository gives the run record a
commit. No test sends a network request.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from experiments._lib import llamacpp_runtime
from experiments._lib.preflight import PreflightError
from tests._exp35_fixtures import load

check = load("rerank_check35")
scorers = load("rerank_scorers35")
datasets35 = load("datasets35")

FILE = "Qwen3-Reranker-0.6B-Q8_0.gguf"
WEIGHTS = b"reranker weights"
BUILD = 11941
START = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


def _pool(n: int) -> list[dict[str, str]]:
    pairs = [{"pair_id": f"p{i:04d}", "query": f"q{i}", "passage": f"text {i}"} for i in range(n)]
    return pairs + [dict(anchor) for anchor in check.ANCHORS]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


# --- llamacpp: the router side ---------------------------------------------------------


def test_llamacpp_scores_send_one_pair_per_request() -> None:
    sent: list[tuple[str, dict[str, Any]]] = []

    def post(url: str, body: dict[str, Any]) -> dict[str, Any]:
        sent.append((url, body))
        return {"results": [{"index": 0, "relevance_score": 0.25 * len(sent)}]}

    pairs = _pool(3)[:3]
    scores = scorers.llamacpp_scores(pairs, base_url="http://127.0.0.1:8080", model="rr", post=post)
    assert scores == [0.25, 0.5, 0.75]
    assert sent[0] == (
        "http://127.0.0.1:8080/v1/rerank",
        {"model": "rr", "query": "q0", "documents": ["text 0"]},
    )


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


def _entry(sha: str) -> dict[str, Any]:
    return {
        "role": "reranker-0.6b",
        "repository": "ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF",
        "file": FILE,
        "sha256": sha,
        "runtime": "llama.cpp",
        "build": BUILD,
        "server_args": {"pooling": "rank"},
    }


class _Calls:
    def __init__(self) -> None:
        self.log: list[str] = []

    def llama(self, pairs: list[dict[str, Any]], **_: Any) -> list[float]:
        self.log.append("score")
        return [float(i) / len(pairs) for i in range(len(pairs))]

    @contextmanager
    def external(self, base_url: str = "http://127.0.0.1:9") -> Iterator[tuple[str, str]]:
        self.log.append("enter")
        yield base_url, "rr"
        self.log.append("leave")


def _clock() -> Any:
    times = iter([START, START + timedelta(minutes=7)])
    return lambda: next(times)


def _run_llamacpp(folder: Path, sha: str, out: Path, calls: _Calls, **kwargs: Any) -> Any:
    return scorers.run_llamacpp(
        folder,
        _entry(sha),
        check.draw_pairs(_pool(250)),
        out=out,
        router=calls.external(),
        kind="external",
        pairs_sha256="c" * 64,
        score=calls.llama,
        now=_clock(),
        command="rerank_check35.py llamacpp",
        **kwargs,
    )


def test_llamacpp_refuses_to_start_when_the_runtime_check_fails(
    folder: Path, tmp_path: Path
) -> None:
    def failing_guard(*args: Any, **kwargs: Any) -> Any:
        raise PreflightError("the SHA-256 differs from the plan")

    calls = _Calls()
    out = tmp_path / "out"
    with pytest.raises(PreflightError):
        _run_llamacpp(folder, "2" * 64, out, calls, guard=failing_guard)
    assert calls.log == ["enter"]
    assert not out.exists()


def test_llamacpp_with_a_wrong_file_hash_refuses_before_scoring(
    folder: Path, router: None, tmp_path: Path
) -> None:
    calls = _Calls()
    with pytest.raises(PreflightError, match="SHA-256"):
        _run_llamacpp(folder, "1" * 64, tmp_path / "out", calls)
    assert "score" not in calls.log
    assert not (folder / "output" / "run-records.jsonl").exists()


def test_llamacpp_writes_one_prefreeze_record_both_times_and_the_model_identity(
    folder: Path, router: None, tmp_path: Path
) -> None:
    calls = _Calls()
    out = tmp_path / "out"
    sha = hashlib.sha256(WEIGHTS).hexdigest()
    _run_llamacpp(folder, sha, out, calls)
    assert calls.log == ["enter", "score", "leave"]
    (line,) = (folder / "output" / "run-records.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["prefreeze"] is True
    assert record["command"] == "rerank_check35.py llamacpp"
    assert record["runtime"]["models"] == [{"file": FILE, "sha256": sha}]
    text = (out / f"{FILE}.llamacpp.json").read_text(encoding="utf-8")
    result = json.loads(text)
    assert result["started_at"] == "2026-11-20T09:00:00+00:00"
    assert result["finished_at"] == "2026-11-20T09:07:00+00:00"
    assert (result["sha256"], result["build"], result["model"]) == (sha, BUILD, "rr")
    assert result["repository"] == "ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF"
    assert result["pairs_sha256"] == "c" * 64
    assert len(result["scores"]) == 202
    assert check.ANCHORS[0]["passage"] not in text


def test_llamacpp_starts_the_managed_router_unless_a_base_url_is_given(
    folder: Path, router: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = hashlib.sha256(WEIGHTS).hexdigest()
    entry = tmp_path / "entry.json"
    entry.write_text(json.dumps(_entry(sha)), encoding="utf-8")
    pairs = _write_jsonl(tmp_path / "pairs.jsonl", check.draw_pairs(_pool(250)))
    calls = _Calls()
    started: list[tuple[str, Path]] = []

    @contextmanager
    def managed(model: dict[str, Any], work: Path) -> Iterator[tuple[str, str]]:
        started.append((model["file"], work))
        with calls.external() as found:
            yield found

    monkeypatch.setattr(check, "EXP_DIR", folder)
    monkeypatch.setattr(scorers, "llamacpp_scores", calls.llama)
    monkeypatch.setattr(scorers, "managed_router", managed)
    argv = ["llamacpp", "--pairs", str(pairs), "--entry", str(entry)]
    assert check.main([*argv, "--out", str(tmp_path / "a")]) == 0
    assert started == [(FILE, tmp_path / "a" / "router")]
    assert calls.log == ["enter", "score", "leave"]
    base = ["--base-url", "http://127.0.0.1:9", "--model", "rr"]
    assert check.main([*argv, *base, "--out", str(tmp_path / "b")]) == 0
    assert len(started) == 1
    result = json.loads((tmp_path / "b" / f"{FILE}.llamacpp.json").read_text(encoding="utf-8"))
    assert (result["router"], result["base_url"]) == ("external", "http://127.0.0.1:9")
    assert result["pairs_sha256"] == datasets35.file_sha256(pairs)


# --- reference: the transformers side --------------------------------------------------


class _Reference:
    def __init__(self, *, live: bool = False, gpu: str | None = "NVIDIA GeForce RTX 4090") -> None:
        self.live, self.gpu = live, gpu
        self.log: list[str] = []

    def probe(self, url: str) -> bool:
        self.log.append(f"probe {url}")
        return self.live

    def device(self) -> str | None:
        self.log.append("device")
        return self.gpu

    def score(self, pairs: list[dict[str, Any]], **kwargs: Any) -> tuple[list[float], dict]:
        self.log.append(f"score {kwargs['device']}")
        info = {"dtype": "bfloat16", "torch": "2.13.0", "transformers": "5.15.0"}
        return [float(i) / len(pairs) for i in range(len(pairs))], info


def _run_reference(folder: Path, out: Path, fake: _Reference, model: str, **kwargs: Any) -> Any:
    return scorers.run_reference(
        folder,
        check.draw_pairs(_pool(250)),
        model_id=model,
        revision="f" * 40,
        out=out,
        server_url="http://127.0.0.1:18080",
        pairs_sha256="c" * 64,
        live=fake.probe,
        device=fake.device,
        score=fake.score,
        now=_clock(),
        command="rerank_check35.py reference",
        **kwargs,
    )


def test_reference_refuses_while_a_llamacpp_server_answers(folder: Path, tmp_path: Path) -> None:
    fake = _Reference(live=True)
    with pytest.raises(scorers.CheckRefused, match="24 GB"):
        _run_reference(folder, tmp_path / "out", fake, "Qwen/Qwen3-Reranker-8B")
    assert fake.log == ["probe http://127.0.0.1:18080"]
    assert not (tmp_path / "out").exists()
    assert not (folder / "output" / "run-records.jsonl").exists()


def test_reference_refuses_4b_and_8b_on_the_cpu_without_allow_cpu(
    folder: Path, tmp_path: Path
) -> None:
    for size in ("4B", "8B"):
        fake = _Reference(gpu=None)
        with pytest.raises(scorers.CheckRefused, match="--allow-cpu"):
            _run_reference(folder, tmp_path / "out", fake, f"Qwen/Qwen3-Reranker-{size}")
        assert not any(step.startswith("score") for step in fake.log)
    assert not (folder / "output" / "run-records.jsonl").exists()
    small = _Reference(gpu=None)
    _run_reference(folder, tmp_path / "out", small, "Qwen/Qwen3-Reranker-0.6B")
    assert small.log[-1] == "score cpu"
    forced = _Reference(gpu=None)
    _run_reference(folder, tmp_path / "out", forced, "Qwen/Qwen3-Reranker-8B", allow_cpu=True)
    assert forced.log[-1] == "score cpu"


def test_reference_writes_one_prefreeze_record_and_both_times(folder: Path, tmp_path: Path) -> None:
    fake = _Reference()
    out = tmp_path / "out"
    _run_reference(folder, out, fake, "Qwen/Qwen3-Reranker-8B")
    assert fake.log[-1] == "score cuda"
    (line,) = (folder / "output" / "run-records.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["prefreeze"] is True
    assert record["command"] == "rerank_check35.py reference"
    text = (out / "reference-Qwen3-Reranker-8B.json").read_text(encoding="utf-8")
    result = json.loads(text)
    assert result["started_at"] == "2026-11-20T09:00:00+00:00"
    assert result["finished_at"] == "2026-11-20T09:07:00+00:00"
    assert (result["hf_model"], result["hf_revision"]) == ("Qwen/Qwen3-Reranker-8B", "f" * 40)
    assert (result["gpu"], result["dtype"]) == ("NVIDIA GeForce RTX 4090", "bfloat16")
    assert len(result["scores"]) == 202
    assert check.ANCHORS[0]["passage"] not in text


def test_reference_command_refuses_with_exit_2_while_a_server_answers(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _Reference(live=True)
    monkeypatch.setattr(check, "EXP_DIR", folder)
    monkeypatch.setattr(scorers, "server_live", fake.probe)
    monkeypatch.setattr(scorers, "cuda_device", fake.device)
    monkeypatch.setattr(scorers, "transformers_scores", fake.score)
    pairs = _write_jsonl(tmp_path / "pairs.jsonl", check.draw_pairs(_pool(250)))
    argv = ["reference", "--pairs", str(pairs), "--hf-model", "Qwen/Qwen3-Reranker-8B"]
    argv += ["--hf-revision", "f" * 40, "--out", str(tmp_path / "out")]
    assert check.main(argv) == 2
    assert fake.log == ["probe http://127.0.0.1:18080"]


def test_server_live_reads_any_http_reply_as_live() -> None:
    import urllib.error

    @contextmanager
    def answers(url: str, timeout: float) -> Iterator[None]:
        yield None

    def loading(url: str, timeout: float) -> Any:
        raise urllib.error.HTTPError(url, 503, "Loading model", {}, None)  # type: ignore[arg-type]

    def refused(url: str, timeout: float) -> Any:
        raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))

    assert scorers.server_live("http://127.0.0.1:18080", opener=answers) is True
    assert scorers.server_live("http://127.0.0.1:18080", opener=loading) is True
    assert scorers.server_live("http://127.0.0.1:18080", opener=refused) is False


def test_model_size_reads_the_size_from_the_name() -> None:
    assert scorers.model_size("Qwen/Qwen3-Reranker-0.6B") == "0.6b"
    assert scorers.model_size("Qwen3-Reranker-4B-Q8_0.gguf") == "4b"
    assert scorers.model_size("qwen3-reranker-8b-q8_0.gguf") == "8b"
    with pytest.raises(ValueError, match="size"):
        scorers.model_size("reranker.gguf")


def test_reference_prompt_is_the_model_card_recipe() -> None:
    assert scorers.PREFIX == (
        "<|im_start|>system\nJudge whether the Document meets the requirements based on the "
        'Query and the Instruct provided. Note that the answer can only be "yes" or "no".'
        "<|im_end|>\n<|im_start|>user\n"
    )
    assert scorers.SUFFIX == "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    assert scorers.reference_text("q", "d") == (
        "<Instruct>: Given a web search query, retrieve relevant passages that answer the query"
        "\n<Query>: q\n<Document>: d"
    )
