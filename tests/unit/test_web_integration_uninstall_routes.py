"""The uninstall route and the uninstall fields of ``GET /v1/integrations`` (task 2.2).

Each test replaces the runtime's install detection with a fake ``uv tool``
install whose ``uv`` is a shell script in ``tmp_path``, and the installed
package map with a fixed one. The script records its arguments, so a refused
request can show it started no process. No test removes a package.
"""

from __future__ import annotations

import json
import os
import shlex
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

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

import omrs.capabilities as capabilities  # noqa: E402
from omrs.transports.api.install_environment import InstallEnvironment  # noqa: E402

STATUS = "/v1/integrations/install"
INSTALLED: dict[str, frozenset[str]] = {
    "omrs": frozenset({"chromadb", "rank-bm25"}),
    "chromadb": frozenset(),
    "llama-index-vector-stores-chroma": frozenset(),
    "rank-bm25": frozenset(),
    "sentence-transformers": frozenset(),
    "transformers": frozenset(),
    "llama-index-llms-anthropic": frozenset(),
}


def url(extra: str) -> str:
    return f"/v1/integrations/{quote(extra, safe='')}/uninstall"


class Harness:
    """A logged-in client, its policy and the runtime's install job."""

    def __init__(self, client: TestClient, policy: Any, tmp_path: Path) -> None:
        self.client = client
        self.policy = policy
        self.tmp_path = tmp_path
        self.job = client.app.state.runtime.installs  # type: ignore[attr-defined]
        self.job.python = "/env/bin/python"
        self.job.installed = lambda: INSTALLED
        self.argv = tmp_path / "argv.txt"
        self.gate = tmp_path / "gate"
        self.install_as()

    def install_as(
        self, install_type: str = "uv-tool", *, uv: bool = True, body: str = "", check: str = ""
    ) -> None:
        """Make the server look like *install_type*, with a fake ``uv`` running *body*."""
        script = self.tmp_path / "bin" / "uv"
        script.parent.mkdir(parents=True, exist_ok=True)
        out = shlex.quote(str(self.argv))
        script.write_text(
            f'#!/bin/sh\nif [ "$2" = check ]; then\n{check or "exit 0"}\nfi\n'
            f'printf "%s\\n" "$@" > {out}\n{body}\n',
            encoding="utf-8",
        )
        script.chmod(0o755)
        env = InstallEnvironment(
            install_type=install_type,  # type: ignore[arg-type]
            receipt_extras=("web", "hybrid") if install_type == "uv-tool" else (),
            receipt_source="~/src/omrs" if install_type == "uv-tool" else None,
            uv=str(script) if uv else None,
        )
        self.job.detect = lambda: env

    def held(self) -> str:
        """A ``uv`` body that waits for the gate file, then succeeds."""
        return f"while [ ! -f {shlex.quote(str(self.gate))} ]; do sleep 0.02; done\nexit 0"

    def settle(self) -> dict[str, Any]:
        """Poll the status route until the job leaves ``running``."""
        deadline = time.monotonic() + 10
        while True:
            install = self.client.get(STATUS).json()["install"]
            if install["state"] != "running":
                return install
            assert time.monotonic() < deadline, install
            time.sleep(0.02)

    def entries(self) -> dict[str, dict[str, Any]]:
        response = self.client.get("/v1/integrations")
        assert response.status_code == 200, response.text
        return {entry["id"]: entry for entry in response.json()["integrations"]}

    def ran(self) -> list[str] | None:
        """The ``uv pip uninstall`` argument list, or ``None`` when no process ran."""
        if not self.argv.exists():
            return None
        return self.argv.read_text(encoding="utf-8").splitlines()


Make = Callable[..., Harness]


@pytest.fixture
def make(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Make]:
    """Build a harness whose Engine has *overrides*; every probe reports installed."""
    monkeypatch.setattr(capabilities, "module_installed", lambda name: True)
    monkeypatch.setattr("omrs.core.vectordb.registry.availability", lambda name: "available")
    clients: list[TestClient] = []

    def build(**overrides: Any) -> Harness:
        engine = make_engine(lance_store(tmp_path), effective_settings(**overrides))
        app, policy = build_app(tmp_path, engine)
        client = TestClient(app, base_url=BASE)
        clients.append(client)
        client.__enter__()
        login(client, policy)
        return Harness(client, policy, tmp_path)

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def harness(make: Make) -> Harness:
    return make()


