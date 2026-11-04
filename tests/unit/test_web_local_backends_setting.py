"""``ocr_local_backends`` on ``/v1/settings/document-reading`` (change local-ocr-backends, 6.4).

The route reuses the harness of ``test_web_document_reading.py``. Responses
are validated against ``openapi.yaml``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit import test_web_document_reading as reading  # noqa: E402
from tests.unit.test_web_document_reading import URL, Harness, put, refused, rows  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.integrations.pdf.local_ocr import registry  # noqa: E402

KEY = "ocr_local_backends"

# The harness and the signed-in client of the Document reading route tests.
harness = reading.harness
client = reading.client


def test_the_row_and_the_backend_options_conform(harness: Harness, client: TestClient) -> None:
    harness.launch()

    body = ContractChecker().check(client.get(URL), 200)

    row = rows(body)[KEY]
    assert (row["value"], row["default"], row["saved"]) == (
        ["pp-ocrv6-small"],
        ["pp-ocrv6-small"],
        None,
    )
    installed = registry.BACKENDS.installed("pp-ocrv6-small")
    assert body["local_ocr_backends"] == [
        {
            "name": "pp-ocrv6-small",
            "available": installed,
            "reason": None if installed else "Not installed.",
        }
    ]


def test_an_unknown_backend_is_refused_with_the_accepted_values(
    harness: Harness, client: TestClient
) -> None:
    harness.launch()

    message = refused(put(client, {KEY: ["nope"]}), 400)

    assert message.startswith(f"{KEY}: ")
    assert "pp-ocrv6-small" in message and "nope" not in message


def test_a_valid_list_is_saved(harness: Harness, client: TestClient) -> None:
    harness.launch()

    response = put(client, {KEY: ["pp-ocrv6-small"]})

    assert response.status_code == 200, response.text
    assert rows(response.json())[KEY]["saved"] == ["pp-ocrv6-small"]
