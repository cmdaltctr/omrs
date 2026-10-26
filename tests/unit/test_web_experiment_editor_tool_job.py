"""The Library refuses "Open in marimo" during a marimo job (install-marimo-from-integrations, 5.2).

The app runs the production plugin host around the fake marimo executable.
A fake ``uv`` script in ``tmp_path`` holds the job until the test releases
it. Real marimo is never started.
"""

from __future__ import annotations

import shlex
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_documents_support import ORIGIN  # noqa: E402
from tests.unit.test_web_experiment_editor_support import (  # noqa: E402
    EditorApp,
    editor_app,
    tree_digest,
)

from omrs.transports.api.routes.experiment_editor import EDITOR_REASONS  # noqa: E402

ANALYSIS = "# %%\nprint('hello')\n"


def _hold(env: EditorApp, tmp_path: Path, *, tool: bool) -> Path:
    gate = tmp_path / "gate"
    script = tmp_path / "held-uv"
    script.write_text(f"#!/bin/sh\nwhile [ ! -f {shlex.quote(str(gate))} ]; do sleep 0.02; done\n")
    script.chmod(0o755)
    job = env.app.state.runtime.installs
    if tool:
        env.client.portal.call(lambda: job.start_tool("marimo", [str(script)], lambda: True))
    else:
        env.client.portal.call(lambda: job.start("chroma", str(script), ["chromadb"]))
    return gate


def _release(env: EditorApp, gate: Path) -> None:
    gate.touch()
    deadline = time.monotonic() + 10
    while env.app.state.runtime.installs.running:
        assert time.monotonic() < deadline
        time.sleep(0.02)


def test_open_in_marimo_is_refused_while_a_marimo_job_runs(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        (env.folder / "analysis.py").write_text(ANALYSIS)
        before = tree_digest(env.folder)
        credentials = env.client.get("/v1/credentials").json()["credentials"]
        gate = _hold(env, tmp_path, tool=True)
        response = env.open()
        assert response.status_code == 409, response.text
        body = response.json()
        assert body["reason"] == "tool_install_running"
        assert body["message"] == EDITOR_REASONS["tool_install_running"]
        assert tree_digest(env.folder) == before
        assert env.host.editors.sessions() == []
        assert not (env.exe.parent / "record.json").exists()
        assert env.client.get("/v1/credentials").json()["credentials"] == credentials
        _release(env, gate)


def test_an_extras_job_does_not_block_open_in_marimo(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with editor_app(tmp_path, effective_settings(), monkeypatch) as env:
        gate = _hold(env, tmp_path, tool=False)
        response = env.open()
        assert response.status_code == 201, response.text
        env.client.delete(f"/v1/plugin-editors/{response.json()['launch_id']}", headers=ORIGIN)
        _release(env, gate)
