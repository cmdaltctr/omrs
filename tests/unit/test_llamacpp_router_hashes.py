"""SHA-256 checks per listed entry (task 3.4; spec "Listed files checked against recorded SHA-256").

``hashes.json`` caches each file's SHA-256 keyed by path, size and
``mtime_ns``, so a 4 GiB file is not hashed on every start. A changed file
leaves only its entry out (``file-changed``). An entry with no recorded value
runs with the note "File not checked", except a decision entry, which is
refused.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from omrs.integrations.llamacpp_runtime import hashes as hashes_module
from omrs.integrations.llamacpp_runtime.hashes import HashCache
from omrs.integrations.llamacpp_runtime.preset_writer import plan_preset

EMBED = "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
CHAT = "Qwen/Qwen3-4B-GGUF:Q8_0"
CLEF = "Clef/Flash-GGUF:Q8_0"


@dataclass
class Entry:
    model: str
    file: str | None = None
    projector: str | None = None
    sha256: str | None = None
    projector_sha256: str | None = None
    preset: dict[str, Any] = field(default_factory=dict)


def _file(folder: Path, name: str, data: bytes) -> tuple[str, str]:
    path = folder / name
    path.write_bytes(data)
    return str(path), hashlib.sha256(data).hexdigest()


@pytest.fixture
def cache(tmp_path: Path) -> HashCache:
    return HashCache(tmp_path / "router" / "hashes.json")


def test_matching_hash_is_listed_with_no_note(tmp_path: Path, cache: HashCache) -> None:
    path, digest = _file(tmp_path, "c.gguf", b"chat model")
    plan = plan_preset([Entry(CHAT, file=path, sha256=digest)], hashes=cache)
    outcome = plan.outcome(CHAT)
    assert outcome is not None
    assert (outcome.state, outcome.reason, outcome.note) == ("listed", None, None)


def test_changed_file_isolated(tmp_path: Path, cache: HashCache) -> None:
    """Spec scenario "Changed file isolated": Chat fails, embeddings still listed."""
    chat_path, _ = _file(tmp_path, "c.gguf", b"chat model")
    embed_path, embed_digest = _file(tmp_path, "e.gguf", b"embed model")
    chat = Entry(CHAT, file=chat_path, sha256="0" * 64)
    embed = Entry(EMBED, file=embed_path, sha256=embed_digest)

    plan = plan_preset([chat, embed], hashes=cache)

    failed = plan.outcome(CHAT)
    assert failed is not None
    assert (failed.state, failed.reason) == ("failed", "file-changed")
    assert "c.gguf" in failed.reason_text
    assert f"[{CHAT}]" not in plan.text
    assert plan.outcome(EMBED).state == "listed"  # type: ignore[union-attr]
    assert f"[{EMBED}]" in plan.text


def test_changed_projector_isolated(tmp_path: Path, cache: HashCache) -> None:
    model, digest = _file(tmp_path, "clef.gguf", b"clef")
    proj, _ = _file(tmp_path, "mmproj-clef.gguf", b"proj")
    entry = Entry(CLEF, file=model, sha256=digest, projector=proj, projector_sha256="1" * 64)
    outcome = plan_preset([entry], hashes=cache).outcome(CLEF)
    assert outcome is not None
    assert (outcome.reason, "mmproj-clef.gguf" in outcome.reason_text) == ("file-changed", True)


def test_no_recorded_hash_runs_with_a_note(tmp_path: Path, cache: HashCache) -> None:
    path, _ = _file(tmp_path, "c.gguf", b"chat model")
    outcome = plan_preset([Entry(CHAT, file=path)], hashes=cache).outcome(CHAT)
    assert outcome is not None
    assert (outcome.state, outcome.note) == ("listed", "File not checked")


def test_decision_entry_without_a_hash_is_refused(tmp_path: Path, cache: HashCache) -> None:
    model, digest = _file(tmp_path, "clef.gguf", b"clef")
    proj, _ = _file(tmp_path, "mmproj-clef.gguf", b"proj")
    no_hash = Entry(CLEF, file=model, preset={"parallel": 1})
    no_proj_hash = Entry(CLEF, file=model, sha256=digest, projector=proj, preset={"parallel": 1})
    for entry in (no_hash, no_proj_hash):
        plan = plan_preset([entry], decision_models={CLEF}, hashes=cache)
        outcome = plan.outcome(CLEF)
        assert outcome is not None
        assert (outcome.state, outcome.reason) == ("failed", "model-invalid")
        assert "SHA-256" in outcome.reason_text
        assert plan.text == ""


def test_cache_avoids_hashing_twice(
    tmp_path: Path, cache: HashCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, digest = _file(tmp_path, "c.gguf", b"chat model")
    calls: list[str] = []
    real = hashes_module.hash_file

    def counting(target: str) -> str:
        calls.append(target)
        return real(target)

    monkeypatch.setattr(hashes_module, "hash_file", counting)
    assert cache.sha256(path) == digest
    assert HashCache(cache.path).sha256(path) == digest  # a new process reads the file
    assert calls == [path]
    stored = json.loads(cache.path.read_text(encoding="utf-8"))
    info = os.stat(path)
    assert stored[path] == {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": digest}


def test_cache_misses_when_size_or_mtime_changes(tmp_path: Path, cache: HashCache) -> None:
    path, first = _file(tmp_path, "c.gguf", b"chat model")
    assert cache.sha256(path) == first
    Path(path).write_bytes(b"chat model, longer now")
    second = hashlib.sha256(b"chat model, longer now").hexdigest()
    assert cache.sha256(path) == second
    info = os.stat(path)
    Path(path).write_bytes(b"chat model, LONGER NOW")  # same size, new mtime
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
    assert cache.sha256(path) == hashlib.sha256(b"chat model, LONGER NOW").hexdigest()


def test_broken_cache_file_reads_as_empty(tmp_path: Path, cache: HashCache) -> None:
    cache.path.parent.mkdir(parents=True)
    cache.path.write_text("{not json", encoding="utf-8")
    path, digest = _file(tmp_path, "c.gguf", b"chat model")
    assert cache.sha256(path) == digest


def test_missing_file_hashes_to_none(tmp_path: Path, cache: HashCache) -> None:
    assert cache.sha256(str(tmp_path / "gone.gguf")) is None
