"""marimo card routes and the ``tools`` list (install-marimo-from-integrations, task 4.2).

The runtime's tool detector is replaced by a fake that returns a chosen
state. Its ``uv`` is a shell script in ``tmp_path`` that records each run, so
a refused request can show that it started no process. No test runs the real
``uv`` or touches the real ``~/.local``.
"""

from __future__ import annotations

import shlex
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrs.core.plugins.versions import VersionRange  # noqa: E402
from omrs.transports.api.routes import integration_tools  # noqa: E402
from omrs.transports.api.tool_environment import ToolStatus  # noqa: E402

RANGE = VersionRange((0, 25, 1), (0, 26, 0))
STATUS = "/v1/integrations/install"
INSTALL = "/v1/integrations/tools/marimo/install"
UNINSTALL = "/v1/integrations/tools/marimo/uninstall"
INSTALL_COMMAND = 'uv tool install "marimo>=0.25.1,<0.26.0" --with jupytext'


class FakeDetector:
    """Returns a fixed tool state; tests change ``status`` between calls."""

    def __init__(self, status: ToolStatus) -> None:
        self.status = status

    def detect(self) -> ToolStatus:
        return self.status

    def tested(self) -> VersionRange:
        return RANGE


class Harness:
    def __init__(self, client: TestClient, policy: Any, tmp_path: Path) -> None:
        self.client, self.policy, self.tmp_path = client, policy, tmp_path
        self.runtime = client.app.state.runtime  # type: ignore[attr-defined]
        self.runtime.installs.python = "/env/bin/python"
        self.runs = tmp_path / "runs.txt"
        self.gate = tmp_path / "gate"
        self.uv = self._script()
        self.detector = FakeDetector(ToolStatus("not-installed", uv=self.uv))
        self.runtime.tools = self.detector

    def _script(self) -> str:
        script = self.tmp_path / "bin" / "uv"
        script.parent.mkdir(parents=True, exist_ok=True)
        gate = shlex.quote(str(self.gate))
        script.write_text(
            f'#!/bin/sh\nprintf "%s|" "$@" >> {shlex.quote(str(self.runs))}\n'
            f"echo >> {shlex.quote(str(self.runs))}\n"
            f"while [ ! -f {gate} ]; do sleep 0.02; done\necho uv done\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return str(script)

    def state(self, availability: str, **fields: Any) -> None:
        self.detector.status = ToolStatus(availability, uv=fields.pop("uv", self.uv), **fields)

    def ran(self) -> list[str]:
        return self.runs.read_text(encoding="utf-8").splitlines() if self.runs.exists() else []

    def tool(self) -> dict[str, Any]:
        response = self.client.get("/v1/integrations")
        assert response.status_code == 200, response.text
        tools = response.json()["tools"]
        assert [item["id"] for item in tools] == ["marimo"]
        return tools[0]

    def settle(self) -> dict[str, Any]:
        deadline = time.monotonic() + 10
        while True:
            install = self.client.get(STATUS).json()["install"]
            if install["state"] != "running":
                return install
            assert time.monotonic() < deadline, install
            time.sleep(0.02)

    def editor_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = SimpleNamespace(plugin="marimo", launch_id="launch-1")
        monkeypatch.setattr(self.runtime.plugins.editors, "sessions", lambda: [session])


@pytest.fixture
def harness(tmp_path: Path, effective_settings: Any) -> Iterator[Harness]:
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        harness = Harness(client, policy, tmp_path)
        yield harness
        harness.gate.touch()


# ── The tools list ───────────────────────────────────────────────────────


def test_not_installed_offers_install_and_the_copy_command(harness: Harness) -> None:
    tool = harness.tool()
    assert tool["availability"] == "not-installed"
    assert tool["name"] == "marimo" and tool["purpose"]
    assert tool["requirement"] == "marimo>=0.25.1,<0.26.0"
    assert tool["install_command"] == INSTALL_COMMAND
    assert tool["uninstall_command"] == "uv tool uninstall marimo"
    assert tool["installable"] is True and tool["install_reason"] is None
    assert tool["install_caution"] is None
    assert tool["uninstallable"] is False and tool["uninstall_reason"] == "not-installed"
    assert tool["version"] is None and tool["executable"] is None
    assert tool["plugin_status"] is None


def test_ready_shows_version_and_path_and_no_install(harness: Harness) -> None:
    harness.state("ready", version="0.25.1", jupytext=True, executable="/t/bin/marimo")
    tool = harness.tool()
    assert tool["availability"] == "ready" and tool["version"] == "0.25.1"
    assert tool["jupytext"] is True and tool["executable"] == "/t/bin/marimo"
    assert tool["installable"] is False and tool["install_reason"] == "already-installed"
    assert tool["uninstall_reason"] == "not-installed-by-app"


def test_a_card_receipt_can_be_uninstalled(harness: Harness) -> None:
    harness.state("ready", version="0.25.1", jupytext=True, installed_by_card=True)
    tool = harness.tool()
    assert tool["uninstallable"] is True and tool["uninstall_reason"] is None


@pytest.mark.parametrize(
    ("availability", "version"), [("needs-jupytext", "0.25.1"), ("outside-range", "0.27.0")]
)
def test_an_existing_marimo_gets_a_caution(
    harness: Harness, availability: str, version: str
) -> None:
    harness.state(availability, version=version)
    tool = harness.tool()
    assert tool["installable"] is True
    assert version in tool["install_caution"] and "replaces" in tool["install_caution"]


def test_no_uv_gives_unknown_without_buttons(harness: Harness) -> None:
    harness.state("unknown", uv=None, problem="uv-not-found")
    tool = harness.tool()
    assert tool["availability"] == "unknown"
    assert tool["install_reason"] == "uv-not-found" and tool["uninstall_reason"] == "uv-not-found"
    assert tool["install_command"] == INSTALL_COMMAND


def test_an_unreadable_tool_environment_is_status_unknown(harness: Harness) -> None:
    harness.state("unknown", problem="status-unknown")
    assert harness.tool()["install_reason"] == "status-unknown"


def test_a_registered_marimo_reports_its_plugin_status(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = SimpleNamespace(status="compatible")
    monkeypatch.setattr(harness.runtime.plugins.registry, "state", lambda name: state)
    assert harness.tool()["plugin_status"] == "compatible"


def test_the_extras_list_is_unchanged(harness: Harness) -> None:
    body = harness.client.get("/v1/integrations").json()
    assert "marimo" not in {entry["id"] for entry in body["integrations"]}


# ── Access ───────────────────────────────────────────────────────────────


def test_a_bearer_credential_is_refused_and_starts_nothing(harness: Harness) -> None:
    harness.client.cookies.clear()
    header = bearer(harness.policy, "read", "graph", "run")
    for path in (INSTALL, UNINSTALL):
        assert harness.client.post(path, headers={**ORIGIN, **header}).status_code == 403
        assert harness.client.post(path, headers=ORIGIN).status_code == 401
    assert harness.ran() == []


def test_an_unknown_tool_gets_404_and_starts_nothing(harness: Harness) -> None:
    for path in ("/v1/integrations/tools/jupyter/install", "/v1/integrations/tools/x/uninstall"):
        assert harness.client.post(path, headers=ORIGIN).status_code == 404
    assert harness.ran() == []


# ── Install ──────────────────────────────────────────────────────────────


def test_install_starts_the_fixed_command_and_checks_ready(harness: Harness) -> None:
    response = harness.client.post(INSTALL, headers=ORIGIN)
    assert response.status_code == 202, response.text
    install = response.json()["install"]
    assert install["state"] == "running" and install["tool"] == "marimo"
    assert install["extra"] is None and install["action"] == "install"
    assert harness.tool()["install_reason"] == "install-running"
    harness.state("ready", version="0.25.1", jupytext=True)
    harness.gate.touch()
    assert harness.settle()["state"] == "succeeded"
    assert harness.ran() == ["tool|install|marimo>=0.25.1,<0.26.0|--with|jupytext|"]
    assert harness.runtime.installs.restart_needed == {}


def test_install_fails_when_jupytext_is_still_missing(harness: Harness) -> None:
    assert harness.client.post(INSTALL, headers=ORIGIN).status_code == 202
    harness.state("needs-jupytext", version="0.25.1")
    harness.gate.touch()
    finished = harness.settle()
    assert finished["state"] == "failed" and finished["reason"] == "check-failed"
    assert "uv done" in finished["output"]


@pytest.mark.parametrize(
    ("availability", "fields", "reason"),
    [
        ("ready", {"version": "0.25.1", "jupytext": True}, "already-installed"),
        ("unknown", {"problem": "status-unknown"}, "status-unknown"),
        ("unknown", {"uv": None, "problem": "uv-not-found"}, "uv-not-found"),
    ],
)
def test_install_refusals_start_nothing(
    harness: Harness, availability: str, fields: dict[str, Any], reason: str
) -> None:
    harness.state(availability, **fields)
    response = harness.client.post(INSTALL, headers=ORIGIN)
    assert response.status_code == 409
    body = response.json()
    assert body["reason"] == reason
    assert body["message"] == integration_tools.TOOL_REASONS[reason]
    assert harness.ran() == []


def test_install_is_refused_while_another_tool_job_runs(harness: Harness) -> None:
    job = harness.runtime.installs
    harness.client.portal.call(lambda: job.start_tool("marimo", [harness.uv, "held"], lambda: True))
    response = harness.client.post(INSTALL, headers=ORIGIN)
    assert response.status_code == 409 and response.json()["reason"] == "install-running"
    harness.gate.touch()
    harness.settle()
    assert harness.ran() == ["held|"]


def test_install_is_refused_while_a_chroma_install_runs(harness: Harness) -> None:
    job = harness.runtime.installs
    harness.client.portal.call(lambda: job.start("chroma", harness.uv, ["chromadb"]))
    response = harness.client.post(INSTALL, headers=ORIGIN)
    assert response.status_code == 409 and response.json()["reason"] == "install-running"
    tool = harness.tool()
    assert tool["installable"] is False and tool["install_reason"] == "install-running"
    harness.gate.touch()
    harness.settle()
    assert [line.split("|")[1] for line in harness.ran()] == ["install", "check"]


def test_install_is_refused_while_a_marimo_editor_runs(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.editor_runs(monkeypatch)
    response = harness.client.post(INSTALL, headers=ORIGIN)
    assert response.status_code == 409 and response.json()["reason"] == "editor-running"
    assert harness.tool()["install_reason"] == "editor-running"
    assert harness.ran() == []


# ── Uninstall ────────────────────────────────────────────────────────────


def test_uninstall_runs_for_the_card_receipt_and_checks_it_is_gone(harness: Harness) -> None:
    harness.state("ready", version="0.25.1", jupytext=True, installed_by_card=True)
    response = harness.client.post(UNINSTALL, headers=ORIGIN)
    assert response.status_code == 202, response.text
    assert response.json()["install"]["action"] == "uninstall"
    harness.state("not-installed")
    harness.gate.touch()
    assert harness.settle()["state"] == "succeeded"
    assert harness.ran() == ["tool|uninstall|marimo|"]


@pytest.mark.parametrize(
    ("availability", "fields", "reason"),
    [
        ("not-installed", {}, "not-installed"),
        ("ready", {"version": "0.25.1", "jupytext": True}, "not-installed-by-app"),
        ("unknown", {"uv": None, "problem": "uv-not-found"}, "uv-not-found"),
    ],
)
def test_uninstall_refusals_start_nothing(
    harness: Harness, availability: str, fields: dict[str, Any], reason: str
) -> None:
    harness.state(availability, **fields)
    response = harness.client.post(UNINSTALL, headers=ORIGIN)
    assert response.status_code == 409
    assert response.json()["reason"] == reason
    assert response.json()["message"] == integration_tools.TOOL_REASONS[reason]
    assert harness.ran() == []


def test_uninstall_is_refused_while_a_marimo_editor_runs(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.state("ready", version="0.25.1", jupytext=True, installed_by_card=True)
    harness.editor_runs(monkeypatch)
    response = harness.client.post(UNINSTALL, headers=ORIGIN)
    assert response.status_code == 409 and response.json()["reason"] == "editor-running"
    assert harness.ran() == []


def test_every_reason_has_a_plain_line() -> None:
    reasons = {
        "already-installed",
        "status-unknown",
        "uv-not-found",
        "install-running",
        "editor-running",
        "not-installed",
        "not-installed-by-app",
    }
    assert set(integration_tools.TOOL_REASONS) == reasons
    assert all(line.endswith(".") for line in integration_tools.TOOL_REASONS.values())


# ── Contract ─────────────────────────────────────────────────────────────


def test_tool_responses_conform(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    check = ContractChecker()
    check.check(harness.client.get("/v1/integrations"), 200)
    check.check(harness.client.post("/v1/integrations/tools/x/install", headers=ORIGIN), 404)
    check.check(harness.client.post(UNINSTALL, headers=ORIGIN), 409)
    check.check(harness.client.post(INSTALL, headers=ORIGIN), 202)
    check.check(harness.client.get(STATUS), 200)
    harness.state("ready", version="0.25.1", jupytext=True, installed_by_card=True)
    harness.gate.touch()
    harness.settle()
    check.check(harness.client.get(STATUS), 200)
    check.check(harness.client.get("/v1/integrations"), 200)
    check.check(harness.client.post(INSTALL, headers=ORIGIN), 409)
    harness.gate.unlink()
    check.check(harness.client.post(UNINSTALL, headers=ORIGIN), 202)
    harness.gate.touch()
    harness.settle()
    harness.client.cookies.clear()
    read = bearer(harness.policy, "read")
    check.check(harness.client.post(INSTALL, headers={**ORIGIN, **read}), 403)
    assert {"installTool", "uninstallTool"} <= check.operations
    assert {"installTool", "uninstallTool"} == FAMILIES["integration_tools"]
