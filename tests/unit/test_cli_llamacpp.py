"""``omrs llamacpp install`` (change one-llamacpp-router, task 6.2, design D12).

Every case runs against the local archive server of the provisioning tests,
in a temporary data folder. The command is headless: no prompt, no server
start, output on stderr only (gotcha #5).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit.test_llamacpp_router_provision_support import (
    CUDA_DEVICE_LINE,
    ArchiveServer,
    _archive_server,  # noqa: F401 - fixture "archive_server"
    data_folder,
)
from typer.testing import CliRunner

from omrs.integrations.llamacpp_runtime import process, provision
from omrs.transports.cli import app

runner = CliRunner()


def flat(text: str) -> str:
    """Collapse whitespace, so a wrapped terminal line still matches."""
    return " ".join(text.split())


@pytest.fixture(autouse=True)
def no_server_starts(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Fail the test if the command launches a server."""
    launched: list[object] = []

    def refuse(*args: object, **kwargs: object) -> None:
        launched.append(args)
        raise AssertionError("install must not start a server")

    monkeypatch.setattr(process, "launch", refuse)
    return launched


def _install(*args: str) -> object:
    return runner.invoke(app, ["llamacpp", "install", *args], input=None)


def test_install_reports_on_stderr_and_prints_nothing_to_stdout(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")

    result = _install("--flavour", "cpu")

    assert result.exit_code == 0, result.stderr
    assert result.stdout == ""
    text = flat(result.stderr)
    assert "b11941" in text and "cpu" in text
    assert str(data_folder(tmp_path)) in text.replace(" ", "")
    assert (data_folder(tmp_path) / "b11941-cpu" / "llama-server").is_file()


def test_install_without_a_flavour_uses_the_detected_one(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)
    (archive_server.root / "nvidia-version").write_text("NVRM version\n")

    result = _install()

    assert result.exit_code == 0, result.stderr
    assert (data_folder(tmp_path) / "b11941-cuda" / "llama-server").is_file()
    assert not (data_folder(tmp_path) / "b11941-cpu").exists()


def test_cuda_install_checks_the_runtime_archive_too(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)

    result = _install("--flavour", "cuda")

    assert result.exit_code == 0, result.stderr
    assert (data_folder(tmp_path) / "b11941-cuda" / "libcudart.so.12").is_file()


def test_a_refusal_exits_non_zero_with_the_reason(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu", tamper=True)

    result = _install("--flavour", "cpu")

    assert result.exit_code == 1
    assert "file-changed" in flat(result.stderr)
    assert result.stdout == ""
    assert not (data_folder(tmp_path) / "b11941-cpu").exists()


def test_cuda_without_a_device_exits_non_zero(archive_server: ArchiveServer) -> None:
    archive_server.publish("cuda", devices=None)

    result = _install("--flavour", "cuda")

    assert result.exit_code == 1
    assert "cuda-device-missing" in flat(result.stderr)


def test_an_unpinned_platform_exits_non_zero(archive_server: ArchiveServer) -> None:
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: ("darwin", "x86_64"))

    result = _install()

    assert result.exit_code == 1
    assert "not-supported" in flat(result.stderr)
    assert archive_server.requests == []


@pytest.mark.parametrize("value", ["metal", "gpu", ""])
def test_a_flavour_other_than_cpu_or_cuda_is_refused(
    archive_server: ArchiveServer, value: str
) -> None:
    archive_server.publish("cpu")

    result = _install("--flavour", value)

    assert result.exit_code == 1
    assert "cpu" in flat(result.stderr) and "cuda" in flat(result.stderr)
    assert archive_server.requests == []


def test_flavour_on_macos_is_refused_with_a_clear_message(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: ("darwin", "arm64"))
    archive_server.publish("metal", system="darwin", machine="arm64")

    result = _install("--flavour", "cpu")

    assert result.exit_code == 1
    text = flat(result.stderr)
    assert "macOS" in text and "--flavour" in text
    assert archive_server.requests == []
    assert not data_folder(tmp_path).exists()


def test_macos_without_a_flavour_installs_metal(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: ("darwin", "arm64"))
    archive_server.publish("metal", system="darwin", machine="arm64")

    result = _install()

    assert result.exit_code == 0, result.stderr
    assert (data_folder(tmp_path) / "b11941-metal" / "llama-server").is_file()
