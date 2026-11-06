"""A blank program with no provisioned build is ``not-provisioned`` (spec ``llamacpp-server``).

Spec scenario "Nothing provisioned": ``llamacpp_server_binary`` is blank and no
pinned build is installed, so the router is ``failed`` with ``not-provisioned``
and no process starts. The line names ``omrs llamacpp install`` and the Get
llama.cpp action. A fake ``llama-server`` stands in; nothing is downloaded.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.unit.test_llamacpp_router_compose_support import (
    EMBED,
    RouterRig,
    composed_rig,
    point_at,
)

from omrs.integrations.llamacpp_runtime import rules
from omrs.integrations.llamacpp_runtime.lease import reason_text

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

LINE = (
    "llama.cpp is not installed. Run `omrs llamacpp install` or press Get llama.cpp "
    "on the Integrations page."
)


@pytest.fixture
def router(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from composed_rig(tmp_path, monkeypatch)


def _embed_through_gate(rig: RouterRig) -> httpx.Response:
    from omrs.core import runtime_gate

    gate = runtime_gate.gate_for("embeddings")
    url = f"http://127.0.0.1:{rig.port}/v1/embeddings"
    request = httpx.Request("POST", url, json={"model": EMBED})
    return runtime_gate.GatedTransport(gate).handle_request(request)


def test_the_reason_is_fixed_and_its_line_names_both_ways_out() -> None:
    assert "not-provisioned" in rules.REASONS
    assert reason_text("not-provisioned") == LINE


def test_a_blank_program_with_no_build_refuses_with_not_provisioned(
    router: RouterRig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from omrs import compose_runtimes

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "no-provisioned-build"))
    point_at(router, monkeypatch, LLAMACPP_SERVER_BINARY="")
    compose_runtimes.install_gates(None)

    response = _embed_through_gate(router)

    assert response.json()["error"]["code"] == "not-provisioned"
    assert LINE in response.json()["error"]["message"]
    assert router.starts() == 0
    item = compose_runtimes.list_runtimes()[0]
    assert (item["state"], item["reason"], item["reason_text"]) == (
        "failed",
        "not-provisioned",
        LINE,
    )


def test_compose_resolves_a_blank_program_to_the_provisioned_build(
    router: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blank program goes through ``resolve_server_binary``: the provisioned build runs."""
    from omrs import compose_runtimes

    asked: list[str] = []

    def provisioned(configured: str) -> str:
        asked.append(configured)
        return configured or str(router.binary)

    monkeypatch.setattr(compose_runtimes, "resolve_server_binary", provisioned)
    point_at(router, monkeypatch, LLAMACPP_SERVER_BINARY="")
    compose_runtimes.install_gates(None)

    assert _embed_through_gate(router).status_code == 200
    assert "" in asked
    assert router.starts() == 1


# ── The Router panel ─────────────────────────────────────────────────────


pytest.importorskip("fastapi")

from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

harness = support.harness
rig = support.rig


def test_start_with_nothing_provisioned_is_failed_not_provisioned(
    rig: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "no-provisioned-build"))
    check = ContractChecker()
    with rig(llamacpp_server_binary="") as r:
        r.save_files()
        response = r.post("start")
        check.check(response, 200)
        body = response.json()
        assert (body["state"], body["reason"], body["reason_text"]) == (
            "failed",
            "not-provisioned",
            LINE,
        )
        assert body["program"] == {"path": "", "source": "none"}
        assert r.pids() == []
        check.check(r.client.get("/v1/runtimes"), 200)
