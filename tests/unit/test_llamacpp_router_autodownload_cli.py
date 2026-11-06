"""``omrs llamacpp install`` downloads missing listed models after the binary (task 6.2a).

Spec scenario "Headless install downloads too". The pinned build install and the
Hugging Face calls are faked at their modules; no network is used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL
from omrs.integrations import huggingface_models as hf
from omrs.integrations.llamacpp_runtime import provision
from omrs.transports.cli import app

REV = "d" * 40


@pytest.fixture
def calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    record: list[tuple[Any, ...]] = []
    monkeypatch.delenv("HF_TOKEN", raising=False)

    def install(flavour: Any, say: Any) -> Any:
        record.append(("binary", flavour))
        say("Downloading llama-b11941-bin-macos-arm64.tar.gz")
        return provision.ProvisionedBuild(
            path=tmp_path / "llama-server", flavour="metal", build=11941
        )

    def list_files(repo: str, *, revision: str | None = None, **_: Any) -> Any:
        name = repo.split("/")[1].removesuffix("-GGUF") + "-Q8_0.gguf"
        return hf.RepoFiles(repo, REV, False, ((name, 1000),))

    def download(
        repo: str, revision: str, files: Any, *, on_bytes: Any, cancel: Any, token: Any
    ) -> str:
        record.append(("model", repo, revision, tuple(files)))
        on_bytes(1000)
        path = tmp_path / files[0]
        path.write_bytes(b"GGUF")
        return str(path)

    monkeypatch.setattr(provision, "install_pinned_build", install)
    monkeypatch.setattr(hf, "list_repo_files", list_files)
    monkeypatch.setattr(hf, "download_files", download)
    return record


def test_install_downloads_each_missing_listed_model_after_the_binary(
    calls: list[tuple[Any, ...]],
) -> None:
    result = CliRunner().invoke(app, ["llamacpp", "install"])

    assert result.exit_code == 0, result.output
    assert calls == [
        ("binary", None),
        ("model", "Qwen/Qwen3-Embedding-4B-GGUF", REV, ("Qwen3-Embedding-4B-Q8_0.gguf",)),
        ("model", "Qwen/Qwen3-4B-GGUF", REV, ("Qwen3-4B-Q8_0.gguf",)),
    ]
    assert f"Downloading {EMBED_MODEL}" in result.output
    assert f"Downloading {CLASSIFY_MODEL}" in result.output


def test_an_external_router_downloads_no_model(
    calls: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLAMACPP_ROUTER_SERVER", "external")

    result = CliRunner().invoke(app, ["llamacpp", "install"])

    assert result.exit_code == 0, result.output
    assert calls == [("binary", None)]
