"""The dots-mocr fetch step on llama.cpp (change dots-mocr-llamacpp-backend, task 2.3).

No test touches the network. The two download seams (``download_model_file``
for the private Hugging Face repository and ``download_url`` for the
llama.cpp release) are replaced with fakes that write small files, and the
pinned hashes are replaced with the hashes of those files.
"""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from tests.fixtures.ocr_worker.dots_llamacpp import ENGINE_DIR, engine_modules

MODEL_BYTES = b"model-weights"
PROJECTOR_BYTES = b"projector-weights"
SERVER_SCRIPT = b"#!/bin/sh\necho 'version: 11941 (abc)'\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _archive_bytes() -> bytes:
    """Build a tar.gz shaped like the real release: one folder with the server and a symlink."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        top = tarfile.TarInfo("llama-b11941")
        top.type = tarfile.DIRTYPE
        top.mode = 0o755
        tar.addfile(top)
        server = tarfile.TarInfo("llama-b11941/llama-server")
        server.size = len(SERVER_SCRIPT)
        server.mode = 0o755
        tar.addfile(server, io.BytesIO(SERVER_SCRIPT))
        link = tarfile.TarInfo("llama-b11941/libllama.dylib")
        link.type = tarfile.SYMTYPE
        link.linkname = "libllama.0.dylib"
        tar.addfile(link)
        lib = tarfile.TarInfo("llama-b11941/libllama.0.dylib")
        lib.size = 3
        lib.mode = 0o644
        tar.addfile(lib, io.BytesIO(b"lib"))
    return buffer.getvalue()


class Env:
    """The loaded modules, the call log and the fake downloaders."""

    def __init__(self, fetch: ModuleType, pins: ModuleType, paths: ModuleType) -> None:
        self.fetch, self.pins, self.paths = fetch, pins, paths
        self.model_calls: list[dict[str, Any]] = []
        self.url_calls: list[str] = []
        self.model_payload = {"dots-mocr-Q8_0.gguf": MODEL_BYTES}
        self.archive = _archive_bytes()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Env]:
    """Load the engine modules with a temporary cache and fake pins and downloads."""
    monkeypatch.setenv("OMRS_OCR_MODEL_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with engine_modules(monkeypatch) as load:
        e = Env(load("fetch"), load("pins"), load("paths"))
        files = (
            e.pins.PinnedFile("dots-mocr-Q8_0.gguf", _sha(MODEL_BYTES)),
            e.pins.PinnedFile("dots-mocr-mmproj-bf16.gguf", _sha(PROJECTOR_BYTES)),
        )
        e.model_payload["dots-mocr-mmproj-bf16.gguf"] = PROJECTOR_BYTES
        monkeypatch.setattr(e.pins, "MODEL_FILES", files)
        monkeypatch.setattr(e.pins, "MODEL_REVISION", "a" * 40)
        archive = e.pins.LlamaArchive("llama-b11941-bin-test.tar.gz", _sha(e.archive))
        monkeypatch.setattr(e.pins, "llama_archive", lambda *_a, **_k: archive)
        monkeypatch.setattr(e.fetch, "get_token", lambda: "hf_test_token")

        def fake_model_download(
            repo: str, revision: str, name: str, token: str, local_dir: Path
        ) -> Path:
            e.model_calls.append({"repo": repo, "revision": revision, "name": name, "token": token})
            target = Path(local_dir) / name
            target.write_bytes(e.model_payload[name])
            return target

        def fake_url_download(url: str, destination: Path) -> None:
            e.url_calls.append(url)
            Path(destination).write_bytes(e.archive)

        monkeypatch.setattr(e.fetch, "download_model_file", fake_model_download)
        monkeypatch.setattr(e.fetch, "download_url", fake_url_download)
        yield e


def _leftovers(folder: Path) -> list[str]:
    """Return every path under *folder* (files and folders), relative."""
    if not folder.exists():
        return []
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


# ── Models: the pinned repository, a hash check, no partial file ───────────


def test_model_files_download_at_the_pinned_revision_with_the_token(env: Env) -> None:
    """Both files come from the pinned repository and revision, with the token."""
    env.fetch.fetch_models()
    assert [c["name"] for c in env.model_calls] == [
        "dots-mocr-Q8_0.gguf",
        "dots-mocr-mmproj-bf16.gguf",
    ]
    assert {c["repo"] for c in env.model_calls} == {"cmdaltctr/omrs-ocr-gguf-converted"}
    assert {c["revision"] for c in env.model_calls} == {"a" * 40}
    assert {c["token"] for c in env.model_calls} == {"hf_test_token"}
    folder = env.paths.models_dir()
    assert (folder / "dots-mocr-Q8_0.gguf").read_bytes() == MODEL_BYTES
    assert (folder / "dots-mocr-mmproj-bf16.gguf").read_bytes() == PROJECTOR_BYTES
    assert [p for p in _leftovers(folder) if "tmp" in p or "download" in p] == []


def test_a_hash_mismatch_names_the_file_and_leaves_no_partial_file(env: Env) -> None:
    """A wrong download stops with the file name; nothing partial stays."""
    env.model_payload["dots-mocr-mmproj-bf16.gguf"] = b"tampered"
    with pytest.raises(env.fetch.FetchError) as excinfo:
        env.fetch.fetch_models()
    assert "dots-mocr-mmproj-bf16.gguf" in str(excinfo.value)
    folder = env.paths.models_dir()
    assert not (folder / "dots-mocr-mmproj-bf16.gguf").exists()
    assert [p for p in _leftovers(folder) if p != "dots-mocr-Q8_0.gguf"] == []


def test_a_missing_token_names_the_login_command_and_the_variable(
    env: Env, monkeypatch: Any
) -> None:
    """Without a token the error names ``hf auth login`` and ``HF_TOKEN``; nothing downloads."""
    monkeypatch.setattr(env.fetch, "get_token", lambda: None)
    with pytest.raises(env.fetch.FetchError) as excinfo:
        env.fetch.fetch_models()
    message = str(excinfo.value)
    assert "hf auth login" in message and "HF_TOKEN" in message
    assert env.model_calls == []


def test_an_unpinned_revision_refuses_to_download(env: Env, monkeypatch: Any) -> None:
    """While the revision is the placeholder, the fetch step stops before any download."""
    monkeypatch.setattr(env.pins, "MODEL_REVISION", env.pins.MODEL_REVISION_PLACEHOLDER)
    with pytest.raises(env.fetch.FetchError) as excinfo:
        env.fetch.fetch_models()
    assert "MODEL_REVISION" in str(excinfo.value)
    assert env.model_calls == []


def test_good_files_are_not_downloaded_again(env: Env) -> None:
    """A second run finds both files in place and downloads nothing."""
    env.fetch.fetch_models()
    env.model_calls.clear()
    env.fetch.fetch_models()
    assert env.model_calls == []


def test_a_changed_file_in_place_is_replaced(env: Env) -> None:
    """A file whose hash no longer matches is downloaded again."""
    env.fetch.fetch_models()
    target = env.paths.models_dir() / "dots-mocr-Q8_0.gguf"
    target.write_bytes(b"corrupt")
    env.model_calls.clear()
    env.fetch.fetch_models()
    assert [c["name"] for c in env.model_calls] == ["dots-mocr-Q8_0.gguf"]
    assert target.read_bytes() == MODEL_BYTES


def test_a_download_error_from_a_private_repository_names_the_login(
    env: Env, monkeypatch: Any
) -> None:
    """A failed download names the file and the token hint."""

    def refuse(*_args: Any) -> Path:
        raise RuntimeError("401 Client Error: Repository Not Found")

    monkeypatch.setattr(env.fetch, "download_model_file", refuse)
    with pytest.raises(env.fetch.FetchError) as excinfo:
        env.fetch.fetch_models()
    message = str(excinfo.value)
    assert "dots-mocr-Q8_0.gguf" in message and "HF_TOKEN" in message


# ── llama.cpp: a pinned archive, a hash check, an unpack ───────────────────


def test_archive_unpacks_into_the_engine_cache(env: Env) -> None:
    """The archive's single top folder is stripped; links and the execute bit stay."""
    env.fetch.fetch_llama()
    folder = env.paths.llama_dir()
    server = folder / "llama-server"
    assert server.read_bytes() == SERVER_SCRIPT
    assert os.access(server, os.X_OK)
    assert (folder / "libllama.dylib").is_symlink()
    assert (folder / "libllama.0.dylib").read_bytes() == b"lib"
    assert env.url_calls == [
        "https://github.com/ggml-org/llama.cpp/releases/download/b11941/llama-b11941-bin-test.tar.gz"
    ]
    assert [p for p in _leftovers(env.paths.cache_dir()) if "tmp" in p or ".tar" in p] == []


