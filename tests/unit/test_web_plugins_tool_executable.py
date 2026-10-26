"""Registration of the found marimo executable, and editor refusals during a marimo job.

install-marimo-from-integrations, tasks 5.1 and 5.2 (design D4, D5, D6). The
plugin host uses the fake probe runner and the fake launcher of the plugin
tests, and the runtime's tool detector is a fake. No process starts except a
fake ``uv`` script in ``tmp_path``.
"""

from __future__ import annotations

import json
import shlex
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_plugin_manifest import valid_manifest  # noqa: E402
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_experiment_app,
    login,
)
from tests.unit.test_web_integration_tools import FakeDetector  # noqa: E402
from tests.unit.test_web_plugins import Tools, _notebook  # noqa: E402
from tests.unit.test_web_runs_support import make_engine  # noqa: E402

from omrs.transports.api.routes.experiment_editor import EDITOR_REASONS  # noqa: E402
from omrs.transports.api.tool_environment import ToolStatus  # noqa: E402


@dataclass
class Env:
    client: TestClient
    parts: Any
    tools: Tools
    manifest: Path
    found: Path
    gate: Path

    @property
    def runtime(self) -> Any:
        return self.client.app.state.runtime  # type: ignore[attr-defined]

    def register(self, exe: Path) -> Any:
        body = {"manifest_path": str(self.manifest), "executable_path": str(exe), "approved": True}
        return self.client.post("/v1/plugins", json=body, headers=ORIGIN)

    def hold(self, *, tool: bool = True) -> None:
        """Start a held job on the server loop: a marimo tool job, or an extras job."""
        script = self.found.parent.parent / "uv"
        gate = shlex.quote(str(self.gate))
        script.write_text(f"#!/bin/sh\nwhile [ ! -f {gate} ]; do sleep 0.02; done\n")
        script.chmod(0o755)
        job = self.runtime.installs
        if tool:
            start = lambda: job.start_tool("marimo", [str(script)], lambda: True)  # noqa: E731
        else:
            start = lambda: job.start("chroma", str(script), ["chromadb"])  # noqa: E731
        self.client.portal.call(start)

    def release(self) -> None:
        self.gate.touch()
        deadline = time.monotonic() + 10
        while self.runtime.installs.running:
            assert time.monotonic() < deadline
            time.sleep(0.02)


@pytest.fixture
def env(tmp_path: Path, effective_settings: Any) -> Iterator[Env]:
    tools = Tools(tmp_path)
    parts = build_experiment_app(
        tmp_path, make_engine(effective_settings), effective_settings, plugins_factory=tools.factory
    )
    manifest = tmp_path / "ws" / "plugins" / "marimo.json"
    manifest.parent.mkdir(parents=True)
    data = valid_manifest()
    data["plugin_id"] = "marimo"
    manifest.write_text(json.dumps(data))
    found = tmp_path / "uv-bin" / "fakeedit"  # a folder that is not on the server PATH
    found.parent.mkdir()
    found.write_text("#!/bin/sh\n")
    found.chmod(0o755)
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        environment = Env(client, parts, tools, manifest, found, tmp_path / "gate")
        environment.runtime.tools = FakeDetector(
            ToolStatus("needs-jupytext", uv="/x/uv", version="0.25.1", executable=str(found))
        )
        yield environment
        environment.gate.touch()


# ── 5.1 Registration and the plugin list ─────────────────────────────────


def test_the_found_executable_registers_although_its_folder_is_not_on_path(env: Env) -> None:
    assert env.found.parent not in env.tools.host.executable_dirs  # type: ignore[union-attr]
    response = env.register(env.found)
    assert response.status_code == 201, response.text
    assert response.json()["plugin"]["executable"] == str(env.found)


def test_another_file_in_that_folder_is_refused_and_recorded_nowhere(env: Env) -> None:
    other = env.found.parent / "other"
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)
    assert env.register(other).status_code == 403
    sibling = env.found.parent / "sub" / "fakeedit"
    sibling.parent.mkdir()
    sibling.write_text("#!/bin/sh\n")
    assert env.register(sibling).status_code == 403
    assert env.client.get("/v1/plugins").json()["plugins"] == []


def test_the_plugin_list_gives_the_found_executable(env: Env) -> None:
    body = env.client.get("/v1/plugins").json()
    assert body["detected_executables"] == {"marimo": str(env.found)}


def test_the_plugin_list_gives_nothing_when_marimo_is_not_installed(env: Env) -> None:
    env.runtime.tools.status = ToolStatus("not-installed", uv="/x/uv")
    assert env.client.get("/v1/plugins").json()["detected_executables"] == {}
    response = env.register(env.found)
    assert response.status_code == 403


def test_the_install_hint_names_the_marimo_card_before_the_command(env: Env) -> None:
    hint = env.client.get("/v1/plugins").json()["install_hint"]
    assert "marimo card on the Integrations page" in hint
    assert hint.index("Integrations page") < hint.index("uv tool install")
    assert 'uv tool install "marimo>=0.25.1,<0.26.0" --with jupytext' in hint
    assert "never installs" not in hint


# ── 5.2 No editor opens during a marimo job ──────────────────────────────


def _open(env: Env, context_id: str) -> Any:
    body = {"notebook": "notebooks/study.py", "experiment_context": context_id, "consent": True}
    return env.client.post("/v1/plugins/marimo/editors", json=body, headers=ORIGIN)


def test_the_code_editor_refuses_while_a_marimo_job_runs(env: Env) -> None:
    assert env.register(env.found).status_code == 201
    context_id, _ = _notebook(env.parts, env.client)
    before = env.client.get("/v1/credentials").json()["credentials"]
    env.hold()
    response = _open(env, context_id)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["reason"] == "tool_install_running"
    assert body["message"] == EDITOR_REASONS["tool_install_running"]
    assert env.client.get("/v1/credentials").json()["credentials"] == before
    assert env.tools.launcher.started == []
    env.release()


def test_an_extras_job_does_not_block_the_code_editor(env: Env) -> None:
    assert env.register(env.found).status_code == 201
    context_id, _ = _notebook(env.parts, env.client)
    env.hold(tool=False)
    response = _open(env, context_id)
    assert response.status_code == 201, response.text
    env.client.delete(f"/v1/plugin-editors/{response.json()['launch_id']}", headers=ORIGIN)
    env.release()
