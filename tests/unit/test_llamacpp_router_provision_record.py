"""The record of the last installed flavour (change one-llamacpp-router, task 6.2).

A host installed with ``--flavour cpu`` on an NVIDIA machine must resolve a
blank ``llamacpp_server_binary`` to the CPU build it installed, not to the CUDA
folder the detection would name. The last install wins.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.test_llamacpp_router_provision_support import (
    CUDA_DEVICE_LINE,
    ArchiveServer,
    _archive_server,  # noqa: F401 - fixture "archive_server"
    data_folder,
)

from omrs.integrations.llamacpp_runtime import provision


def _binary(tmp_path: Path, flavour: str) -> str:
    return str(data_folder(tmp_path) / f"b11941-{flavour}" / "llama-server")


def _nvidia(server: ArchiveServer) -> None:
    (server.root / "nvidia-version").write_text("NVRM version\n")


def test_cpu_installed_on_an_nvidia_host_resolves_to_the_cpu_build(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    _nvidia(archive_server)
    provision.install_pinned_build("cpu")

    assert provision.resolve_server_binary("") == _binary(tmp_path, "cpu")


def test_the_record_holds_the_build_and_flavour_and_leaves_no_temporary_file(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    provision.install_pinned_build("cpu")

    record = data_folder(tmp_path) / "installed.json"
    assert json.loads(record.read_text()) == {"build": 11941, "flavour": "cpu"}
    assert sorted(p.name for p in data_folder(tmp_path).iterdir()) == [
        "b11941-cpu",
        "installed.json",
    ]


def test_the_last_install_wins(archive_server: ArchiveServer, tmp_path: Path) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)

    provision.install_pinned_build("cpu")
    provision.install_pinned_build("cuda")
    assert provision.resolve_server_binary("") == _binary(tmp_path, "cuda")

    provision.install_pinned_build("cpu")  # reused, not downloaded
    assert provision.resolve_server_binary("") == _binary(tmp_path, "cpu")
    assert (data_folder(tmp_path) / "b11941-cuda" / "llama-server").is_file()


def test_a_refused_install_keeps_the_record(archive_server: ArchiveServer, tmp_path: Path) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=None)
    provision.install_pinned_build("cpu")

    try:
        provision.install_pinned_build("cuda")
    except provision.ProvisionError:
        pass

    assert provision.resolve_server_binary("") == _binary(tmp_path, "cpu")


def test_a_record_whose_folder_is_gone_falls_back_to_the_detected_flavour(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)
    provision.install_pinned_build("cpu")
    provision.install_pinned_build("cuda")
    (data_folder(tmp_path) / "b11941-cuda" / "llama-server").unlink()

    assert provision.resolve_server_binary("") == _binary(tmp_path, "cpu")


def test_a_broken_or_foreign_record_is_ignored(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)
    provision.install_pinned_build("cuda")
    provision.install_pinned_build("cpu")
    record = data_folder(tmp_path) / "installed.json"

    for text in ("not json", '{"build": 11510, "flavour": "cuda"}', '{"flavour": 3}', "[]"):
        record.write_text(text)
        assert provision.resolve_server_binary("") == _binary(tmp_path, "cpu"), text


def test_a_set_path_ignores_the_record(archive_server: ArchiveServer) -> None:
    archive_server.publish("cpu")
    provision.install_pinned_build("cpu")

    assert provision.resolve_server_binary("/opt/mine/llama-server") == "/opt/mine/llama-server"
