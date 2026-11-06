"""``ocr_local_cuts`` on ``/v1/settings/document-reading`` (change local-ocr-per-backend-cuts, 5.1).

The route reuses the harness of ``test_web_document_reading.py``. Each test
follows a scenario of the ``workspace-settings`` delta. Responses are validated
against ``openapi.yaml``. No message may hold a submitted value.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit import test_web_document_reading as reading  # noqa: E402
from tests.unit.test_web_document_reading import URL, Harness, put, refused, rows  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import ContractChecker  # noqa: E402

from omrs.config.rules import DOCUMENT_READING_KEYS, document_reading_problem  # noqa: E402
from omrs.config.user_config import parse_jsonc  # noqa: E402
from omrs.core import reading_parts  # noqa: E402

KEY = "ocr_local_cuts"
OLD_KEY = "ocr_local_min_confidence"
# A comment on its own line, a blank line, the old key's own comment, the old
# key, and a comment after another member. The old key's own comment goes with
# it (change cuts-follow-ups); the other two survive a write.
FILE_WITH_OLD_KEY = (
    "{\n"
    "  // keep this comment\n"
    "\n"
    "  // old single cut\n"
    f'  "{OLD_KEY}": 0.9,\n'
    '  "ocr_routing_unit": "page" // keep this one too\n'
    "}\n"
)

# The harness and the signed-in client of the Document reading route tests.
harness = reading.harness
client = reading.client


def _revision(client: TestClient) -> str:
    return client.get(URL).json()["revision"]


# ── Read ─────────────────────────────────────────────────────────────────


def test_the_cuts_entry_is_listed_with_its_default(harness: Harness, client: TestClient) -> None:
    harness.launch()

    body = ContractChecker().check(client.get(URL), 200)

    assert rows(body)[KEY] == {
        "key": KEY,
        "value": {},
        "saved": None,
        "source": "default",
        "locked": False,
        "lock_reason": None,
        "restart_pending": False,
        "default": {},
    }


def test_each_backend_option_carries_its_default_cut(harness: Harness, client: TestClient) -> None:
    harness.launch()

    options = {option["name"]: option for option in client.get(URL).json()["local_ocr_backends"]}

    assert options["pp-ocrv6-small"]["default_cut"] == 0.92  # spec scenario "Read the cuts"
    for descriptor in reading_parts.LOCAL_OCR_BACKENDS:
        if descriptor.min_confidence is not None:
            assert options[descriptor.name]["default_cut"] == descriptor.min_confidence


def test_a_map_in_the_file_shows_as_saved_and_pending(harness: Harness, client: TestClient) -> None:
    harness.launch()
    harness.write('{ "ocr_local_cuts": {"indra": 0.95} }')

    row = rows(client.get(URL).json())[KEY]

    assert (row["value"], row["saved"], row["restart_pending"]) == ({}, {"indra": 0.95}, True)


def test_the_retired_key_is_named_when_the_file_holds_it(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE_WITH_OLD_KEY)
    harness.launch()

    body = ContractChecker().check(client.get(URL), 200)

    assert body["retired_keys"] == [OLD_KEY]


def test_no_retired_key_is_named_for_a_clean_file(harness: Harness, client: TestClient) -> None:
    harness.launch()

    assert client.get(URL).json()["retired_keys"] == []


def test_the_environment_locks_the_entry(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_LOCAL_CUTS", '{"indra": 0.96}')
    harness.launch()

    row = rows(client.get(URL).json())[KEY]

    assert (row["locked"], row["source"], row["value"]) == (True, "env", {"indra": 0.96})
    assert row["lock_reason"] == (
        "Remove OCR_LOCAL_CUTS from the environment or .env to edit it here."
    )
    before = harness.text()
    refused(put(client, {KEY: {"indra": 0.95}}), 409)
    assert harness.text() == before


# ── Write ────────────────────────────────────────────────────────────────


def test_a_save_writes_the_map_keeps_comments_and_removes_the_old_key(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE_WITH_OLD_KEY)
    harness.launch()

    response = put(client, {KEY: {"indra": 0.95}}, _revision(client))

    assert response.status_code == 200, response.text
    text = harness.text()
    assert parse_jsonc(text) == {KEY: {"indra": 0.95}, "ocr_routing_unit": "page"}
    assert "// keep this comment" in text and "// keep this one too" in text
    assert OLD_KEY not in text
    assert "// old single cut" not in text
    body = response.json()
    assert rows(body)[KEY]["saved"] == {"indra": 0.95}
    assert body["retired_keys"] == []


def test_null_removes_the_map_and_the_old_key(harness: Harness, client: TestClient) -> None:
    harness.write(f'{{ "{OLD_KEY}": 0.9, "{KEY}": {{"indra": 0.95}} }}')
    harness.launch()

    response = put(client, {KEY: None}, _revision(client))

    assert response.status_code == 200, response.text
    assert parse_jsonc(harness.text()) == {}


def test_a_save_that_does_not_set_the_cuts_keeps_the_old_key(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE_WITH_OLD_KEY)
    harness.launch()

    response = put(client, {"ocr_fallback_enabled": False}, _revision(client))

    assert response.status_code == 200, response.text
    assert OLD_KEY in harness.text()


def test_a_save_replaces_the_whole_map(harness: Harness, client: TestClient) -> None:
    harness.write('{ "ocr_local_cuts": {"indra": 0.95} }')
    harness.launch()

    response = put(client, {KEY: {"pp-ocrv6-small": 0.9}}, _revision(client))

    assert response.status_code == 200, response.text
    assert parse_jsonc(harness.text()) == {KEY: {"pp-ocrv6-small": 0.9}}


@pytest.mark.parametrize(
    ("value", "secret"),
    [
        ({"pp-ocrv6-small": 2}, "2"),  # above the range (spec scenario "Refused value")
        ({"pp-ocrv6-small": 1.37}, "1.37"),
        ({"pp-ocrv6-small": -0.25}, "0.25"),
        ({"pp-ocrv6-small": True}, "true"),
        ({"pp-ocrv6-small": "0.5"}, "0.5"),
        ({"zz-nope": 0.9}, "zz-nope"),  # not a backend a list can name
        (True, "true"),
        ([0.9], "0.9"),
    ],
)
def test_a_bad_map_is_refused_without_the_value_and_the_file_stays(
    harness: Harness, client: TestClient, value: Any, secret: str
) -> None:
    harness.write(FILE_WITH_OLD_KEY)
    harness.launch()
    before = harness.text()

    message = refused(put(client, {KEY: value}, _revision(client)), 400)

    assert message.startswith(f"{KEY}: ")
    assert secret.lower() not in message.lower()
    assert harness.text() == before
    assert not (harness.folder / "omrs.jsonc.tmp").exists()


def test_a_name_error_lists_the_accepted_backends(harness: Harness, client: TestClient) -> None:
    harness.launch()

    message = refused(put(client, {KEY: {"zz-nope": 0.9}}), 400)

    assert "pp-ocrv6-small" in message


def test_a_stale_revision_is_refused_and_the_file_stays(
    harness: Harness, client: TestClient
) -> None:
    harness.write(FILE_WITH_OLD_KEY)
    harness.launch()
    before = harness.text()

    refused(put(client, {KEY: {"indra": 0.95}}, "stale"), 409)

    assert harness.text() == before


def test_write_responses_conform_to_the_contract(harness: Harness, client: TestClient) -> None:
    harness.write(FILE_WITH_OLD_KEY)
    harness.launch()
    check = ContractChecker()

    check.check(put(client, {KEY: {"indra": 0.95}}, _revision(client)), 200)
    check.check(put(client, {KEY: {"indra": 3}}, _revision(client)), 400)
    check.check(put(client, {KEY: {"indra": 0.9}}, "stale"), 409)


# ── The page write rule, on its own ──────────────────────────────────────


def test_the_page_rule_covers_the_cuts_key() -> None:
    # The rule runs before the writer (update_refusal), so a bad map never reaches the file.
    assert KEY in DOCUMENT_READING_KEYS
    assert document_reading_problem(KEY, {"pp-ocrv6-small": 0.9}) is None
    assert document_reading_problem(KEY, None) is None  # null removes the key
    assert document_reading_problem(KEY, {"pp-ocrv6-small": 2}) is not None
    assert document_reading_problem(KEY, {"zz-nope": 0.9}) is not None
    assert document_reading_problem(KEY, True) is not None
