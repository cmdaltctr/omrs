"""Shared helpers for the Library "Open in marimo" route tests (open-experiment-in-marimo).

Not a test module. It starts the app with the production plugin host
(``PluginRegistry`` + ``SubprocessProbeRunner`` and ``OwnedProcessLauncher``)
around the fake marimo executable from the launcher tests. Real marimo is
never started. The project gets a fake ``.venv`` whose Python version
matches the fake editor's interpreter, so the version check passes.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_plugin_marimo_manifest import MANIFEST  # noqa: E402
from tests.unit.test_process_launcher_support import free_port, make_fake_editor  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_experiment_library_support import FIRST, make_project  # noqa: E402

from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.lifespan import WebConfig  # noqa: E402
from omrs.transports.api.security import AccessPolicy  # noqa: E402

PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"


@dataclass
class EditorApp:
    """One running app with a registered fake marimo and an added project."""

    client: TestClient
    policy: AccessPolicy
    app: Any
    root: Path
    exe: Path
    project_id: str

    @property
    def folder(self) -> Path:
        """The first experiment folder of the project."""
        return self.root / "experiments" / FIRST

    @property
    def host(self) -> Any:
        """The plugin host of the running app."""
        return self.app.state.runtime.plugins

    def url(self, folder: str = FIRST, project_id: str | None = None) -> str:
        """Return the open route for *folder*."""
        project = project_id or self.project_id
        return f"/v1/experiment-projects/{project}/experiments/{folder}/editor"

    def open(self, folder: str = FIRST, **body: Any) -> Any:
        """Send a consented open request (``body`` overrides the JSON body)."""
        return self.client.post(self.url(folder), json=body or {"consent": True}, headers=ORIGIN)


def make_venv(root: Path, version: str = PYTHON) -> Path:
    """Write a minimal POSIX virtual environment at ``<root>/.venv``."""
    venv = root / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "lib" / f"python{version}" / "site-packages").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(f"home = /usr/bin\nversion_info = {version}.0\n")
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    return venv


def tree_digest(folder: Path) -> dict[str, str]:
    """Return the SHA-256 of every file below *folder*, by relative path."""
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def register_marimo(client: TestClient, manifest: Path, exe: Path) -> None:
    """Register *manifest* with *exe* and run a compatibility check."""
    created = client.post(
        "/v1/plugins",
        json={"manifest_path": str(manifest), "executable_path": str(exe), "approved": True},
        headers=ORIGIN,
    )
    assert created.status_code == 201, created.text
    checked = client.post("/v1/plugins/marimo/recheck", headers=ORIGIN)
    assert checked.json()["plugin"]["launchable"] is True, checked.text


@contextmanager
def editor_app(
    tmp_path: Path,
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    register: bool = True,
    venv: bool = True,
    ports: tuple[int, ...] | None = None,
) -> Iterator[EditorApp]:
    """Start the app, sign in, register the fake marimo and add one project."""
    exe = make_fake_editor(tmp_path / "tool")
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    root = make_project(tmp_path)
    if venv:
        make_venv(root)
    config = WebConfig(
        workspace=tmp_path / "ws",
        host="127.0.0.1",
        port=8765,
        static_dir=None,
        plugin_ports=ports or (free_port(),),
    )
    policy = AccessPolicy.for_launch(config.host, config.port)
    engine = make_engine(lance_store(tmp_path), settings)
    app = create_app(config, policy=policy, engine_factory=lambda: engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        if register:
            register_marimo(client, MANIFEST, exe)
        added = client.post(
            "/v1/experiment-projects", json={"path": str(root), "name": "OMRS"}, headers=ORIGIN
        )
        assert added.status_code == 201, added.text
        yield EditorApp(client, policy, app, root, exe, added.json()["project"]["project_id"])
