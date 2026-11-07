"""A second lost connection after a crash restart is a refusal (review fix 3; design D5).

The router lease restarts a crashed router once per request. When the request
loses its connection again, the caller gets ``RuntimeRequestFailed`` with
reason ``exited``, and the gate answers with a refusal that clients must not
retry. No second restart happens. A fake router ``llama-server`` stands in.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from tests.unit.test_llamacpp_router_lock_order import kill_router, within
from tests.unit.test_llamacpp_router_worker import (
    CHAT,
    RouterRig,
    as_entries,
    rig_fixture,
)

from omrs.compose_runtimes import RouterGate
from omrs.core.runtime_gate import NO_RETRY_HEADER, REFUSED_STATUS, GatedTransport
from omrs.integrations.llamacpp_runtime.lease import RuntimeRequestFailed
from omrs.integrations.llamacpp_runtime.router_lease import open_router

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


class CrashingTransport(httpx.BaseTransport):
    """Kills the router before it sends each request, so every send loses its connection."""

    def __init__(self) -> None:
        self.inner = httpx.HTTPTransport()
        self.kills = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        kill_router()
        self.kills += 1
        return self.inner.handle_request(request)


def test_second_lost_connection_is_exited_after_one_restart(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    crashing = CrashingTransport()

    def send(url: str) -> httpx.Response:
        request = httpx.Request("POST", f"{url}/v1/chat/completions", json={"model": CHAT})
        return crashing.handle_request(request)

    def body() -> None:
        with pytest.raises(RuntimeRequestFailed) as caught:
            router.request_model(CHAT, send)
        assert caught.value.reason == "exited"

    within(rig, body)
    assert crashing.kills == 2
    assert rig.starts() == 2  # the first start and one restart, no more


def test_gate_answers_a_second_crash_with_a_no_retry_refusal(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    crashing = CrashingTransport()
    transport = GatedTransport(RouterGate(router), inner=crashing)
    request = httpx.Request(
        "POST", f"http://127.0.0.1:{rig.port}/v1/chat/completions", json={"model": CHAT}
    )

    response = within(rig, lambda: transport.handle_request(request))

    assert response.status_code == REFUSED_STATUS
    assert response.headers[NO_RETRY_HEADER] == "false"
    assert response.json()["error"]["code"] == "exited"
    assert crashing.kills == 2
    assert rig.starts() == 2
