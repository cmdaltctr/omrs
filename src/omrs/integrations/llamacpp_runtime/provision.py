"""Provision the pinned llama.cpp build on request (change one-llamacpp-router, design D12).

``install_pinned_build`` downloads each archive of the pinned build, checks
its SHA-256, unpacks the server archive into ``<data>/b11941-<flavour>/`` with
the ``cudart`` files beside ``llama-server``, runs ``--version`` (and
``--list-devices`` for CUDA) and only then places the folder. A failed step
leaves no binary in place. Nothing here starts a server.

The data folder is ``$XDG_DATA_HOME/omrs/llamacpp``, else
``~/.local/share/omrs/llamacpp``. Each flavour has its own folder, because
every archive unpacks to a ``llama-b11941/`` folder of the same name.

``resolve_server_binary`` maps a blank ``llamacpp_server_binary`` to the
provisioned binary of the detected flavour.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import pins
from .hashes import hash_file
from .pins import Flavour, PinnedArchive, PinnedBuild
from .provision_checks import ProvisionError, check_cuda_device, check_version

__all__ = [
    "NVIDIA_VERSION_FILE",
    "ProvisionError",
    "ProvisionedBuild",
    "detect_flavour",
    "host_platform",
    "install_pinned_build",
    "llamacpp_data_folder",
    "resolve_server_binary",
]

#: Present on a Linux host that has the NVIDIA driver loaded.
NVIDIA_VERSION_FILE = Path("/proc/driver/nvidia/version")
#: The program inside each unpacked flavour folder.
SERVER_NAME = "llama-server"
#: Beside the flavour folders: the build and flavour of the last install.
RECORD_FILE = "installed.json"

_CHUNK = 1024 * 1024
_DOWNLOAD_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class ProvisionedBuild:
    """A placed and checked build.

    Attributes:
        path: Absolute path of ``llama-server``.
        flavour: ``metal``, ``cpu`` or ``cuda``.
        build: The build number ``--version`` reported.
    """

    path: Path
    flavour: Flavour
    build: int


def host_platform() -> tuple[str, str]:
    """Return ``(sys.platform, machine)`` of this host. Tests replace this."""
    return sys.platform, platform.machine()


def llamacpp_data_folder() -> Path:
    """Return ``$XDG_DATA_HOME/omrs/llamacpp``, else ``~/.local/share/omrs/llamacpp``."""
    base = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "omrs" / "llamacpp"


def detect_flavour() -> Flavour:
    """Return the flavour this host uses when none is named.

    macOS arm64 is ``metal`` (one build, no choice). Linux x86-64 is ``cuda``
    when ``/proc/driver/nvidia/version`` exists, else ``cpu``.

    Raises:
        pins.NotSupported: No build is pinned for this platform.
    """
    system, machine = host_platform()
    for probe in ("metal", "cpu"):
        try:
            pins.pinned_build(probe, system, machine)
        except pins.NotSupported:
            continue
        if probe == "metal":
            return "metal"
        return "cuda" if NVIDIA_VERSION_FILE.exists() else "cpu"
    raise pins.NotSupported(f"no llama.cpp {pins.LLAMA_TAG} build is pinned for {system} {machine}")


def resolve_server_binary(configured: str) -> str:
    """Return the program to run for ``llamacpp_server_binary``.

    A set path is returned as given: the program rule and the build floor
    judge it later. A blank value gives the binary of the flavour installed
    last (``installed.json``), else of the detected flavour. It gives blank when
    that binary is missing or the platform is not pinned.

    Args:
        configured: The ``llamacpp_server_binary`` setting.
    """
    if configured.strip():
        return configured
    root = llamacpp_data_folder()
    recorded = _recorded_binary(root)
    if recorded is not None:
        return str(recorded)
    try:
        folder = pins.pinned_build(detect_flavour(), *host_platform()).folder_name
    except pins.NotSupported:
        return ""
    binary = root / folder / SERVER_NAME
    return str(binary) if binary.is_file() else ""


def _recorded_binary(root: Path) -> Path | None:
    """Return the binary of the flavour recorded by the last install, if it is still there."""
    try:
        record = json.loads((root / RECORD_FILE).read_text(encoding="utf-8"))
        if record["build"] != pins.LLAMA_BUILD:
            return None
        folder = pins.pinned_build(record["flavour"], *host_platform()).folder_name
    except (OSError, ValueError, KeyError, TypeError, pins.NotSupported):
        return None
    binary = root / folder / SERVER_NAME
    return binary if binary.is_file() else None


def _write_record(root: Path, flavour: str, build: int) -> None:
    """Record the flavour installed last, with a temporary file and a rename."""
    temporary = root / f"{RECORD_FILE}.tmp"
    temporary.write_text(json.dumps({"build": build, "flavour": flavour}), encoding="utf-8")
    os.replace(temporary, root / RECORD_FILE)


def install_pinned_build(
    flavour: str | None = None, report: Callable[[str], None] | None = None
) -> ProvisionedBuild:
    """Download, check and place the pinned build for *flavour*.

    A build already placed that passes its checks is returned with no download.

    Args:
        flavour: ``cpu`` or ``cuda`` on Linux, ``metal`` on macOS arm64; ``None``
            takes :func:`detect_flavour`.
        report: Called with a short progress line before each step.

    Returns:
        The placed build.

    Raises:
        ProvisionError: With ``not-supported``, ``download-failed``,
            ``file-changed``, ``binary-check-failed`` or ``cuda-device-missing``.
            No binary is placed after a refusal.
    """
    say = report or (lambda _line: None)
    try:
        chosen = flavour or detect_flavour()
        pinned = pins.pinned_build(chosen, *host_platform())
    except pins.NotSupported as exc:
        raise ProvisionError("not-supported", str(exc)) from exc
    root = llamacpp_data_folder()
    target = root / pinned.folder_name
    existing = _checked_existing(target, pinned)
    if existing is not None:
        say(f"{pinned.folder_name} is already installed and passes its checks")
        _write_record(root, existing.flavour, existing.build)
        return existing
    root.mkdir(parents=True, exist_ok=True)
    work = root / f".install-{pinned.folder_name}.tmp"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        stage = _stage(pinned, work, say)
        say(f"Checking {SERVER_NAME}")
        build = _verify(stage / SERVER_NAME, pinned.flavour)
        os.replace(stage, target)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    _write_record(root, pinned.flavour, build)
    return ProvisionedBuild(target / SERVER_NAME, pinned.flavour, build)


def _verify(binary: Path, flavour: str) -> int:
    """Run the checks of *flavour* on *binary*; return the build."""
    build = check_version(binary)
    if flavour == "cuda":
        check_cuda_device(binary)
    return build


def _checked_existing(target: Path, pinned: PinnedBuild) -> ProvisionedBuild | None:
    """Return the build in *target* when it passes its checks; remove a folder that fails."""
    binary = target / SERVER_NAME
    if not binary.is_file():
        shutil.rmtree(target, ignore_errors=True)
        return None
    try:
        return ProvisionedBuild(binary, pinned.flavour, _verify(binary, pinned.flavour))
    except ProvisionError:
        shutil.rmtree(target, ignore_errors=True)
        return None


def _stage(pinned: PinnedBuild, work: Path, say: Callable[[str], None]) -> Path:
    """Download, check and unpack every archive into one folder under *work*."""
    stage = work / "stage"
    for index, archive in enumerate(pinned.archives):
        part = work / f"{archive.name}.part"
        say(f"Downloading {archive.name}")
        _download(archive, part)
        say(f"Checking {archive.name}")
        _check_hash(archive, part)
        unpack = work / f"unpack-{index}"
        _unpack(archive, part, unpack)
        part.unlink()
        top = _single_top_folder(unpack)
        if index == 0:
            os.replace(top, stage)
            continue
        for item in top.iterdir():
            os.replace(item, stage / item.name)
    return stage


def _download(archive: PinnedArchive, destination: Path) -> None:
    """Stream the archive to *destination* (a temporary name)."""
    try:
        with (
            urllib.request.urlopen(  # noqa: S310 - pinned https URL
                archive.url, timeout=_DOWNLOAD_TIMEOUT_SECONDS
            ) as response,
            destination.open("wb") as handle,
        ):
            shutil.copyfileobj(response, handle, _CHUNK)
    except (OSError, ValueError) as exc:
        raise ProvisionError(
            "download-failed", f"download of {archive.name} failed: {type(exc).__name__}: {exc}"
        ) from exc


def _check_hash(archive: PinnedArchive, path: Path) -> None:
    """Refuse with ``file-changed`` unless *path* has the pinned SHA-256."""
    actual = hash_file(str(path))
    if actual != archive.sha256:
        raise ProvisionError(
            "file-changed",
            f"{archive.name} does not match its pinned SHA-256 "
            f"(expected {archive.sha256}, got {actual}); nothing was placed",
        )


def _unpack(archive: PinnedArchive, path: Path, destination: Path) -> None:
    """Unpack with the tar ``data`` filter, which refuses any path that leaves *destination*."""
    destination.mkdir()
    try:
        with tarfile.open(path, "r:gz") as tar:
            tar.extractall(destination, filter="data")
    except (tarfile.TarError, OSError) as exc:
        raise ProvisionError(
            "download-failed", f"unpacking {archive.name} failed: {type(exc).__name__}: {exc}"
        ) from exc


def _single_top_folder(folder: Path) -> Path:
    """Return the one folder inside *folder*, or *folder* when there is not exactly one."""
    entries = list(folder.iterdir())
    if len(entries) == 1 and entries[0].is_dir() and not entries[0].is_symlink():
        return entries[0]
    return folder
