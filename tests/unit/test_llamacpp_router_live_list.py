"""A saved model list reaches the running app (one-llamacpp-router D3, D7; bug B).

``llamacpp_models`` and ``decision_models`` are file-only maps. The routes read
``omrs.jsonc``, and compose and the Engine must read the same list, or the next
gate request writes the old preset back to ``models.ini`` and reverts the save
without a sign. A fake router ``llama-server`` stands in for the real one.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("fastapi")

import httpx  # noqa: E402
from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402
from tests.unit.test_web_llamacpp_router_support import ORIGIN  # noqa: E402

from omrs import compose_runtimes  # noqa: E402
from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL  # noqa: E402
from omrs.core import runtime_gate  # noqa: E402
from omrs.integrations.llamacpp_runtime import children  # noqa: E402
from omrs.integrations.llamacpp_runtime.preset_writer import (  # noqa: E402
    read_preset,
    split_sections,
)
from omrs.integrations.llamacpp_runtime.router_spec import router_dir  # noqa: E402
from omrs.integrations.llamacpp_runtime.state import read_server_record, state_root  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

DECISIONS = "/v1/settings/decision-models"


@pytest.fixture(autouse=True)
def _reset_gates() -> Iterator[None]:
    yield
    compose_runtimes.reset()


def _install_gates(r: Any) -> Any:
    """Install the gate resolver over the app's saved values, as ``omrs web`` does."""
    state = r.h.app.state.runtime.providers
    compose_runtimes.install_gates(state.source)
    return state


def _through_gate(model: str) -> str:
    """Send one request for *model* through the gate; return the router base URL."""
    gate = runtime_gate.gate_for("classification")
    assert gate is not None
    return gate.request(lambda url: url, model=model)


def _sections() -> dict[str, str]:
    return split_sections(read_preset(router_dir(state_root())))


def _router_children() -> set[int]:
    record = read_server_record(router_dir(state_root()))
    assert record is not None
    return set(children.direct_children(record.pid))


def _args(url: str, model: str) -> list[str]:
    items = httpx.get(f"{url.removesuffix('/v1')}/v1/models", timeout=10).json()["data"]
    return next(i["status"]["args"] for i in items if i["id"] == model)


def test_a_saved_preset_edit_survives_the_next_gate_request(rig: Any) -> None:
    """Save through the route, then use the gate: the new value stays, one model reloads."""
    with rig() as r:
        r.save_files()
        assert r.post("start").json()["state"] == "running"
        _install_gates(r)
        _through_gate(EMBED_MODEL)
        _through_gate(CLASSIFY_MODEL)
        loaded = _router_children()
        assert len(loaded) == 2

        body = {"preset": {"ctx-size": 4096, "parallel": 2}}
        assert r.put_model("qwen3-4b", body).status_code == 200
        _through_gate(EMBED_MODEL)

        assert "ctx-size = 4096" in _sections()[CLASSIFY_MODEL]
        assert "ctx-size = 8192" in _sections()[EMBED_MODEL]
        assert len(loaded & _router_children()) == 1  # only the edited model unloaded
        url = _through_gate(CLASSIFY_MODEL)
        args = _args(url, CLASSIFY_MODEL)
        assert args[args.index("--ctx-size") + 1] == "4096"
        assert "ctx-size = 4096" in _sections()[CLASSIFY_MODEL]


def test_the_engine_and_compose_see_the_saved_list(rig: Any) -> None:
    with rig() as r:
        state = _install_gates(r)
        assert r.put_model("qwen3-4b", {"preset": {"ctx-size": 4096}}).status_code == 200

        settings = compose_runtimes.current_settings(state.source())
        assert settings.llamacpp_models["qwen3-4b"].preset["ctx-size"] == 4096
        engine = r.h.engines[0]
        assert engine._effective_settings.llamacpp_models["qwen3-4b"].preset["ctx-size"] == 4096


def test_a_saved_decision_model_reaches_compose_and_the_engine(rig: Any) -> None:
    """``decision_models`` had the same stale snapshot; it follows the file too."""
    with rig() as r:
        state = _install_gates(r)
        entry = {"kind": "llamacpp", "address": "http://127.0.0.1:9200", "model": "clef-q8_0"}
        body = {"entry": entry, "revision": r.get()["revision"]}
        response = r.client.put(f"{DECISIONS}/clef", json=body, headers=ORIGIN)
        assert response.status_code == 200, response.text

        settings = compose_runtimes.current_settings(state.source())
        assert settings.decision_models["clef"].model == "clef-q8_0"
        engine = r.h.engines[0]
        assert engine._effective_settings.decision_models["clef"].model == "clef-q8_0"
