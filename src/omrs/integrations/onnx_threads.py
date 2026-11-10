"""Bounded ONNX Runtime worker pools for CPU sessions (ADR-118).

A container can see many more CPUs than it may use. A RunPod pod exposed all
96 host CPUs without a quota. An ONNX session with default options starts one
worker per visible CPU, and those workers then fight for the few real cores.
Every CPU session in OMRS builds its options here, so the cap has one source.
"""

from __future__ import annotations

import os
from typing import Any

ONNX_INTRA_OP_THREAD_CAP = 8


def visible_cpu_count() -> int:
    """Return the CPUs this process may run on, or ``os.cpu_count()``."""
    affinity = getattr(os, "sched_getaffinity", None)
    try:
        return len(affinity(0)) if affinity else (os.cpu_count() or 1)
    except OSError:
        return os.cpu_count() or 1


def capped_session_options(rt: Any) -> Any:
    """Build ``SessionOptions`` with at most 8 intra-op threads and 1 inter-op thread.

    Args:
        rt: The imported ``onnxruntime`` module. Callers import it lazily.

    Returns:
        An ``rt.SessionOptions`` instance with bounded worker pools.
    """
    options = rt.SessionOptions()
    options.intra_op_num_threads = min(visible_cpu_count(), ONNX_INTRA_OP_THREAD_CAP)
    options.inter_op_num_threads = 1
    return options
