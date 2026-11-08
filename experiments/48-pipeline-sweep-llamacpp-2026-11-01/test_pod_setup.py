"""Tests for the GPU check of ``pod_setup.sh`` (PR 195 review fix, CodeRabbit 2026-11-08).

Run with: uv run --no-sync pytest test_pod_setup.py -q

The test cuts the ``gpu_is_single_4090`` function out of the script and runs
it in bash on fixed ``nvidia-smi`` listings. Nothing runs ``nvidia-smi``,
``uv`` or a download.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parent / "pod_setup.sh").read_text(encoding="utf-8")


def _accepts(listing: str) -> bool:
    match = re.search(r"^gpu_is_single_4090\(\) \{\n.*?^\}\n", SCRIPT, flags=re.S | re.M)
    assert match, "pod_setup.sh has no gpu_is_single_4090 function"
    code = match.group(0) + 'gpu_is_single_4090 "$1"\n'
    done = subprocess.run(
        ["bash", "-c", code, "_", listing], capture_output=True, text=True, timeout=30, check=False
    )
    return done.returncode == 0


def test_one_rtx_4090_is_accepted():
    assert _accepts("NVIDIA GeForce RTX 4090, 24564 MiB")


@pytest.mark.parametrize(
    "listing",
    [
        "NVIDIA A100-SXM4-80GB, 81920 MiB",
        "NVIDIA GeForce RTX 3090, 24576 MiB",
        "NVIDIA GeForce RTX 4090, 24564 MiB\nNVIDIA GeForce RTX 4090, 24564 MiB",
        "NVIDIA GeForce RTX 4090, 24564 MiB\nNVIDIA A100-SXM4-80GB, 81920 MiB",
        "",
    ],
)
def test_any_other_listing_is_refused(listing):
    assert not _accepts(listing)


def test_step_4_uses_the_check_and_stops_with_the_listing():
    step = SCRIPT[SCRIPT.index('step 4 "') : SCRIPT.index('step 5 "')]
    assert 'gpu_is_single_4090 "$GPUS" || die' in step
