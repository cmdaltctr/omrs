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


def _fail_listing(monkeypatch: pytest.MonkeyPatch, reasons: dict[str, str]) -> None:
    """Make ``list_repo_files`` raise the mapped reason for each named repo."""
    real = hf.list_repo_files

    def list_files(repo: str, **kwargs: Any) -> Any:
        if repo in reasons:
            raise hf.ModelHostError(reasons[repo])
        return real(repo, **kwargs)

    monkeypatch.setattr(hf, "list_repo_files", list_files)


def test_a_failed_model_does_not_stop_the_models_after_it(
    calls: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_listing(monkeypatch, {"Qwen/Qwen3-Embedding-4B-GGUF": "network"})

    result = CliRunner().invoke(app, ["llamacpp", "install"])

    assert result.exit_code == 1, result.output
    assert calls == [
        ("binary", None),
        ("model", "Qwen/Qwen3-4B-GGUF", REV, ("Qwen3-4B-Q8_0.gguf",)),
    ]
    assert f"{EMBED_MODEL}: network" in result.output
    assert "SHA-256" in result.output


def test_each_failure_prints_its_reason_and_the_exit_names_the_failed_models(
    calls: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_listing(
        monkeypatch,
        {"Qwen/Qwen3-Embedding-4B-GGUF": "gated", "Qwen/Qwen3-4B-GGUF": "not-found"},
    )

    result = CliRunner().invoke(app, ["llamacpp", "install"])

    assert result.exit_code == 1, result.output
    assert calls == [("binary", None)]
    assert f"{EMBED_MODEL}: gated" in result.output
    assert f"{CLASSIFY_MODEL}: not-found" in result.output
    closing = result.output.rstrip().splitlines()[-1]
    assert EMBED_MODEL in closing
    assert CLASSIFY_MODEL in closing


def test_a_repo_without_the_gguf_label_fails_and_the_next_model_still_downloads(
    calls: list[tuple[Any, ...]], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = hf.list_repo_files

    def list_files(repo: str, **kwargs: Any) -> Any:
        if repo == "Qwen/Qwen3-Embedding-4B-GGUF":
            return hf.RepoFiles(repo, REV, False, (("Qwen3-Embedding-4B-F16.gguf", 1000),))
        return real(repo, **kwargs)

    monkeypatch.setattr(hf, "list_repo_files", list_files)

    result = CliRunner().invoke(app, ["llamacpp", "install"])

    assert result.exit_code == 1, result.output
    assert [c[1] for c in calls[1:]] == ["Qwen/Qwen3-4B-GGUF"]
    assert "the repo holds no Q8_0 GGUF file" in result.output


def _plain_help(args: list[str]) -> str:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    return " ".join(result.output.split())


def test_the_group_and_install_help_say_install_also_downloads_the_models() -> None:
    for text in (
        _plain_help(["llamacpp", "--help"]),
        _plain_help(["llamacpp", "install", "--help"]),
    ):
        assert "managed" in text
        assert "Hugging Face cache" in text
        assert "has no file" in text
