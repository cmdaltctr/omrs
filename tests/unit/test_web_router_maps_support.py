"""Shared harness for the decision model and router route tests (task 4.1).

Not a test module. The app is built without its lifespan, so no Engine runs
and nothing contacts a model. A temporary config folder replaces the real one;
no test reads ``~/.config/omrs``. A fake profile catalogue stands in for the
workspace.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import BASE, ORIGIN, login  # noqa: E402

from omrs.config.settings_file import file_revision  # noqa: E402
from omrs.config.user_config import parse_jsonc  # noqa: E402
from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.lifespan import WebConfig  # noqa: E402
from omrs.transports.api.security import AccessPolicy  # noqa: E402

#: A file with one local and one hosted model, and two routers.
FILE = """{
  // decision models
  "decision_models": {
    "clef-local": { "kind": "llamacpp", "address": "http://127.0.0.1:9100",
                    "model": "clef-flash-q8_0", "images": true },
    "jev": { "kind": "typesafe", "address": "https://api.example.test",
             "model": "jev", "images": true, "key": "env://ROUTER_TEST_KEY" },
    "cf": { "kind": "cloudflare", "address": "https://cf.example.test", "model": "clef" }
  },
  "document_routers": {
    "handwriting": { "model": "clef-local", "question": "Does the text match?",
                     "threshold": 0.172, "images": true },
    "hosted": { "model": "jev", "question": "Does the text match?", "threshold": 0.21,
                "images": true }
  }
}
"""


class FakeCatalogue:
    """Saved user profiles: ``{title: router name}`` on one Read document step each."""

    def __init__(self, routers: Mapping[str, str | None], *, broken: bool = False) -> None:
        self.routers = dict(routers)
        self.broken = broken

    def list_profiles(self) -> list[dict[str, Any]]:
        if self.broken:
            raise RuntimeError("database is locked")
        return [{"profile_id": f"p{i}", "title": t} for i, t in enumerate(self.routers)]

    def slot_document(self, profile_id: str, slot: str) -> dict[str, Any] | None:
        if slot != "ingest":
            return None
        title = list(self.routers)[int(profile_id[1:])]
        params = {"document_router": self.routers[title]} if self.routers[title] else {}
        return {"nodes": [{"id": "read", "operation": "read.document", "params": params}]}


class Harness:
    """The app, its policy and the config folder."""

    def __init__(self, app: Any, policy: AccessPolicy, folder: Path) -> None:
        self.app = app
        self.policy = policy
        self.folder = folder

    @property
    def path(self) -> Path:
        return self.folder / "omrs.jsonc"

    def write(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8") if self.path.exists() else ""

    def data(self) -> Any:
        return parse_jsonc(self.text())

    def revision(self) -> str:
        return file_revision(self.folder)

    def profiles(self, catalogue: Any) -> None:
        """Start the fake profile service (the lifespan does not run)."""
        self.app.state.runtime = SimpleNamespace(profiles=SimpleNamespace(catalogue=catalogue))


def make_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    """Build the app over a temporary config folder (the test module's ``harness`` fixture)."""
    monkeypatch.delenv("ROUTER_TEST_KEY", raising=False)
    monkeypatch.delenv("DOCUMENT_ROUTER", raising=False)
    folder = tmp_path / "omrs-config"
    folder.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(folder))
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: None)
    return Harness(app, policy, folder)


def signed_in(harness: Harness) -> TestClient:
    """A signed-in client. It is not a context manager, so the lifespan never runs."""
    test_client = TestClient(harness.app, base_url=BASE)
    login(test_client, harness.policy)
    return test_client


def send(client: TestClient, method: str, url: str, body: Any = None) -> Any:
    """Send a request with the application Origin."""
    return client.request(method, url, json=body, headers=ORIGIN)


def refused(response: Any, status: int, reason: str | None = None) -> str:
    """Assert an error envelope with *status* and *reason*; return the message."""
    assert response.status_code == status, response.text
    body = response.json()
    assert body["status"] == "error"
    assert body.get("reason") == reason
    return body["message"]