def save(values: dict[str, Any]) -> None:
    """Write ``omrs.jsonc`` into the isolated config folder the conftest set."""
    folder = Path(os.environ["OMRS_CONFIG_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "omrs.jsonc").write_text(json.dumps(values), encoding="utf-8")


# ── Catalogue fields ─────────────────────────────────────────────────────


def test_an_installed_unused_extra_is_uninstallable(harness: Harness) -> None:
    entry = harness.entries()["chroma"]
    assert entry["uninstallable"] is True and entry["uninstall_reason"] is None
    assert entry["uninstall_setting"] is None
    assert entry["removes"] == ["chromadb", "llama-index-vector-stores-chroma"]
    assert entry["keeps"] == []
    assert entry["lasting_uninstall_command"] is None


def test_an_extra_in_the_receipt_carries_the_lasting_command(harness: Harness) -> None:
    entry = harness.entries()["hybrid"]
    assert entry["uninstallable"] is True and entry["removes"] == ["rank-bm25"]
    assert entry["lasting_uninstall_command"] == (
        'uv tool install --reinstall "omrs[web] @ ~/src/omrs"'
    )


def test_base_and_web_entries_list_nothing(harness: Harness) -> None:
    entries = harness.entries()
    for name in ("web", "magika", "pdf-inspector", "llamacpp", "openrouter"):
        entry = entries[name]
        assert entry["uninstallable"] is False, name
        assert entry["uninstall_reason"] == "not-uninstallable-here", name
        assert entry["removes"] == [] and entry["keeps"] == [], name
        assert entry["lasting_uninstall_command"] is None, name


def test_a_shared_package_is_kept_and_not_removed(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = {**INSTALLED, "some-tool": frozenset({"chromadb"})}
    harness.job.installed = lambda: shared
    harness.install_as(body="exit 0")
    entry = harness.entries()["chroma"]
    assert entry["removes"] == ["llama-index-vector-stores-chroma"]
    assert entry["keeps"] == ["chromadb"]
    assert harness.client.post(url("chroma"), headers=ORIGIN).status_code == 202
    harness.settle()
    assert harness.ran() == [
        "pip",
        "uninstall",
        "--python",
        "/env/bin/python",
        "llama-index-vector-stores-chroma",
    ]


# ── Starting an uninstall ────────────────────────────────────────────────


def test_uninstall_answers_202_then_reports_restart_needed(harness: Harness) -> None:
    harness.install_as(body="echo Uninstalled 2 packages")
    response = harness.client.post(url("chroma"), headers=ORIGIN)
    assert response.status_code == 202, response.text
    install = response.json()["install"]
    assert install["state"] == "running" and install["action"] == "uninstall"
    assert install["extra"] == "chroma"
    install = harness.settle()
    assert install["state"] == "succeeded" and install["action"] == "uninstall"
    assert install["output"] == ["Uninstalled 2 packages"]
    assert harness.ran() == [
        "pip",
        "uninstall",
        "--python",
        "/env/bin/python",
        "chromadb",
        "llama-index-vector-stores-chroma",
    ]
    entry = harness.entries()["chroma"]
    assert entry["availability"] == "restart-needed"
    assert entry["uninstallable"] is False and entry["uninstall_reason"] == "not-installed"
    assert entry["removes"] == [] and entry["keeps"] == []
    again = harness.client.post(url("chroma"), headers=ORIGIN)
    assert again.status_code == 409 and again.json()["reason"] == "not-installed"


def test_a_failed_check_fails_the_uninstall(harness: Harness) -> None:
    harness.install_as(body="exit 0", check="echo 'x 1.0 requires chromadb'\nexit 1")
    assert harness.client.post(url("chroma"), headers=ORIGIN).status_code == 202
    install = harness.settle()
    assert install["state"] == "failed" and install["reason"] == "check-failed"
    assert install["action"] == "uninstall"
    assert harness.entries()["chroma"]["availability"] == "available"


def test_an_extra_whose_packages_all_stay_is_409_nothing_to_remove(harness: Harness) -> None:
    # lancedb lists both torch packages under its own extras, and D1 keeps them.
    shared = {"sentence-transformers", "transformers"}
    harness.job.installed = lambda: {**INSTALLED, "lancedb": frozenset(shared)}
    entry = harness.entries()["torch"]
    assert entry["uninstallable"] is False
    assert entry["uninstall_reason"] == "nothing-to-remove"
    assert entry["removes"] == [] and set(entry["keeps"]) == shared
    response = harness.client.post(url("torch"), headers=ORIGIN)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["reason"] == "nothing-to-remove" and "setting" not in body
    assert harness.ran() is None


def test_an_effective_setting_in_use_is_409_with_the_setting(make: Make) -> None:
    harness = make(rerank_backend="torch")
    entry = harness.entries()["torch"]
    assert entry["uninstall_reason"] == "in-use"
    assert entry["uninstall_setting"] == "retrieval.rerank_backend"
    response = harness.client.post(url("torch"), headers=ORIGIN)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["reason"] == "in-use" and body["setting"] == "retrieval.rerank_backend"
    assert "retrieval.rerank_backend" in body["message"]
    assert harness.ran() is None


@pytest.mark.parametrize(
    ("extra", "saved", "setting"),
    [
        ("chroma", {"vector_store": "chroma"}, "vector_store"),
        ("anthropic", {"answer": {"verify_provider": "anthropic"}}, "answer.verify_provider"),
    ],
)
def test_a_saved_setting_in_use_is_409(
    harness: Harness, extra: str, saved: dict[str, Any], setting: str
) -> None:
    save(saved)
    response = harness.client.post(url(extra), headers=ORIGIN)
    assert response.status_code == 409, response.text
    assert response.json()["reason"] == "in-use" and response.json()["setting"] == setting
    assert harness.ran() is None


@pytest.mark.parametrize("extra", ["web", "magika", "pdf-inspector", "llamacpp", "openrouter"])
def test_base_entries_and_web_are_409(harness: Harness, extra: str) -> None:
    response = harness.client.post(url(extra), headers=ORIGIN)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["reason"] == "not-uninstallable-here" and body["message"]
    assert "setting" not in body
    assert harness.ran() is None


@pytest.mark.parametrize("extra", ["chroma; rm -rf ~", "no-such-extra"])
def test_an_unknown_extra_is_404_and_starts_nothing(harness: Harness, extra: str) -> None:
    response = harness.client.post(url(extra), headers=ORIGIN)
    assert response.status_code == 404, response.text
    assert harness.ran() is None
    assert harness.client.get(STATUS).json()["install"]["state"] == "idle"


@pytest.mark.parametrize(
    ("install_type", "uv", "reason"),
    [
        ("checkout", True, "not-uv-tool"),
        ("other", True, "not-uv-tool"),
        ("uv-tool", False, "uv-not-found"),
    ],
)
def test_an_install_the_app_cannot_change_is_409(
    harness: Harness, install_type: str, uv: bool, reason: str
) -> None:
    harness.install_as(install_type, uv=uv)
    assert harness.entries()["hybrid"]["uninstall_reason"] == reason
    response = harness.client.post(url("hybrid"), headers=ORIGIN)
    assert response.status_code == 409 and response.json()["reason"] == reason
    assert harness.ran() is None


def test_a_running_job_is_409_and_shows_in_the_catalogue(harness: Harness) -> None:
    harness.install_as(body=harness.held())
    assert harness.client.post(url("hybrid"), headers=ORIGIN).status_code == 202
    assert harness.entries()["chroma"]["uninstall_reason"] == "install-running"
    second = harness.client.post(url("chroma"), headers=ORIGIN)
    assert second.status_code == 409 and second.json()["reason"] == "install-running"
    install = harness.client.get(STATUS).json()["install"]
    assert install["extra"] == "hybrid" and install["action"] == "uninstall"
    harness.gate.write_text("", encoding="utf-8")
    assert harness.settle()["state"] == "succeeded"
    assert harness.ran() == ["pip", "uninstall", "--python", "/env/bin/python", "rank-bm25"]


# ── Access and contract ──────────────────────────────────────────────────


def test_a_bearer_credential_is_refused_and_starts_nothing(harness: Harness) -> None:
    harness.client.cookies.clear()
    header = bearer(harness.policy, "read", "graph", "run")
    assert harness.client.post(url("chroma"), headers={**ORIGIN, **header}).status_code == 403
    assert harness.client.post(url("chroma"), headers=ORIGIN).status_code == 401
    assert harness.ran() is None


def test_uninstall_responses_conform(harness: Harness) -> None:
    check = ContractChecker()
    harness.install_as(body="echo done")
    check.check(harness.client.get("/v1/integrations"), 200)
    check.check(harness.client.post(url("no-such"), headers=ORIGIN), 404)
    check.check(harness.client.post(url("web"), headers=ORIGIN), 409)
    save({"vector_store": "chroma"})
    check.check(harness.client.post(url("chroma"), headers=ORIGIN), 409)
    check.check(harness.client.post(url("hybrid"), headers=ORIGIN), 202)
    harness.settle()
    check.check(harness.client.get(STATUS), 200)
    check.check(harness.client.get("/v1/integrations"), 200)
    harness.client.cookies.clear()
    read = bearer(harness.policy, "read")
    check.check(harness.client.post(url("hybrid"), headers={**ORIGIN, **read}), 403)
    assert "uninstallIntegration" in check.operations
    assert "uninstallIntegration" in FAMILIES["integration_install"]
