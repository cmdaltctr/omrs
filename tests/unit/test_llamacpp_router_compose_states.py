"""Router lifecycle states and model states seen through compose (one-llamacpp-router, task 4.4).

Spec ``llamacpp-server`` "Lifecycle states and fixed reasons" and "Start moves to
running or to a failed state": the router start waits up to 180 seconds for
``GET /health`` and loads no model; a model is ``not-downloaded``, ``unloaded``,
``loading``, ``loaded`` or ``failed`` with a fixed reason. The fake router of
``tests/fixtures/llamacpp`` stands in for ``llama-server``.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.fixtures.llamacpp.harness import pid_alive
from tests.unit.test_llamacpp_router_compose_support import (
    CHAT,
    EMBED,
    RouterRig,
    composed_rig,
    point_at,
)

from omrs.integrations.llamacpp_runtime import MODEL_REASONS, MODEL_STATES, ModelUnavailable

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from composed_rig(tmp_path, monkeypatch)


def _router_item() -> dict[str, Any]:
    from omrs import compose_runtimes

    return next(i for i in compose_runtimes.list_runtimes() if i["id"] == "router")


def _send(model: str) -> httpx.Response:
    from omrs import compose
    from omrs.core import runtime_gate

    url = f"{compose.get_settings().llamacpp_router_url}/embeddings"
    request = httpx.Request("POST", url, json={"model": model, "input": "x"})
    gate = runtime_gate.gate_for("embeddings")
    assert gate is not None
    return runtime_gate.GatedTransport(gate).handle_request(request)


def test_the_fixed_sets_match_the_spec() -> None:
    from omrs.integrations.llamacpp_runtime.process import HEALTH_TIMEOUT_SECONDS

    assert HEALTH_TIMEOUT_SECONDS == 180
    assert MODEL_STATES == ("not-downloaded", "unloaded", "loading", "loaded", "failed")
    assert set(MODEL_REASONS) == {
        "model-invalid", "file-changed", "preset-invalid", "model-load-failed",
        "model-not-listed", "role-mismatch", "version-busy",
    }  # fmt: skip


def test_a_healthy_start_loads_no_model(rig: RouterRig, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec "Healthy start": running, and every listed model ``unloaded``."""
    from omrs import compose, compose_runtimes

    point_at(rig, monkeypatch)
    lease = compose_runtimes.router_lease_for(compose.get_settings())
    assert not isinstance(lease, str)

    lease.join()

    item = _router_item()
    assert item["state"] == "running"
    assert {row["state"] for row in item["models"]} == {"unloaded"}


def test_a_request_to_an_entry_with_no_file_is_not_downloaded(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The entry is ``not-downloaded``, not a failed ``model-invalid``; other models serve."""
    from omrs import compose_runtimes

    entries = rig.entries()
    entries[1]["file"] = None
    point_at(rig, monkeypatch, entries=entries)
    compose_runtimes.install_gates(None)

    refused = _send(CHAT)

    assert refused.json()["error"]["code"] == "not-downloaded"
    assert refused.json()["error"]["message"] == "The model file is not downloaded yet."
    assert _send(EMBED).status_code == 200


def test_the_router_lease_reports_not_downloaded_as_a_state(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose, compose_runtimes

    entries = rig.entries()
    entries[1]["file"] = None
    point_at(rig, monkeypatch, entries=entries)
    lease = compose_runtimes.router_lease_for(compose.get_settings())
    assert not isinstance(lease, str)

    with pytest.raises(ModelUnavailable) as refused:
        lease.ensure_ready(CHAT)

    assert (refused.value.state, refused.value.reason) == ("not-downloaded", "not-downloaded")


def test_a_router_that_never_answers_health_fails_with_timeout_and_stops(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec "Timeout": ``failed`` with ``timeout``, and the owned process is stopped."""
    from omrs import compose_runtimes
    from omrs.integrations.llamacpp_runtime import process

    monkeypatch.setattr(process, "HEALTH_TIMEOUT_SECONDS", 1.0)
    rig.set_env(FAKE_LLAMA_NEVER_HEALTHY="1")
    point_at(rig, monkeypatch)
    compose_runtimes.install_gates(None)

    refused = _send(EMBED)

    assert refused.json()["error"]["code"] == "timeout"
    item = _router_item()
    assert (item["state"], item["reason"]) == ("failed", "timeout")
    started = (rig.folder / "starts.txt").read_text(encoding="utf-8").split()[0]
    assert not pid_alive(int(started))