def test_an_archive_hash_mismatch_names_the_archive_and_leaves_nothing(
    env: Env, monkeypatch: Any
) -> None:
    """A wrong archive stops with its name; no partial file and no unpacked folder."""
    changed = env.pins.LlamaArchive("llama-b11941-bin-test.tar.gz", "0" * 64)
    monkeypatch.setattr(env.pins, "llama_archive", lambda *_a, **_k: changed)
    with pytest.raises(env.fetch.FetchError) as excinfo:
        env.fetch.fetch_llama()
    assert "llama-b11941-bin-test.tar.gz" in str(excinfo.value)
    assert not env.paths.llama_dir().exists()
    assert [p for p in _leftovers(env.paths.cache_dir()) if "tar" in p or "tmp" in p] == []


def test_an_unpacked_release_is_not_downloaded_again(env: Env) -> None:
    """A second run finds the marked release and downloads nothing."""
    env.fetch.fetch_llama()
    env.url_calls.clear()
    env.fetch.fetch_llama()
    assert env.url_calls == []


def test_a_platform_without_a_pin_is_refused(env: Env, monkeypatch: Any) -> None:
    """macOS x86-64 and Windows have no pinned archive."""
    monkeypatch.setattr(env.pins, "llama_archive", lambda *_a, **_k: None)
    with pytest.raises(env.fetch.FetchError) as excinfo:
        env.fetch.fetch_llama()
    assert "platform" in str(excinfo.value)


