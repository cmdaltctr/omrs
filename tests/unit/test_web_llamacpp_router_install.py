"""``POST`` and ``GET /v1/llamacpp/router/install`` (task 7.1, design D12).

``provision.install_pinned_build`` is replaced by a fake that waits on a gate,
so a test reads the running state. No archive is downloaded and no binary is
placed. The provisioning code has its own tests (``test_llamacpp_router_provision.py``).
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_connections_edit as edit  # noqa: E402
from tests.unit import test_web_llamacpp_router_support as support  # noqa: E402
from tests.unit.test_web_llamacpp_router_support import ORIGIN, URL  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.integrations.llamacpp_runtime import pins, provision  # noqa: E402
from omrs.integrations.llamacpp_runtime.provision import ProvisionedBuild  # noqa: E402
from omrs.transports.api import security  # noqa: E402

harness = support.harness
rig = support.rig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

INSTALL = f"{URL}/install"


class Install:
    """A fake ``install_pinned_build``: records its calls and waits on a gate."""

    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.gate = threading.Event()
        self.started = threading.Event()
        self.error: provision.ProvisionError | None = None

    def __call__(self, flavour: str | None = None, report: Any = None) -> ProvisionedBuild:
        self.calls.append(flavour)
        self.started.set()
        if report is not None:
            report("Downloading llama-b11941-bin-ubuntu-x64.tar.gz")
        assert self.gate.wait(10)
        if self.error is not None:
            raise self.error
        return ProvisionedBuild(Path("/data/b11941-cpu/llama-server"), "cpu", 11941)


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch) -> Install:
    fake = Install()
    monkeypatch.setattr(provision, "install_pinned_build", fake)
    monkeypatch.setattr(provision, "detect_flavour", lambda: "cuda")
    monkeypatch.setattr(provision, "resolve_server_binary", lambda configured: configured)
    return fake


def settle(r: Any) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while True:
        body = r.client.get(INSTALL).json()
        if body["job"]["state"] != "running":
            return body
        assert time.monotonic() < deadline, body
        time.sleep(0.01)


def post(r: Any, **body: Any) -> Any:
    return r.client.post(INSTALL, json=body, headers=ORIGIN)


# ── GET ──────────────────────────────────────────────────────────────────


def test_get_reports_the_detected_flavour_and_the_choices(rig: Any, install: Install) -> None:
    with rig() as r:
        body = r.client.get(INSTALL).json()
        assert (body["build"], body["detected"], body["choices"]) == (
            pins.LLAMA_TAG,
            "cuda",
            ["cpu", "cuda"],
        )
        assert body["installed_path"] is None
        assert body["job"]["state"] == "idle"
        assert install.calls == []  # a read installs nothing


def test_get_on_macos_gives_no_choice(
    rig: Any, install: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(provision, "detect_flavour", lambda: "metal")
    with rig() as r:
        body = r.client.get(INSTALL).json()
        assert (body["detected"], body["choices"]) == ("metal", [])


def test_get_on_an_unpinned_platform_says_so(
    rig: Any, install: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unsupported() -> str:
        raise pins.NotSupported("no archive")

    monkeypatch.setattr(provision, "detect_flavour", unsupported)
    with rig() as r:
        body = r.client.get(INSTALL).json()
        assert (body["detected"], body["choices"]) == (None, [])


def test_get_names_the_provisioned_program(
    rig: Any, install: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(provision, "resolve_server_binary", lambda configured: "/data/llama-server")
    with rig() as r:
        assert r.client.get(INSTALL).json()["installed_path"] == "/data/llama-server"


def test_get_needs_read_and_a_read_bearer_can_see_it(rig: Any, install: Install) -> None:
    with rig() as r:
        r.client.cookies.clear()
        assert r.client.get(INSTALL).status_code == 401
        assert r.client.get(INSTALL, headers=edit.bearer(r.h.policy, "read")).status_code == 200


# ── POST ─────────────────────────────────────────────────────────────────


def test_the_flavour_in_the_request_reaches_the_job(rig: Any, install: Install) -> None:
    with rig() as r:
        response = post(r, flavour="cpu")
        assert response.status_code == 202, response.text
        assert install.started.wait(5)
        assert install.calls == ["cpu"]
        running = r.client.get(INSTALL).json()["job"]
        assert (running["state"], running["flavour"]) == ("running", "cpu")
        assert "Downloading" in running["line"]
        install.gate.set()
        done = settle(r)["job"]
        assert (done["state"], done["reason"], done["message"]) == ("succeeded", None, None)


def test_no_flavour_leaves_the_choice_to_the_job(rig: Any, install: Install) -> None:
    with rig() as r:
        assert post(r).status_code == 202
        assert install.started.wait(5)
        assert install.calls == [None]
        install.gate.set()
        settle(r)


def test_a_failure_gives_a_fixed_reason_and_no_binary(rig: Any, install: Install) -> None:
    install.error = provision.ProvisionError("file-changed", "archive does not match its SHA-256")
    install.gate.set()
    with rig() as r:
        post(r, flavour="cpu")
        job = settle(r)["job"]
        assert (job["state"], job["reason"]) == ("failed", "file-changed")
        assert "SHA-256" in job["message"]
        assert r.client.get(INSTALL).json()["installed_path"] is None


def test_a_second_install_while_one_runs_is_409_busy(rig: Any, install: Install) -> None:
    with rig() as r:
        assert post(r, flavour="cpu").status_code == 202
        assert install.started.wait(5)
        second = post(r, flavour="cuda")
        assert second.status_code == 409
        assert second.json()["reason"] == "busy"
        assert install.calls == ["cpu"]
        install.gate.set()
        settle(r)


@pytest.mark.parametrize("bad", ["gpu", "metal", "", 3])
def test_an_unknown_flavour_is_400_and_starts_no_job(rig: Any, install: Install, bad: Any) -> None:
    with rig() as r:
        assert post(r, flavour=bad).status_code == 400
        assert install.calls == []


def test_a_flavour_on_macos_is_400(
    rig: Any, install: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(provision, "detect_flavour", lambda: "metal")
    with rig() as r:
        response = post(r, flavour="cpu")
        assert response.status_code == 400
        assert "macOS" in response.json()["message"]
        assert install.calls == []


def test_an_unknown_body_key_is_400(rig: Any, install: Install) -> None:
    with rig() as r:
        assert post(r, flavour="cpu", url="http://x").status_code == 400
        assert install.calls == []


def test_the_install_needs_manage_and_a_session(
    rig: Any, install: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    with rig() as r:
        every = security.SESSION_SCOPES
        monkeypatch.setattr(security, "SESSION_SCOPES", every - {"manage"})
        assert post(r, flavour="cpu").status_code == 403
        monkeypatch.setattr(security, "SESSION_SCOPES", every)
        r.client.cookies.clear()
        header = edit.bearer(r.h.policy, "read", "graph", "run")
        assert r.client.post(INSTALL, json={}, headers=header).status_code == 403
        assert install.calls == []


def test_an_install_changes_no_setting(rig: Any, install: Install) -> None:
    with rig() as r:
        post(r, flavour="cpu")
        install.gate.set()
        settle(r)
        assert r.file_text() == ""


def test_the_responses_conform_to_the_contract(rig: Any, install: Install) -> None:
    check = ContractChecker()
    with rig() as r:
        check.check(r.client.get(INSTALL), 200)
        check.check(post(r, flavour="gpu"), 400)
        check.check(post(r, flavour="cpu"), 202)
        assert install.started.wait(5)
        check.check(post(r, flavour="cpu"), 409)
        check.check(r.client.get(INSTALL), 200)
        install.gate.set()
        settle(r)
        install.error = provision.ProvisionError("cuda-device-missing", "no CUDA device")
        install.gate.set()
        check.check(post(r, flavour="cuda"), 202)
        settle(r)
        check.check(r.client.get(INSTALL), 200)
    assert {"installLlamacppBuild", "getLlamacppBuild"} <= check.operations
