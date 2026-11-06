"""The pinned llama.cpp build OMRS provisions (change one-llamacpp-router, design D12).

Pure data and one lookup. Nothing here reads the network or the disk. The
download, the hash check and the unpacking belong to the provisioning job.

The OCR engine ``ocr-workers/engines/dots-mocr`` pins the same build in its
own ``pins.py``. This package cannot import ``ocr-workers``, so the values
are written twice and ``tests/unit/test_llamacpp_router_pins.py`` compares
them.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Literal

#: The only llama.cpp build OMRS provisions (ADR-110, ADR-113).
LLAMA_BUILD = 11941
LLAMA_TAG = f"b{LLAMA_BUILD}"
LLAMA_RELEASE_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"

#: ``metal`` is the one macOS arm64 build. ``cpu`` and ``cuda`` are Linux x86-64.
Flavour = Literal["metal", "cpu", "cuda"]


class NotSupported(ValueError):
    """No archive is pinned for the platform and flavour asked for."""

    #: The refusal reason the provisioning job reports.
    reason = "not-supported"


@dataclass(frozen=True)
class PinnedArchive:
    """One release archive: its file name and its SHA-256."""

    name: str
    sha256: str

    @property
    def url(self) -> str:
        """Return the download URL of the archive."""
        return f"{LLAMA_RELEASE_URL}/{self.name}"


@dataclass(frozen=True)
class PinnedBuild:
    """The archives of one platform flavour.

    Attributes:
        flavour: The flavour these archives belong to.
        archives: The server archive first, then any runtime archive. The
            runtime files go beside ``llama-server`` (design D12).
    """

    flavour: Flavour
    archives: tuple[PinnedArchive, ...]

    @property
    def folder_name(self) -> str:
        """Return the folder this flavour unpacks into, for example ``b11941-cpu``."""
        return f"{LLAMA_TAG}-{self.flavour}"


_MACOS_ARM64 = PinnedArchive(
    f"llama-{LLAMA_TAG}-bin-macos-arm64.tar.gz",
    "fb5c491b35c75731019caa85d704fb839532c15dbb9bd3f6b3f75a667e7ac49a",
)
_UBUNTU_X64 = PinnedArchive(
    f"llama-{LLAMA_TAG}-bin-ubuntu-x64.tar.gz",
    "e8a1ee13aa19c6c78f5651457758160da27410301b179d6ef3505c81c8ea31f1",
)
_UBUNTU_CUDA_X64 = PinnedArchive(
    f"llama-{LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz",
    "9945330f20a35b9a30fbac43f99f5b7f88ae7dd32dc2e5089af5c75310d3acf1",
)
_UBUNTU_CUDART_X64 = PinnedArchive(
    f"cudart-llama-{LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz",
    "3011ef1b30e73a3059c5a4d3d44446562155aff49035efc49e7e2f1c370524f8",
)

_BUILDS: dict[tuple[str, str, str], PinnedBuild] = {
    ("darwin", "arm64", "metal"): PinnedBuild("metal", (_MACOS_ARM64,)),
    ("linux", "x86_64", "cpu"): PinnedBuild("cpu", (_UBUNTU_X64,)),
    ("linux", "x86_64", "cuda"): PinnedBuild("cuda", (_UBUNTU_CUDA_X64, _UBUNTU_CUDART_X64)),
}

#: Machine names that mean the same architecture.
_MACHINE_ALIASES = {"aarch64": "arm64", "amd64": "x86_64"}


def pinned_build(
    flavour: str, system: str | None = None, machine: str | None = None
) -> PinnedBuild:
    """Return the pinned archives for a platform flavour.

    Args:
        flavour: ``metal`` (macOS arm64), or ``cpu`` or ``cuda`` (Linux x86-64).
        system: ``sys.platform`` value; defaults to the running platform.
        machine: ``platform.machine()`` value; defaults to the running machine.

    Returns:
        The archives to download, check and unpack.

    Raises:
        NotSupported: No archive is pinned for the platform and flavour, for
            example macOS x86-64, Windows or Linux arm64. The reason is
            ``not-supported``.
    """
    system = sys.platform if system is None else system
    system = "linux" if system.startswith("linux") else system
    machine = (platform.machine() if machine is None else machine).lower()
    machine = _MACHINE_ALIASES.get(machine, machine)
    try:
        return _BUILDS[(system, machine, flavour)]
    except KeyError:
        raise NotSupported(
            f"no llama.cpp {LLAMA_TAG} archive is pinned for {system} {machine} ({flavour})"
        ) from None
