"""Tests for the GPU memory sampler of the timing runner (change task 4.4, design D9).

Run with: uv run --no-sync pytest test_gpu_memory.py -q

No test runs a real ``nvidia-smi``: every call goes through an injected runner.
"""

from __future__ import annotations

import subprocess
import time

import pytest
from gpu_memory import (
    NVIDIA_SMI_ARGS,
    SAMPLE_INTERVAL_S,
    GpuMemoryError,
    GpuMemorySampler,
    parse_compute_apps,
    run_nvidia_smi,
)

# --- parsing (pure) ---------------------------------------------------------


def test_parse_sums_used_memory_of_server_pids_only():
    text = "101, 4000\n202, 1500\n999, 7000\n"
    assert parse_compute_apps(text, {101, 202}) == (5500, True)


def test_parse_ignores_pid_not_in_set():
    assert parse_compute_apps("999, 7000\n", {101}) == (0, False)


def test_parse_blank_output_is_zero_and_no_match():
    assert parse_compute_apps("", {101}) == (0, False)
    assert parse_compute_apps("\n  \n", {101}) == (0, False)


def test_parse_sums_two_lines_of_one_pid():
    # One line per GPU per process on a multi-GPU machine.
    assert parse_compute_apps("101, 100\n101, 200\n", {101}) == (300, True)


@pytest.mark.parametrize("line", ["101, [N/A]", "garbage", "101, 5, 6", "x, 5"])
def test_parse_refuses_malformed_line_and_names_it(line):
    with pytest.raises(GpuMemoryError) as exc:
        parse_compute_apps(f"202, 10\n{line}\n", {202})
    assert line in str(exc.value)
    assert "nvidia-smi" in str(exc.value)


# --- the subprocess call ----------------------------------------------------


def test_nvidia_smi_args_are_the_compute_apps_query():
    assert NVIDIA_SMI_ARGS == (
        "nvidia-smi",
        "--query-compute-apps=pid,used_memory",
        "--format=csv,noheader,nounits",
    )


def test_run_nvidia_smi_returns_stdout():
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout="101, 5\n", stderr="")

    assert run_nvidia_smi(run=fake_run) == "101, 5\n"
    assert seen["args"] == list(NVIDIA_SMI_ARGS)


def test_run_nvidia_smi_missing_names_nvidia_smi():
    def fake_run(args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "nvidia-smi")

    with pytest.raises(GpuMemoryError, match="nvidia-smi"):
        run_nvidia_smi(run=fake_run)


def test_run_nvidia_smi_failure_names_nvidia_smi_and_exit_code():
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 9, stdout="", stderr="No devices were found")

    with pytest.raises(GpuMemoryError) as exc:
        run_nvidia_smi(run=fake_run)
    assert "nvidia-smi" in str(exc.value)
    assert "9" in str(exc.value)
    assert "No devices were found" in str(exc.value)


def test_run_nvidia_smi_timeout_names_nvidia_smi():
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 0))

    with pytest.raises(GpuMemoryError, match="nvidia-smi"):
        run_nvidia_smi(run=fake_run)


# --- the sampler ------------------------------------------------------------


def test_sample_interval_is_half_a_second():
    assert SAMPLE_INTERVAL_S == 0.5


class _Outputs:
    """Runner that returns fixed outputs in turn, then repeats the last one."""

    def __init__(self, *outputs: str) -> None:
        self.outputs = list(outputs)
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.outputs[min(self.calls, len(self.outputs)) - 1]


def test_cuda_sampler_keeps_peak_in_mb():
    runner = _Outputs("101, 1000\n", "101, 3000\n202, 1000\n", "101, 500\n")
    sampler = GpuMemorySampler(cuda=True, pid_source=lambda: {101, 202}, runner=runner)
    for _ in range(3):
        sampler.sample()
    # 4000 MiB = 4000 * 1048576 bytes = 4194.304 MB, rounded as peak_rss_mb is.
    assert sampler.stop() == 4194.3


def test_cuda_sampler_thread_samples_and_stops():
    runner = _Outputs("101, 2000\n")
    sampler = GpuMemorySampler(cuda=True, pid_source=lambda: {101}, runner=runner, interval_s=0.001)
    sampler.start()
    deadline = time.monotonic() + 5
    while runner.calls < 3 and time.monotonic() < deadline:
        time.sleep(0.001)
    assert sampler.stop() == 2097.2
    assert not sampler.is_alive()


def test_cuda_start_fails_at_once_when_nvidia_smi_missing():
    def missing() -> str:
        raise GpuMemoryError("nvidia-smi not found")

    sampler = GpuMemorySampler(cuda=True, pid_source=lambda: {101}, runner=missing)
    with pytest.raises(GpuMemoryError, match="nvidia-smi"):
        sampler.start()


def test_cuda_error_inside_thread_is_raised_by_stop():
    runner = _Outputs("101, 10\n", "101, 10\n", "101, [N/A]\n")
    sampler = GpuMemorySampler(cuda=True, pid_source=lambda: {101}, runner=runner, interval_s=0.001)
    sampler.start()
    sampler.join(timeout=5)  # the thread ends on the error
    with pytest.raises(GpuMemoryError, match=r"nvidia-smi.*\[N/A\]"):
        sampler.stop()


def test_cuda_pid_source_failure_inside_thread_is_raised_by_stop():
    calls = []

    def pids() -> set[int]:
        calls.append(1)
        if len(calls) > 1:
            raise OSError("state file gone")
        return {101}

    sampler = GpuMemorySampler(
        cuda=True, pid_source=pids, runner=_Outputs("101, 10\n"), interval_s=0.001
    )
    sampler.start()
    sampler.join(timeout=5)  # the thread ends on the error
    with pytest.raises(GpuMemoryError, match=r"state file gone"):
        sampler.stop()


def test_cuda_stop_refuses_when_no_server_pid_was_ever_listed():
    # A container PID namespace can hide the server: no silent zero.
    runner = _Outputs("999, 7000\n")
    sampler = GpuMemorySampler(cuda=True, pid_source=lambda: {101}, runner=runner)
    sampler.sample()
    with pytest.raises(GpuMemoryError, match="nvidia-smi"):
        sampler.stop()


def test_metal_or_cpu_records_none_and_never_calls_nvidia_smi():
    def must_not_run() -> str:
        raise AssertionError("nvidia-smi called on a non-CUDA run")

    sampler = GpuMemorySampler(cuda=False, pid_source=lambda: {101}, runner=must_not_run)
    sampler.start()
    sampler.sample()
    assert sampler.stop() is None
