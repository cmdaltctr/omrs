"""The checks of a provisioned llama.cpp build (change one-llamacpp-router, design D12).

Each check runs the unpacked ``llama-server`` once and starts no server:

* ``--version`` must report the pinned build. A host that is too old for the
  build, or one that lacks ``libgomp1``, fails here with the loader's message.
* ``--list-devices`` must list a CUDA device for the CUDA flavour. The CUDA
  build exits 0 and lists no device when the driver is missing (spike 1.4),
  so the output is the only sign.

The program runs with the minimal child environment, like a managed server.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .pins import LLAMA_BUILD
from .process import _BUILD_IN_VERSION
from .rules import child_environment

#: Seconds a check may take before it counts as failed.
CHECK_TIMEOUT_SECONDS = 30.0
#: Longest piece of program output kept in a refusal message.
_MAX_OUTPUT_CHARS = 500


class ProvisionError(Exception):
    """A provisioning step was refused with one fixed reason.

    Attributes:
        reason: ``not-supported``, ``file-changed``, ``download-failed``,
            ``binary-check-failed`` or ``cuda-device-missing``.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _run(binary: Path, flag: str) -> str:
    """Run ``<binary> <flag>`` and return its output; refuse on any failure to answer."""
    try:
        run = subprocess.run(  # noqa: S603 - fixed argv, a file OMRS just unpacked
            [str(binary), flag],
            capture_output=True,
            text=True,
            env=child_environment(os.environ, "file"),
            timeout=CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProvisionError(
            "binary-check-failed", f"llama-server {flag} could not run: {exc}"
        ) from exc
    output = f"{run.stdout}\n{run.stderr}".strip()
    if run.returncode != 0:
        shown = output[:_MAX_OUTPUT_CHARS]
        raise ProvisionError(
            "binary-check-failed", f"llama-server {flag} failed (exit {run.returncode}): {shown}"
        )
    return output


def check_version(binary: Path) -> int:
    """Return the build ``--version`` reports; refuse unless it is the pinned build.

    Raises:
        ProvisionError: ``binary-check-failed``, with the loader's message when the
            program does not run, or the build that was found.
    """
    output = _run(binary, "--version")
    found = _BUILD_IN_VERSION.search(output)
    if found is None:
        raise ProvisionError(
            "binary-check-failed",
            f"llama-server --version printed no build number: {output[:_MAX_OUTPUT_CHARS]}",
        )
    build = int(found.group(1))
    if build != LLAMA_BUILD:
        raise ProvisionError(
            "binary-check-failed", f"llama-server reports build {build}, needs {LLAMA_BUILD}"
        )
    return build


def check_cuda_device(binary: Path) -> None:
    """Refuse unless ``--list-devices`` lists a line that starts with ``CUDA``.

    Raises:
        ProvisionError: ``cuda-device-missing``, or ``binary-check-failed`` when
            the program does not run.
    """
    output = _run(binary, "--list-devices")
    if not any(line.lstrip().startswith("CUDA") for line in output.splitlines()):
        raise ProvisionError(
            "cuda-device-missing",
            "llama-server --list-devices lists no CUDA device. Check the NVIDIA driver "
            "(nvidia-smi) or install the cpu flavour.",
        )
