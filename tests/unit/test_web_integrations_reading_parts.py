"""The ``reading_parts`` block on ``GET /v1/integrations`` (change local-ocr-backends, task 6.2).

The block comes from ``reading_parts_health.py``. The response is validated
against ``openapi.yaml``.
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

from omrs.integrations.pdf import page_routing  # noqa: E402


@pytest.fixture
def client(tmp_path: Path, effective_settings: Any):
    settings = effective_settings(ocr_non_latin_routing="detect")
    app, policy = build_app(tmp_path, make_engine(lance_store(tmp_path), settings))
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        yield test_client


def test_the_block_conforms_to_the_contract(client: TestClient) -> None:
    page_routing.switch_local_tier_off("PanicException: lock poisoned")

    body = ContractChecker().check(client.get("/v1/integrations"), 200)

    parts = body["reading_parts"]
    assert [row["name"] for row in parts["local_ocr_backends"]] == ["pp-ocrv6-small"]
    assert parts["local_ocr_backends"][0]["off_reason"] == "PanicException: lock poisoned"
    rules = {row["name"]: row["enabled"] for row in parts["page_rules"]}
    assert rules == {"blank": True, "maths": True, "non_latin": True}
    assert parts["discovered_parts"] == []


def test_a_broken_discovered_part_row_conforms_with_its_name(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``DiscoveredPartHealth.name`` is a non-null string (review of PR #168, finding 6)."""
    from tests.unit.test_part_discovery_support import fake_parts_builder, run_discovery

    builder = fake_parts_builder(tmp_path, monkeypatch)
    build = next(builder)
    try:
        build("acmebroken", {"omrs.page_rules": {"acme": "{mod:desc}:RULE"}},
              {"desc": "import a_module_that_is_gone\n"})  # fmt: skip
        run_discovery()

        body = ContractChecker().check(client.get("/v1/integrations"), 200)
    finally:
        next(builder, None)

    (row,) = body["reading_parts"]["discovered_parts"]
    assert row["name"] == "acme"
    assert row["kind"] == "page_rule"
    assert "a_module_that_is_gone" in row["problem"]
