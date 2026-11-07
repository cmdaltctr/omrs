"""GPU memory sampler for the Part B timing runner (change task 4.4, design D9).

On a CUDA run the model sits in GPU memory, so the server's resident memory is
not the useful number. This sampler reads ``nvidia-smi --query-compute-apps``
every 0.5 s, sums the used memory of the server PIDs (the router and its child
``llama-server`` processes) and keeps the peak. On a Metal or CPU run it records
no GPU value and never calls ``nvidia-smi``.

A CUDA run that cannot read the GPU memory stops with an error that names
``nvidia-smi`` (spec scenario "Peak memory on a CUDA machine"). No silent zero.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Collection

SAMPLE_INTERVAL_S = 0.5
NVIDIA_SMI_ARGS: tuple[str, ...] = (
    "nvidia-smi",
    "--query-compute-apps=pid,used_memory",
    "--format=csv,noheader,nounits",
)
NVIDIA_SMI_TIMEOUT_S = 10.0
_BYTES_PER_MIB = 1024 * 1024


class GpuMemoryError(RuntimeError):
    """The GPU memory of a CUDA run could not be read."""


def parse_compute_apps(text: str, pids: Collection[int]) -> tuple[int, bool]:
    """Sum the used GPU memory of the given PIDs from ``nvidia-smi`` output.

    Args:
        text: Output of ``NVIDIA_SMI_ARGS``: one ``pid, used_memory`` line per
            process and GPU, memory in MiB. Blank output means no compute process.
        pids: The server PIDs to count. Lines of other PIDs are ignored.

    Returns:
        The summed used memory in MiB, and whether any line named a server PID.

    Raises:
        GpuMemoryError: A non-blank line is not two integers, for example
            ``[N/A]`` in place of the memory. The error names the line.
    """
    total = 0
    matched = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        fields = [field.strip() for field in line.split(",")]
        try:
            if len(fields) != 2:
                raise ValueError(line)
            pid, used_mib = int(fields[0]), int(fields[1])
        except ValueError:
            raise GpuMemoryError(
                f"nvidia-smi output line {line!r} is not 'pid, used_memory' in MiB; "
                "the GPU memory cannot be read"
            ) from None
        if pid in pids:
            total += used_mib
            matched = True
    return total, matched


def run_nvidia_smi(
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Run the compute-apps query once and return its output.

    Args:
        run: The subprocess call, injectable so tests never run ``nvidia-smi``.

    Returns:
        The standard output of ``NVIDIA_SMI_ARGS``.

    Raises:
        GpuMemoryError: ``nvidia-smi`` is missing, times out or exits non-zero.
    """
    try:
        result = run(
            list(NVIDIA_SMI_ARGS),
            capture_output=True,
            text=True,
            check=False,
            timeout=NVIDIA_SMI_TIMEOUT_S,
        )
    except FileNotFoundError:
        raise GpuMemoryError(
            "nvidia-smi not found on PATH; a CUDA run needs it to read GPU memory"
        ) from None
    except subprocess.TimeoutExpired:
        raise GpuMemoryError(f"nvidia-smi did not answer within {NVIDIA_SMI_TIMEOUT_S} s") from None
    if result.returncode != 0:
        raise GpuMemoryError(
            f"nvidia-smi exited with code {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


class GpuMemorySampler(threading.Thread):
    """Sample the server's peak GPU memory every 0.5 s (design D9).

    Use ``start()`` before the timed work and ``stop()`` after it. On a CUDA run
    ``start()`` takes one sample at once, so a missing ``nvidia-smi`` stops the
    run before any timing. An error inside the thread ends sampling and
    ``stop()`` raises it.
    """

    def __init__(
        self,
        *,
        cuda: bool,
        pid_source: Callable[[], Collection[int]],
        runner: Callable[[], str] = run_nvidia_smi,
        interval_s: float = SAMPLE_INTERVAL_S,
    ) -> None:
        """Set up the sampler.

        Args:
            cuda: True when the server runs on the CUDA backend. False (Metal or
                CPU) records no GPU value and never calls ``nvidia-smi``.
            pid_source: Returns the current server PIDs; read at every sample,
                because the router starts its child servers on demand.
            runner: Returns one ``nvidia-smi`` output; injectable for tests.
            interval_s: Seconds between samples.
        """
        super().__init__(daemon=True)
        self.cuda = cuda
        self.pid_source = pid_source
        self.runner = runner
        self.interval_s = interval_s
        self.stop_event = threading.Event()
        self.peak_mib = 0
        self.matched = False
        self.error: GpuMemoryError | None = None

    def sample(self) -> None:
        """Take one sample and update the peak. Does nothing on a non-CUDA run."""
        if not self.cuda:
            return
        used_mib, matched = parse_compute_apps(self.runner(), set(self.pid_source()))
        self.peak_mib = max(self.peak_mib, used_mib)
        self.matched = self.matched or matched

    def start(self) -> None:
        """Take a first sample (CUDA only), then start the sampling thread."""
        self.sample()
        super().start()

    def run(self) -> None:
        """Sample until ``stop()``; keep the first error for ``stop()``."""
        if not self.cuda:
            return
        while not self.stop_event.wait(self.interval_s):
            try:
                self.sample()
            except GpuMemoryError as exc:
                self.error = exc
                return

    def stop(self) -> float | None:
        """Stop sampling and return the peak GPU memory.

        Returns:
            The peak in MB (10**6 bytes, one decimal, as ``peak_rss_mb``), or
            None on a Metal or CPU run.

        Raises:
            GpuMemoryError: A sample failed, or ``nvidia-smi`` never listed a
                server PID, so the GPU memory was not read.
        """
        self.stop_event.set()
        if self.is_alive():
            self.join()
        if not self.cuda:
            return None
        if self.error is not None:
            raise self.error
        if not self.matched:
            raise GpuMemoryError(
                "nvidia-smi never listed a server PID; the GPU memory was not read "
                "(a container PID namespace can hide the server's processes)"
            )
        return round(self.peak_mib * _BYTES_PER_MIB / 1e6, 1)
