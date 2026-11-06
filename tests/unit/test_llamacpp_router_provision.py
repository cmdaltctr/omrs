"""Provisioning of the pinned llama.cpp build (change one-llamacpp-router, task 6.2, design D12).

Spec requirements: "OMRS provisions a pinned llama.cpp build on request" and
"A provisioned build is checked before use". A local archive server serves
small fake archives; no test uses the network or a real ``llama-server``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from tests.unit.test_llamacpp_router_provision_support import (
    CUDA_DEVICE_LINE,
    LOADER_MESSAGE,
    TOP_FOLDER,
    ArchiveServer,
    _archive_server,  # noqa: F401 - fixture "archive_server"
    data_folder,
    server_script,
)

from omrs.integrations.llamacpp_runtime import pins, process, provision
from omrs.integrations.llamacpp_runtime.router_spec import router_spec


def _install(flavour: str | None = None) -> provision.ProvisionedBuild:
    return provision.install_pinned_build(flavour)


def _refusal(flavour: str | None = None) -> provision.ProvisionError:
    with pytest.raises(provision.ProvisionError) as caught:
        _install(flavour)
    return caught.value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _folders(tmp_path: Path) -> list[str]:
    """Return the installed flavour folders, not the record file."""
    return sorted(p.name for p in data_folder(tmp_path).iterdir() if p.is_dir())


def _nothing_left(tmp_path: Path) -> None:
    """Assert the data folder holds no installed build and no temporary file."""
    folder = data_folder(tmp_path)
    assert not folder.exists() or list(folder.iterdir()) == []


# ── Placing a build ──────────────────────────────────────────────────────


def test_cpu_install_places_the_server_in_its_own_folder(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")

    result = _install("cpu")

    expected = data_folder(tmp_path) / "b11941-cpu" / "llama-server"
    assert result.path == expected
    assert (result.flavour, result.build) == ("cpu", 11941)
    assert os.access(expected, os.X_OK)
    # The archive's own top folder is stripped; the other files sit beside the server.
    assert not (expected.parent / TOP_FOLDER).exists()
    assert (expected.parent / "libfake.so").is_file()
    assert (expected.parent / "libfake.so.0").is_symlink()
    assert _folders(tmp_path) == ["b11941-cpu"]


def test_hash_mismatch_is_file_changed_and_places_nothing(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu", tamper=True)

    refusal = _refusal("cpu")

    assert refusal.reason == "file-changed"
    assert "llama-b11941-cpu.tar.gz" in str(refusal)
    _nothing_left(tmp_path)


def test_unpinned_platform_is_not_supported(archive_server: ArchiveServer, tmp_path: Path) -> None:
    provision_host = ("darwin", "x86_64")
    archive_server.publish("cpu")
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: provision_host)

    refusal = _refusal("cpu")

    assert refusal.reason == "not-supported"
    assert archive_server.requests == []
    _nothing_left(tmp_path)


def test_no_default_flavour_on_an_unpinned_host(archive_server: ArchiveServer) -> None:
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: ("darwin", "x86_64"))

    assert _refusal(None).reason == "not-supported"


def test_download_failure_names_the_archive_and_places_nothing(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    (archive_server.root / "rel" / "llama-b11941-cpu.tar.gz").unlink()

    refusal = _refusal("cpu")

    assert refusal.reason == "download-failed"
    assert "llama-b11941-cpu.tar.gz" in str(refusal)
    _nothing_left(tmp_path)


def test_an_archive_member_that_escapes_the_folder_is_refused(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu", unsafe=True)

    refusal = _refusal("cpu")

    assert refusal.reason == "download-failed"
    assert not (tmp_path / "escape.txt").exists()
    assert not list(tmp_path.rglob("escape.txt"))
    _nothing_left(tmp_path)


# ── The version check ────────────────────────────────────────────────────


@pytest.mark.parametrize("build", [11510, 11960])
def test_a_wrong_build_from_version_is_binary_check_failed(
    archive_server: ArchiveServer, tmp_path: Path, build: int
) -> None:
    archive_server.publish("cpu", build=build)

    refusal = _refusal("cpu")

    assert refusal.reason == "binary-check-failed"
    assert str(build) in str(refusal)
    _nothing_left(tmp_path)


def test_a_loader_failure_shows_the_loader_message_and_places_nothing(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu", loader_failure=True)

    refusal = _refusal("cpu")

    assert refusal.reason == "binary-check-failed"
    assert LOADER_MESSAGE in str(refusal)
    _nothing_left(tmp_path)


# ── CUDA ─────────────────────────────────────────────────────────────────


def test_cuda_install_puts_the_runtime_files_beside_the_server(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)

    result = _install("cuda")

    folder = data_folder(tmp_path) / "b11941-cuda"
    assert result.path == folder / "llama-server"
    assert (folder / "libcudart.so.12").read_text() == "cudart"
    assert (folder / "libcublas.so.12").read_text() == "cublas"
    assert not (folder / "cudart-llama-b11941-bin-ubuntu-cuda-12.8-x64").exists()
    assert sorted(path.rsplit("/", 1)[-1] for path in archive_server.requests) == [
        "cudart-llama-b11941-cuda.tar.gz",
        "llama-b11941-cuda.tar.gz",
    ]


@pytest.mark.parametrize(
    "listing",
    [None, "  Vulkan0: pretend GPU for CUDA"],
    ids=["no-device", "other-backend-mentions-cuda"],
)
def test_cuda_without_a_cuda_device_line_is_cuda_device_missing(
    archive_server: ArchiveServer, tmp_path: Path, listing: str | None
) -> None:
    archive_server.publish("cuda", devices=listing)

    refusal = _refusal("cuda")

    assert refusal.reason == "cuda-device-missing"
    _nothing_left(tmp_path)


def test_the_cpu_flavour_needs_no_device_line(archive_server: ArchiveServer) -> None:
    archive_server.publish("cpu", devices=None)

    assert _install("cpu").flavour == "cpu"


def test_flavours_are_kept_apart(archive_server: ArchiveServer, tmp_path: Path) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)
    cpu = _install("cpu").path
    before = (_digest(cpu), cpu.stat().st_mtime_ns)

    cuda = _install("cuda").path

    assert cuda.parent.name == "b11941-cuda" and cpu.parent.name == "b11941-cpu"
    assert (_digest(cpu), cpu.stat().st_mtime_ns) == before
    assert cuda.read_text() != cpu.read_text()  # CUDA script lists a device


def test_a_failed_cuda_install_leaves_the_cpu_flavour_alone(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=None)
    cpu = _install("cpu").path

    assert _refusal("cuda").reason == "cuda-device-missing"

    assert cpu.is_file()
    assert _folders(tmp_path) == ["b11941-cpu"]


# ── Flavour detection ────────────────────────────────────────────────────


def test_linux_with_the_nvidia_marker_defaults_to_cuda(archive_server: ArchiveServer) -> None:
    (archive_server.root / "nvidia-version").write_text("NVRM version\n")

    assert provision.detect_flavour() == "cuda"


def test_linux_without_the_nvidia_marker_defaults_to_cpu(archive_server: ArchiveServer) -> None:
    assert provision.detect_flavour() == "cpu"


def test_macos_arm64_is_metal(archive_server: ArchiveServer) -> None:
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: ("darwin", "arm64"))

    assert provision.detect_flavour() == "metal"


def test_an_unpinned_host_has_no_default_flavour(archive_server: ArchiveServer) -> None:
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: ("darwin", "x86_64"))

    with pytest.raises(pins.NotSupported):
        provision.detect_flavour()


def test_install_without_a_flavour_uses_the_detected_one(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)
    (archive_server.root / "nvidia-version").write_text("NVRM version\n")

    assert _install(None).flavour == "cuda"
    assert (data_folder(tmp_path) / "b11941-cuda").is_dir()


def test_a_named_flavour_beats_the_detected_one(archive_server: ArchiveServer) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)
    (archive_server.root / "nvidia-version").write_text("NVRM version\n")

    assert _install("cpu").flavour == "cpu"


def test_macos_arm64_installs_metal(archive_server: ArchiveServer, tmp_path: Path) -> None:
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: ("darwin", "arm64"))
    archive_server.publish("metal", system="darwin", machine="arm64")

    result = _install(None)

    assert result.flavour == "metal"
    assert result.path == data_folder(tmp_path) / "b11941-metal" / "llama-server"


# ── Data folder and reuse ────────────────────────────────────────────────


def test_data_folder_follows_xdg_data_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert provision.llamacpp_data_folder() == tmp_path / "xdg" / "omrs" / "llamacpp"


def test_data_folder_falls_back_to_the_home_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert provision.llamacpp_data_folder() == (
        tmp_path / "home" / ".local" / "share" / "omrs" / "llamacpp"
    )


def test_a_second_install_of_a_good_build_downloads_nothing(
    archive_server: ArchiveServer,
) -> None:
    archive_server.publish("cpu")
    first = _install("cpu")
    archive_server.requests.clear()

    second = _install("cpu")

    assert second == first
    assert archive_server.requests == []


def test_a_broken_existing_build_is_replaced(archive_server: ArchiveServer, tmp_path: Path) -> None:
    archive_server.publish("cpu")
    result = _install("cpu")
    result.path.write_text(server_script(loader_failure=True))
    archive_server.requests.clear()

    again = _install("cpu")

    assert again.path == result.path
    assert archive_server.requests != []
    assert "loading shared libraries" not in again.path.read_text()


def test_a_broken_existing_build_is_gone_when_the_new_one_also_fails(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    result = _install("cpu")
    result.path.write_text(server_script(loader_failure=True))
    archive_server.publish("cpu", tamper=True)

    assert _refusal("cpu").reason == "file-changed"

    assert _folders(tmp_path) == []


# ── Resolving the program ────────────────────────────────────────────────


def test_blank_binary_resolves_the_provisioned_one(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    _install("cpu")

    for blank in ("", "   "):
        assert provision.resolve_server_binary(blank) == str(
            data_folder(tmp_path) / "b11941-cpu" / "llama-server"
        )


def test_blank_binary_follows_the_detected_flavour(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)
    _install("cpu")
    _install("cuda")
    (archive_server.root / "nvidia-version").write_text("NVRM version\n")

    assert provision.resolve_server_binary("") == str(
        data_folder(tmp_path) / "b11941-cuda" / "llama-server"
    )


def test_blank_binary_with_nothing_provisioned_stays_blank(archive_server: ArchiveServer) -> None:
    assert provision.resolve_server_binary("") == ""


def test_blank_binary_on_an_unpinned_host_stays_blank(archive_server: ArchiveServer) -> None:
    archive_server.monkeypatch.setattr(provision, "host_platform", lambda: ("darwin", "x86_64"))

    assert provision.resolve_server_binary("") == ""


def test_a_user_path_is_kept_as_given(archive_server: ArchiveServer, tmp_path: Path) -> None:
    archive_server.publish("cpu")
    _install("cpu")
    mine = "/opt/homebrew/bin/llama-server"

    assert provision.resolve_server_binary(mine) == mine


def test_a_user_path_below_the_pinned_build_is_wrong_build(
    archive_server: ArchiveServer, tmp_path: Path
) -> None:
    old = tmp_path / "mine" / "llama-server"
    old.parent.mkdir()
    old.write_text(server_script(build=11510))
    old.chmod(0o755)
    resolved = provision.resolve_server_binary(str(old))
    spec = router_spec(
        binary=resolved, root=tmp_path / "state", port=8080, models_max=4, memory_margin_mib=8192
    )
    folder = tmp_path / "state" / "runtimes" / "router"
    folder.mkdir(parents=True)
    launched: list[tuple[int, int]] = []

    with pytest.raises(process.StartRefused) as caught:
        process.start_server(
            spec, folder, os.environ, lambda pid, port: launched.append((pid, port))
        )

    assert caught.value.reason == "wrong-build"
    assert launched == []
