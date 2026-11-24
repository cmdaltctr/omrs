"""Checks on pod_setup35.sh, the Experiment 35 pod preparation (task 9.2, gap G4).

Stub commands first on ``PATH`` stand in for ``uv``, ``curl``, ``wget``,
``nvidia-smi`` and ``uname``. Each stub logs its arguments and changes nothing,
so no test installs, downloads or reaches the network (``HF_HUB_OFFLINE=1``
blocks the Hugging Face client as well).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest

from omrs.core.experiment_records.runtime_block import RuntimeBlock

HERE = Path(__file__).parent
SCRIPT = HERE / "pod_setup35.sh"
REPO = HERE.parents[2]
PLAN = json.loads((HERE.parent / "plan.json").read_text(encoding="utf-8"))
MODELS = PLAN["runtime"]["models"]
#: Reranker test inputs for the task 15.10 check (gap G2); plan.json pins them since it passed.
CANDIDATES = HERE / "rerank_candidates.json"
CANDIDATE_STATUS = "candidate, not pinned; pinned only after the task 15.10 check"
CANDIDATE_ROLES = ["reranker-0.6b", "reranker-4b", "reranker-8b"]
PENDING = {item["key"] for item in PLAN["pins"]["pending"]}
TOKEN = "hf_SECRET_TOKEN_VALUE_0451"  # noqa: S105 - a fake value the output must not show
WRONG = b"not the model\n"
NETWORK_TOOLS = ("uv", "curl", "wget", "nvidia-smi")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stubs(tmp_path: Path, *, linux: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    tools = {name: "" for name in NETWORK_TOOLS}
    tools["nvidia-smi"] = (
        'case "$*" in *--query-gpu*) echo "NVIDIA GeForce RTX 4090, 24564 MiB" ;; '
        '*) echo "| NVIDIA-SMI 580.95   Driver Version: 580.95   CUDA Version: 13.2 |" ;; esac\n'
    )
    scripts = {name: f'echo "{name} $*" >> "{log}"\n{body}' for name, body in tools.items()}
    if linux:
        scripts["uname"] = "echo Linux\n"
    for name, body in scripts.items():
        stub = bin_dir / name
        stub.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
        stub.chmod(0o755)
    return bin_dir


def _inputs(tmp_path: Path, *, recorded: str | None = None) -> Path:
    folder = tmp_path / "inputs"
    folder.mkdir()
    (tmp_path / "note.txt").write_text("fixture\n", encoding="utf-8")
    archive = folder / "exp35-inputs.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tmp_path / "note.txt", arcname="note.txt")
    digest = recorded or _sha(archive.read_bytes())
    (folder / "exp35-inputs.tgz.sha256").write_text(f"{digest}  exp35-inputs.tgz\n", "utf-8")
    return folder


def _run(
    tmp_path: Path, *args: str, linux: bool = False, recorded: str | None = None
) -> subprocess.CompletedProcess[str]:
    bin_dir = _stubs(tmp_path, linux=linux)
    home = tmp_path / "home"
    home.mkdir()
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(home),
        "HF_HUB_OFFLINE": "1",
        "HF_TOKEN": TOKEN,
        "SWEEP_GGUF_DIR": str(tmp_path / "gguf"),
    }
    paths = ["--passages-dir", str(tmp_path / "passages"), "--ragas-venv", str(tmp_path / "rv")]
    paths += ["--ref-venv", str(tmp_path / "ref")]
    inputs = str(_inputs(tmp_path, recorded=recorded))
    command = ["bash", str(SCRIPT), "--commit", head, "--inputs", inputs, *paths, *args]
    return subprocess.run(
        command, env=env, capture_output=True, text=True, timeout=120, check=False
    )


def _calls(tmp_path: Path) -> str:
    log = tmp_path / "calls.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def test_dry_run_prints_every_step_and_calls_no_network_tool(tmp_path: Path) -> None:
    result = _run(tmp_path, "--dry-run")
    output = result.stdout + result.stderr
    assert _calls(tmp_path) == ""
    assert "uv sync --frozen --extra web --extra llamacpp --extra hybrid" in output
    assert "omrs llamacpp install --flavour cuda" in output
    for model in MODELS:
        url = re.escape(f"https://huggingface.co/{model['repository']}/resolve/")
        assert re.search(url + r"[0-9a-f]{40}/" + re.escape(model["file"]), output), model["file"]
        assert model["sha256"] in output
    assert "Qwen/Qwen3-Embedding-4B/resolve/5cf2132abc99cad020ac570b19d031efec650f2b" in output
    assert "uv export --frozen --only-group ragas" in output
    assert "prepare35.py --dataset freshstack" in output
    assert "prepare35.py --dataset bioasq" in output
    assert TOKEN not in output
    assert not any((tmp_path / name).exists() for name in ("gguf", "passages", "rv", "ref"))
    assert list((tmp_path / "home").iterdir()) == []
    problems = [line for line in output.splitlines() if "PROBLEM:" in line]
    assert all(any(key in line for key in PENDING) for line in problems), problems
    assert result.returncode == (1 if problems else 0)


def _candidates() -> list[dict]:
    return json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]


def test_the_reranker_candidates_are_runtime_entries_and_plan_json_pins_them_unchanged() -> None:
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    assert data["status"] == CANDIDATE_STATUS
    entries = [candidate["entry"] for candidate in data["candidates"]]
    assert [entry["role"] for entry in entries] == CANDIDATE_ROLES
    for candidate, entry in zip(data["candidates"], entries, strict=True):
        assert re.fullmatch(r"[0-9a-f]{40}", candidate["revision"]), entry["role"]
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), entry["role"]
        assert isinstance(candidate["bytes"], int) and candidate["bytes"] > 0
        assert entry["role"].removeprefix("reranker-") in entry["file"].lower()
        args = entry["server_args"]  # readiness design D27 item 5
        assert {"embeddings": True, "pooling": "rank", "ctx-size": 8192}.items() <= args.items()
        assert args["batch-size"] == args["ubatch-size"]
    # rerank_check35.py llamacpp --entry reads one entry: one runtime model object.
    tolerance = [{"metric": "spearman", "max_abs_change": 0.0}]
    block = RuntimeBlock.model_validate({"models": entries, "tolerance": tolerance})
    assert {model.build for model in block.models} == {model["build"] for model in MODELS}
    # Task 15.10 passed on 2026-11-24: plan.json pins each candidate entry as it was checked,
    # plus only `parallel: 1` (protocol section 7, one-slot reranker amendment, 2026-11-24).
    pinned = {model["role"]: model for model in MODELS}
    one_slot = [{**e, "server_args": {**e["server_args"], "parallel": 1}} for e in entries]
    assert [pinned[entry["role"]] for entry in entries] == one_slot


def test_dry_run_lists_each_pinned_reranker_once_with_its_revision_and_sha256(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, "--dry-run")
    output = result.stdout + result.stderr
    assert _calls(tmp_path) == ""
    for candidate in _candidates():
        entry = candidate["entry"]
        url = "https://huggingface.co/{}/resolve/{}/{}".format(
            entry["repository"], candidate["revision"], entry["file"]
        )
        assert output.count(url) == 1, entry["role"]
        assert entry["sha256"] in output, entry["role"]
    # A candidate that plan.json pins is fetched as a plan.json model, not as a candidate.
    assert "candidate for the task 15.10 check, not pinned" not in output
    assert not (tmp_path / "gguf").exists()


def test_a_gguf_file_with_another_sha256_stops_the_real_run(tmp_path: Path) -> None:
    gguf = tmp_path / "gguf"
    gguf.mkdir()
    for model in MODELS:
        (gguf / model["file"]).write_bytes(WRONG)
    result = _run(tmp_path, linux=True)
    first = MODELS[0]
    assert result.returncode == 1
    assert "STOP: SHA-256 differs" in result.stderr
    assert str(gguf / first["file"]) in result.stderr
    assert first["sha256"] in result.stderr and _sha(WRONG) in result.stderr
    assert all((gguf / m["file"]).read_bytes() == WRONG for m in MODELS)
    calls = _calls(tmp_path)
    assert "uv sync --frozen --extra web --extra llamacpp --extra hybrid" in calls
    assert "llamacpp install --flavour cuda" in calls
    assert not any(word in calls for word in ("curl", "wget", " pip ", " venv ", " export "))


def test_an_inputs_tarball_with_another_sha256_stops_before_any_install(tmp_path: Path) -> None:
    result = _run(tmp_path, linux=True, recorded="0" * 64)
    found = _sha((tmp_path / "inputs" / "exp35-inputs.tgz").read_bytes())
    assert result.returncode == 1
    assert "STOP: SHA-256 differs" in result.stderr
    assert "exp35-inputs.tgz" in result.stderr
    assert "0" * 64 in result.stderr and found in result.stderr
    assert _calls(tmp_path) == ""
    assert not (tmp_path / "home" / "Development").exists()


def _gpu_ok(listing: str, cuda: str) -> bool:
    text = SCRIPT.read_text(encoding="utf-8")
    funcs = [
        re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, flags=re.S | re.M)
        for name in ("gpu_is_single_4090", "cuda_at_least")
    ]
    assert all(funcs), "pod_setup35.sh lacks gpu_is_single_4090 or cuda_at_least"
    call = 'gpu_is_single_4090 "$1" && cuda_at_least "$2"\n'
    code = "".join(f.group(0) for f in funcs if f) + call
    done = subprocess.run(["bash", "-c", code, "_", listing, cuda], capture_output=True, timeout=30)
    return done.returncode == 0


@pytest.mark.parametrize(
    ("listing", "cuda", "accepted"),
    [
        ("NVIDIA GeForce RTX 4090, 24564 MiB", "13.2", True),
        ("NVIDIA GeForce RTX 4090, 24564 MiB", "13.0", True),
        ("NVIDIA GeForce RTX 4090, 24564 MiB", "12.8", False),
        ("NVIDIA GeForce RTX 4090, 24564 MiB", "", False),
        ("NVIDIA RTX A6000, 49140 MiB", "13.2", False),
        ("NVIDIA GeForce RTX 4090, 24564 MiB\nNVIDIA GeForce RTX 4090, 24564 MiB", "13.2", False),
        ("", "13.2", False),
    ],
)
def test_the_gpu_check_wants_one_rtx_4090_on_cuda_13_0_or_newer(
    listing: str, cuda: str, accepted: bool
) -> None:
    assert _gpu_ok(listing, cuda) is accepted
