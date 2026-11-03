"""The ``pdf_readers`` block on ``GET /v1/integrations``.

Change ordered-reader-and-ocr-lists, task 4.2. The probes are faked, and the
response is validated against ``openapi.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs import capabilities  # noqa: E402

OPTIONS = {
    "liteparse": None,
    "pdf_inspector": None,
    "pypdf": None,
    "pypdfium2": "The package 'pypdfium2' is not installed.",
}


@pytest.fixture
def client(tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(capabilities, "pdf_reader_options", lambda: dict(OPTIONS))
    settings = effective_settings(pdf_readers=("pdf_inspector", "pypdfium2", "pypdf"))
    app, policy = build_app(tmp_path, make_engine(lance_store(tmp_path), settings))
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        yield test_client


def _readers(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/v1/integrations")
    assert response.status_code == 200, response.text
    return {item["name"]: item for item in response.json()["pdf_readers"]}


def test_one_row_per_registered_reader_with_the_contract_fields(client: TestClient) -> None:
    readers = _readers(client)
    assert list(readers) == ["pdf_inspector", "pypdfium2", "pypdf", "liteparse"]
    assert all(
        set(item) == {"name", "installed", "extra", "fix_command", "used_by"}
        for item in readers.values()
    )


def test_installed_state_and_the_fix_command_of_a_missing_reader(client: TestClient) -> None:
    readers = _readers(client)
    assert readers["pypdf"]["installed"] is True and readers["pypdf"]["fix_command"] is None
    missing = readers["pypdfium2"]
    assert (missing["installed"], missing["extra"]) == (False, "pdf-pypdfium2")
    assert "pdf-pypdfium2" in missing["fix_command"]


def test_used_by_lines_follow_the_host_list(client: TestClient) -> None:
    readers = _readers(client)
    assert readers["pdf_inspector"]["used_by"] == ["First in Settings > Document reading"]
    assert readers["pypdfium2"]["used_by"] == ["Second in Settings > Document reading"]
    assert readers["pypdf"]["used_by"] == ["Third in Settings > Document reading"]
    assert readers["liteparse"]["used_by"] == []


def test_the_block_conforms_to_the_contract(client: TestClient) -> None:
    body = ContractChecker().check(client.get("/v1/integrations"), 200)
    assert len(body["pdf_readers"]) == 4
