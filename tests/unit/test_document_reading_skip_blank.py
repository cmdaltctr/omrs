"""``ocr_skip_blank_pages`` on ``/v1/settings/document-reading`` (page-routing-panel, task 3.1).

The route reuses the harness of ``test_web_document_reading.py``. Each test
follows a scenario of the ``workspace-settings`` and ``settings-file`` deltas.
Responses are validated against ``openapi.yaml``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit import test_web_document_reading as reading  # noqa: E402
from tests.unit.test_web_document_reading import URL, Harness, put, refused, rows  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.config import provenance  # noqa: E402
from omrs.config.settings_file import file_revision  # noqa: E402
from omrs.config.user_config import parse_jsonc  # noqa: E402

KEY = "ocr_skip_blank_pages"
ENV = "OCR_SKIP_BLANK_PAGES"

# The harness and the signed-in client of the Document reading route tests.
harness = reading.harness
client = reading.client


@pytest.fixture(autouse=True)
def _no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV, raising=False)


def test_read_lists_the_switch_with_default_true(harness: Harness, client: TestClient) -> None:
    harness.launch()

    body = ContractChecker().check(client.get(URL), 200)

    assert rows(body)[KEY] == {
        "key": KEY,
        "value": True,
        "saved": None,
        "source": "default",
        "locked": False,
        "lock_reason": None,
        "restart_pending": False,
        "default": True,
    }


def test_put_false_writes_the_key_keeps_comments_and_shows_restart(
    harness: Harness, client: TestClient
) -> None:
    harness.write('// mine\n{ "ocr_routing_unit": "page" }\n')
    harness.launch()

    response = put(client, {KEY: False}, file_revision(harness.folder))

    body = ContractChecker().check(response, 200)
    assert parse_jsonc(harness.text())[KEY] is False
    assert harness.text().startswith("// mine\n")
    row = rows(body)[KEY]
    assert (row["value"], row["saved"], row["restart_pending"]) == (True, False, True)


def test_put_text_is_refused_and_the_file_stays(harness: Harness, client: TestClient) -> None:
    harness.launch()

    refused(put(client, {KEY: "no"}), 400, f"{KEY}: The value must be true or false.")

    assert harness.text() == ""


def test_put_null_removes_the_key(harness: Harness, client: TestClient) -> None:
    harness.write('{ "ocr_skip_blank_pages": false }\n')
    harness.launch()

    response = put(client, {KEY: None}, file_revision(harness.folder))

    assert response.status_code == 200, response.text
    assert KEY not in parse_jsonc(harness.text())


def test_the_environment_locks_the_switch(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, "false")
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    harness.launch()

    row = rows(client.get(URL).json())[KEY]

    assert (row["value"], row["locked"], row["source"]) == (False, True, "env")
    assert row["lock_reason"] == f"Remove {ENV} from the environment or .env to edit it here."