@pytest.fixture
def real_pins(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Load the pins module with nothing replaced."""
    with engine_modules(monkeypatch) as load:
        yield load("pins")


def test_the_pinned_archives_are_the_recorded_release_values(real_pins: ModuleType) -> None:
    """The real pins match the values recorded in task 1.2."""
    assert real_pins.LLAMA_BUILD == 11941
    assert real_pins.MACOS_ARM64.sha256 == (
        "fb5c491b35c75731019caa85d704fb839532c15dbb9bd3f6b3f75a667e7ac49a"
    )
    assert real_pins.UBUNTU_X64.sha256 == (
        "e8a1ee13aa19c6c78f5651457758160da27410301b179d6ef3505c81c8ea31f1"
    )
    assert real_pins.MACOS_ARM64.url == (
        "https://github.com/ggml-org/llama.cpp/releases/download/b11941/"
        "llama-b11941-bin-macos-arm64.tar.gz"
    )


def test_platform_lookup(real_pins: ModuleType) -> None:
    """macOS arm64 and Linux x86-64 have pins; other platforms have none."""
    assert real_pins.llama_archive("darwin", "arm64") is real_pins.MACOS_ARM64
    assert real_pins.llama_archive("linux", "x86_64") is real_pins.UBUNTU_X64
    assert real_pins.llama_archive("darwin", "x86_64") is None
    assert real_pins.llama_archive("win32", "AMD64") is None


def test_the_declared_program_exists_after_the_fetch_step_unpacks_the_archive(env: Env) -> None:
    """The host's ``program`` path in the manifest is the file the fetch step leaves."""
    from omrs.integrations.ocr_worker.manifest import declared_runtime

    env.fetch.fetch_llama()
    runtime = declared_runtime(ENGINE_DIR, env.paths.cache_dir())
    assert runtime is not None
    assert runtime.program.is_file()
    assert os.access(runtime.program, os.X_OK)
