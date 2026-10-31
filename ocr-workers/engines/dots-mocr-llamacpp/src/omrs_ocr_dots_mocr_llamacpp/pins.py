"""Every pinned item of the engine: model files, projector and llama.cpp (design D3, D4, D5).

Nothing here is read from the network. A change to any value is a change
of the engine's pipeline revision and re-indexes documents (design D7).
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass

#: The private Hugging Face repository that holds our own conversion (D4).
MODEL_REPO = "cmdaltctr/omrs-ocr-gguf-converted"

#: The commit of :data:`MODEL_REPO` to download. It is a placeholder until
#: the operator uploads the files (task 1.1) and writes the commit here.
#: The fetch step refuses to run while this value is the placeholder.
MODEL_REVISION_PLACEHOLDER = "pending-upload-task-1.1"
MODEL_REVISION = MODEL_REVISION_PLACEHOLDER

#: The upstream model the conversion comes from (recorded in LICENCE-NOTES.md).
SOURCE_MODEL = "rednote-hilab/dots.mocr"
SOURCE_REVISION = "e539fbb52280393adc081b289ec597430a0f9031"

#: The quantisation and the converter, as they appear in the pipeline revision.
QUANT = "q8_0"


@dataclass(frozen=True)
class PinnedFile:
    """A downloaded file: its name in the repository and its SHA-256."""

    name: str
    sha256: str


MODEL_FILE = PinnedFile(
    "dots-mocr-Q8_0.gguf",
    "6017b1844a77837010649939fe2e934af17728fc89243f88b10bde4afa04d6be",
)
PROJECTOR_FILE = PinnedFile(
    "dots-mocr-mmproj-bf16.gguf",
    "63f415f961da981d0ee101cfdbf7a7bcc81ace4c4aa780a6e2823c0cd780761f",
)
MODEL_FILES = (MODEL_FILE, PROJECTOR_FILE)

#: The only llama.cpp build the engine accepts (D3).
LLAMA_BUILD = 11941
LLAMA_TAG = f"b{LLAMA_BUILD}"
LLAMA_RELEASE_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"


@dataclass(frozen=True)
class LlamaArchive:
    """A llama.cpp release archive for one platform."""

    name: str
    sha256: str

    @property
    def url(self) -> str:
        """Return the download URL of the archive."""
        return f"{LLAMA_RELEASE_URL}/{self.name}"


MACOS_ARM64 = LlamaArchive(
    f"llama-{LLAMA_TAG}-bin-macos-arm64.tar.gz",
    "fb5c491b35c75731019caa85d704fb839532c15dbb9bd3f6b3f75a667e7ac49a",
)
#: The CPU build. It runs untested (design Non-Goals).
UBUNTU_X64 = LlamaArchive(
    f"llama-{LLAMA_TAG}-bin-ubuntu-x64.tar.gz",
    "e8a1ee13aa19c6c78f5651457758160da27410301b179d6ef3505c81c8ea31f1",
)

#: The server flags of Experiment 41 arm D4 (D5). Port, model and projector
#: are added by :func:`omrs_ocr_dots_mocr_llamacpp.server.server_command`.
SERVER_FLAGS = (
    "--temp",
    "0",
    "-c",
    "24576",
    "-np",
    "1",
    "--image-min-tokens",
    "4",
    "--image-max-tokens",
    "14400",
)


def llama_archive(system: str | None = None, machine: str | None = None) -> LlamaArchive | None:
    """Return the pinned archive for a platform, or None when none is pinned.

    Args:
        system: ``sys.platform`` value; defaults to the running platform.
        machine: ``platform.machine()`` value; defaults to the running machine.

    Returns:
        The macOS arm64 or Linux x86-64 archive. macOS x86-64 and Windows
        are not pinned (design D3).
    """
    system = sys.platform if system is None else system
    machine = platform.machine().lower() if machine is None else machine.lower()
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return MACOS_ARM64
    if system.startswith("linux") and machine in ("x86_64", "amd64"):
        return UBUNTU_X64
    return None
