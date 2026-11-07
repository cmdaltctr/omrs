"""The install path of the optional ``pypdfium2`` reader (change page-routing-panel, task 3.5).

The Page routing panel's Install button starts the existing extra install job
for ``pdf-pypdfium2`` (design D8). These tests pin that the extra is allowed:
``install_reason`` lets it through, the install route answers 202 on a fake
``uv tool`` install, and ``GET /v1/integrations`` offers the button on a
``uv tool`` install and the ``not-uv-tool`` reason on a checkout. The reader is
reported missing by a patched probe, so no test depends on what is installed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit import test_web_integration_install_routes as routes  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_app,
    lance_store,
    login,
    make_engine,
)

import omrs.capabilities as capabilities  # noqa: E402
from omrs.transports.api.install_environment import (  # noqa: E402
    InstallEnvironment,
    install_reason,
)

EXTRA = "pdf-pypdfium2"
INSTALL = f"/v1/integrations/{EXTRA}/install"
PACKAGES = ["pypdfium2>=4.0.0"]
TOOL = InstallEnvironment(install_type="uv-tool", uv="/bin/uv")


def test_install_reason_lets_the_extra_through_on_a_uv_tool_install() -> None:
    assert install_reason(EXTRA, "not-installed", PACKAGES, TOOL) is None


@pytest.fixture
def harness(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> Iterator[routes.Harness]:
    real = capabilities.pdf_reader_installed
    monkeypatch.setattr(
        capabilities,
        "pdf_reader_installed",
        lambda name: False if name == "pypdfium2" else real(name),
    )
    monkeypatch.setattr("omrs.core.vectordb.registry.availability", lambda name: "absent")
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield routes.Harness(client, policy, tmp_path)


def test_the_catalogue_offers_the_install_on_a_uv_tool_install(harness: routes.Harness) -> None:
    harness.install_as("uv-tool")
    entry = harness.entries()[EXTRA]
    assert entry["availability"] == "not-installed"
    assert entry["installable"] is True and entry["install_reason"] is None
    assert entry["packages"] == PACKAGES


def test_the_catalogue_gives_the_reason_on_a_checkout(harness: routes.Harness) -> None:
    harness.install_as("checkout")
    entry = harness.entries()[EXTRA]
    assert entry["installable"] is False and entry["install_reason"] == "not-uv-tool"


def test_the_install_route_answers_202(harness: routes.Harness) -> None:
    harness.install_as("uv-tool", body="echo Installed 1 package")
    response = harness.client.post(INSTALL, headers=ORIGIN)
    assert response.status_code == 202, response.text
    assert response.json()["install"]["extra"] == EXTRA
    assert harness.settle()["state"] == "succeeded"
