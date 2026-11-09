"""Construction tests for Magika's bounded ONNX session (issue #201)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.integrations import magika


def _construct_with_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    visible_cpus: int,
    affinity: bool = True,
    affinity_error: bool = False,
) -> dict[str, Any]:
    """Drive the lazy constructor with fake optional runtime modules."""
    calls: dict[str, Any] = {}

    class FakeMagika:
        def __init__(self) -> None:
            self._model_path = Path("model.onnx")
            self._onnx_session = self._init_onnx_session()

        def _init_onnx_session(self) -> None:
            return None

    class FakeSessionOptions:
        intra_op_num_threads = 0
        inter_op_num_threads = 0

    def fake_session(model: Path, *, providers: list[str], sess_options: Any) -> object:
        calls.update(
            model=model,
            providers=providers,
            intra=sess_options.intra_op_num_threads,
            inter=sess_options.inter_op_num_threads,
        )
        return object()

    monkeypatch.setitem(sys.modules, "magika", SimpleNamespace(Magika=FakeMagika))
    monkeypatch.setitem(
        sys.modules,
        "onnxruntime",
        SimpleNamespace(
            SessionOptions=FakeSessionOptions,
            InferenceSession=fake_session,
            disable_telemetry_events=lambda: None,
        ),
    )
    if affinity_error:

        def fail_affinity(_pid: int) -> range:
            raise OSError("affinity denied")

        monkeypatch.setattr(magika.os, "sched_getaffinity", fail_affinity, raising=False)
        monkeypatch.setattr(magika.os, "cpu_count", lambda: visible_cpus)
    elif affinity:
        monkeypatch.setattr(
            magika.os, "sched_getaffinity", lambda _pid: range(visible_cpus), raising=False
        )
    else:
        monkeypatch.delattr(magika.os, "sched_getaffinity", raising=False)
        monkeypatch.setattr(magika.os, "cpu_count", lambda: visible_cpus)

    magika.reset_magika_cache()
    try:
        instance = magika._get_magika_instance()
    finally:
        magika.reset_magika_cache()
    assert isinstance(instance, FakeMagika)
    return calls


@pytest.mark.parametrize(("visible_cpus", "expected"), [(4, 4), (8, 8), (96, 8)])
def test_constructor_caps_intra_op_threads_and_uses_one_inter_op_thread(
    monkeypatch: pytest.MonkeyPatch, visible_cpus: int, expected: int
) -> None:
    calls = _construct_with_fakes(monkeypatch, visible_cpus=visible_cpus)

    assert calls == {
        "model": Path("model.onnx"),
        "providers": ["CPUExecutionProvider"],
        "intra": expected,
        "inter": 1,
    }


def test_constructor_falls_back_to_cpu_count_without_affinity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _construct_with_fakes(monkeypatch, visible_cpus=6, affinity=False)

    assert calls["intra"] == 6
    assert calls["inter"] == 1


def test_constructor_uses_cpu_count_when_affinity_is_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _construct_with_fakes(monkeypatch, visible_cpus=6, affinity_error=True)

    assert calls["intra"] == 6
    assert calls["inter"] == 1
