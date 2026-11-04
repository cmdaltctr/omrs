"""``GET`` and ``PUT /v1/settings/document-reading`` (document-reading-settings, task 1.7).

Each test follows a scenario of the ``workspace-settings`` and ``settings-file``
deltas, or a row of the design D10 error table. The app is built without its
lifespan, so no Engine runs. A temporary config folder replaces the real one;
no test reads ``~/.config/omrs``. The PDF reader probes are faked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import BASE, ORIGIN, bearer, login  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    ContractChecker,
)

from omrs import capabilities  # noqa: E402
from omrs.config import Settings, provenance  # noqa: E402
from omrs.config.rules import DOCUMENT_READING_KEYS, OLD_READING_KEYS  # noqa: E402
from omrs.config.settings_file import file_revision, read_settings_file  # noqa: E402
from omrs.config.user_config import parse_jsonc  # noqa: E402
from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.document_reading import reset_reader_in_use  # noqa: E402
from omrs.transports.api.lifespan import WebConfig  # noqa: E402
from omrs.transports.api.restart_snapshot import capture  # noqa: E402
from omrs.transports.api.routes.configuration import ConfigurationState  # noqa: E402
from omrs.transports.api.security import AccessPolicy  # noqa: E402

URL = "/v1/settings/document-reading"
OPTIONS = {"pypdf": None, "pypdfium2": "The package 'pypdfium2' is not installed."}
OLD_KEYS = tuple(old for olds in OLD_READING_KEYS.values() for old in olds)
VARIABLES = tuple(key.upper() for key in (*DOCUMENT_READING_KEYS, *OLD_KEYS)) + ("OCR_WORKERS_DIR",)
SUBMITTED = "zz-submitted-zz"


class Harness:
    """The app, its policy and the config folder."""

    def __init__(self, app: Any, policy: AccessPolicy, folder: Path, empty_env: Path) -> None:
        self.app = app
        self.policy = policy
        self.folder = folder
        self.empty_env = empty_env

    @property
    def path(self) -> Path:
        return self.folder / "omrs.jsonc"

    def write(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8") if self.path.exists() else ""

    def launch(self) -> None:
        self.app.state.configuration = ConfigurationState(
            launch_settings=Settings(_env_file=self.empty_env),
            snapshot=capture(read_settings_file(self.folder)),
            read_file=lambda: read_settings_file(self.folder),
        )


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    monkeypatch.setattr(capabilities, "pdf_reader_options", lambda: dict(OPTIONS))
    monkeypatch.setattr(capabilities, "resolve_pdf_reader", lambda settings: "pypdf")
    reset_reader_in_use()
    folder = tmp_path / "omrs-config"
    folder.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(folder))
    empty_env = tmp_path / "none.env"
    empty_env.write_text("", encoding="utf-8")
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: None)
    yield Harness(app, policy, folder, empty_env)
    reset_reader_in_use()


@pytest.fixture
def client(harness: Harness) -> TestClient:
    """A signed-in client. It is not a context manager, so the lifespan never runs."""
    test_client = TestClient(harness.app, base_url=BASE)
    login(test_client, harness.policy)
    return test_client


def rows(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in body["settings"]}


def put(client: TestClient, values: dict[str, Any], revision: str = "absent") -> Any:
    return client.put(URL, json={"values": values, "revision": revision}, headers=ORIGIN)


def refused(response: Any, status: int, message: str | None = None) -> str:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["status"] == "error"
    if message is not None:
        assert body["message"] == message
    return body["message"]


# ── Access ───────────────────────────────────────────────────────────────


def test_get_needs_the_read_scope(harness: Harness, client: TestClient) -> None:
    harness.launch()
    client.cookies.clear()
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=bearer(harness.policy, "run")).status_code == 403
    assert client.get(URL, headers=bearer(harness.policy, "read")).status_code == 200


def test_put_refuses_a_bearer_credential(harness: Harness, client: TestClient) -> None:
    harness.launch()
    client.cookies.clear()
    headers = {**ORIGIN, **bearer(harness.policy, "read", "run", "graph")}
    body = {"values": {"pdf_readers": ["pypdf"]}, "revision": "absent"}
    assert client.put(URL, json=body, headers=headers).status_code == 403
    assert harness.text() == ""


# ── Read ─────────────────────────────────────────────────────────────────


def test_read_the_section(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [row["key"] for row in body["settings"]] == list(DOCUMENT_READING_KEYS)
    assert body["pdf_readers"][0] == {"name": "auto", "available": True, "reason": None}
    assert isinstance(body["ocr"]["engines"], list)


def test_value_saved_but_not_yet_in_force(harness: Harness, client: TestClient) -> None:
    harness.write('{ "pdf_readers": ["pypdf"] }')
    harness.launch()
    harness.write('{ "pdf_readers": ["liteparse", "pypdf"] }')
    row = rows(client.get(URL).json())["pdf_readers"]
    assert (row["value"], row["saved"], row["restart_pending"]) == (
        ["pypdf"],
        ["liteparse", "pypdf"],
        True,
    )


def test_blank_saved_fallback_shows_as_not_set(harness: Harness, client: TestClient) -> None:
    # The file reader treats a blank value as not set, so the engine keeps its default.
    harness.write('{ "ocr_engine_fallback": "" }')
    harness.launch()
    row = rows(client.get(URL).json())["ocr_engines"]
    assert row["saved"] is None


def test_key_locked_by_dotenv(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ROUTING_UNIT", "page")
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset({"OCR_ROUTING_UNIT"}))
    harness.launch()
    row = rows(client.get(URL).json())["ocr_routing_unit"]
    assert (row["locked"], row["source"]) == (True, "dotenv")
    assert row["lock_reason"] == (
        "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here."
    )


def test_a_read_failure_gives_the_envelope(harness: Harness, client: TestClient) -> None:
    def explode() -> Any:
        raise RuntimeError("detail /Users/someone")

    harness.launch()
    harness.app.state.configuration.read_file = explode
    response = client.get(URL)
    refused(response, 500)
    assert "someone" not in response.text


# ── Write ────────────────────────────────────────────────────────────────


def test_save_a_boolean(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = put(client, {"ocr_maths_routing_enabled": False})
    assert response.status_code == 200, response.text
    body = response.json()
    assert parse_jsonc(harness.text())["ocr_maths_routing_enabled"] is False
    row = rows(body)["ocr_maths_routing_enabled"]
    assert (row["value"], row["saved"], row["restart_pending"]) == (True, False, True)
    assert body["revision"] == file_revision(harness.folder)


def test_use_default_removes_the_key(harness: Harness, client: TestClient) -> None:
    harness.write('// mine\n{ "ocr_engines": ["dots-mocr", "my-engine"] }\n')
    harness.launch()
    response = put(client, {"ocr_engines": None}, file_revision(harness.folder))
    assert response.status_code == 200, response.text
    assert "ocr_engines" not in parse_jsonc(harness.text())
    assert harness.text().startswith("// mine\n")


def test_unprovisioned_engine_is_allowed(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = put(client, {"ocr_engines": ["my-engine"]})
    assert response.status_code == 200, response.text
    assert parse_jsonc(harness.text())["ocr_engines"] == ["my-engine"]
    engines = {engine["name"]: engine for engine in response.json()["ocr"]["engines"]}
    assert engines["my-engine"]["available"] is False
    assert engines["my-engine"]["reason"]


def test_a_reader_that_is_not_installed_is_allowed_in_a_list(
    harness: Harness, client: TestClient
) -> None:
    harness.launch()
    response = put(client, {"pdf_readers": ["pypdfium2", "pypdf"]})
    assert response.status_code == 200, response.text
    assert parse_jsonc(harness.text())["pdf_readers"] == ["pypdfium2", "pypdf"]


def test_all_five_keys_in_one_save(harness: Harness, client: TestClient) -> None:
    harness.launch()
    values = {
        "pdf_readers": ["pypdf", "liteparse"],
        "ocr_fallback_enabled": False,
        "ocr_routing_unit": "page",
        "ocr_engines": ["a", "b"],
        "ocr_maths_routing_enabled": False,
        "ocr_non_latin_routing": "always",
    }
    response = put(client, values)
    assert response.status_code == 200, response.text
    saved = {key: row["saved"] for key, row in rows(response.json()).items()}
    # ocr_local_backends (local-ocr-backends) is not in this save: its row stays unset.
    assert saved == {**values, "ocr_local_backends": None}


def test_a_list_save_removes_the_old_keys_in_the_same_write(
    harness: Harness, client: TestClient
) -> None:
    harness.write(
        '// mine\n{ "pdf_reader": "pypdf", "ocr_engine_primary": "dots-mocr",'
        ' "ocr_engine_fallback": "paddleocr-vl", "web_port": 9100 }\n'
    )
    harness.launch()
    revision = file_revision(harness.folder)
    response = put(client, {"pdf_readers": ["liteparse"], "ocr_engines": ["dots-mocr"]}, revision)
    assert response.status_code == 200, response.text
    saved = parse_jsonc(harness.text())
    assert saved == {"pdf_readers": ["liteparse"], "ocr_engines": ["dots-mocr"], "web_port": 9100}
    assert harness.text().startswith("// mine\n")


def test_a_list_save_with_a_file_that_holds_one_old_key_removes_only_that_list_old_keys(
    harness: Harness, client: TestClient
) -> None:
    harness.write('{ "pdf_reader": "pypdf", "ocr_engine_primary": "mine" }')
    harness.launch()
    put(client, {"pdf_readers": ["liteparse"]}, file_revision(harness.folder))
    assert parse_jsonc(harness.text()) == {
        "pdf_readers": ["liteparse"],
        "ocr_engine_primary": "mine",
    }


# ── Refusals, in the D10 order ───────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"values": {"pdf_readers": ["pypdf"]}},
        {"values": {"pdf_readers": ["pypdf"]}, "revision": "absent", "extra": 1},
        {"values": ["pdf_readers"], "revision": "absent"},
        {"values": {}, "revision": "absent"},
        {"values": {f"k{i}": 1 for i in range(10)}, "revision": "absent"},
        {"values": {"pdf_readers": ["pypdf"]}, "revision": "r" * 129},
    ],
)
def test_1_body_shape(harness: Harness, client: TestClient, body: dict[str, Any]) -> None:
    harness.launch()
    message = refused(client.put(URL, json=body, headers=ORIGIN), 400)
    assert message.startswith("Invalid request.")
    assert harness.text() == ""


def test_2_key_outside_the_five(harness: Harness, client: TestClient) -> None:
    harness.launch()
    refused(
        put(client, {"embed_provider": "local"}),
        400,
        "embed_provider is not a document reading setting.",
    )
    assert harness.text() == ""


@pytest.mark.parametrize(
    "key",
    ["ocr_fallback_min_confidence", "ocr_fallback_page_fraction", "ocr_maths_page_fraction"],
)
def test_2_removed_fraction_key(harness: Harness, client: TestClient, key: str) -> None:
    harness.launch()
    refused(put(client, {key: 0.2}), 400, f"{key} is not a document reading setting.")
    assert harness.text() == ""


@pytest.mark.parametrize(
    ("key", "list_key"),
    [
        ("pdf_reader", "pdf_readers"),
        ("ocr_engine_primary", "ocr_engines"),
        ("ocr_engine_fallback", "ocr_engines"),
    ],
)
def test_2_old_key_is_refused_naming_the_list_key(
    harness: Harness, client: TestClient, key: str, list_key: str
) -> None:
    harness.launch()
    refused(
        put(client, {key: "pypdf"}),
        400,
        f"{key}: Replaced by {list_key}. Write {list_key} instead.",
    )
    refused(
        put(client, {key: None}), 400, f"{key}: Replaced by {list_key}. Write {list_key} instead."
    )
    assert harness.text() == ""


def test_3_locked_key(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDF_READERS", "pypdf")
    harness.launch()
    message = "Remove PDF_READERS from the environment or .env to edit it here."
    refused(put(client, {"pdf_readers": ["liteparse"]}), 409, message)
    refused(put(client, {"pdf_readers": None}), 409, message)
    assert harness.text() == ""


def test_3_locked_by_an_old_variable_names_that_variable(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ENGINE_PRIMARY", "x")
    harness.launch()
    refused(
        put(client, {"ocr_engines": ["a"]}),
        409,
        "Remove OCR_ENGINE_PRIMARY from the environment or .env to edit it here.",
    )
    assert harness.text() == ""


def test_4_value_not_allowed(harness: Harness, client: TestClient) -> None:
    harness.launch()
    message = refused(put(client, {"ocr_routing_unit": "document"}), 400)
    assert message == "ocr_routing_unit: The value must be one of: page."
    assert "document" not in message
    assert harness.text() == ""


def test_4_one_bad_value_stops_the_whole_save(harness: Harness, client: TestClient) -> None:
    harness.write('{ "web_port": 9100 }')
    harness.launch()
    before = harness.text()
    response = put(client, {"ocr_fallback_enabled": False, "ocr_engines": ["../x"]})
    refused(response, 400)
    assert harness.text() == before


def test_4_blank_text(harness: Harness, client: TestClient) -> None:
    harness.launch()
    refused(
        put(client, {"ocr_engines": ["dots-mocr", ""]}),
        400,
        "ocr_engines: The value must not be blank. Send null to use the default.",
    )


def test_4_unknown_reader(harness: Harness, client: TestClient) -> None:
    harness.launch()
    refused(
        put(client, {"pdf_readers": ["pdfminer"]}),
        400,
        "pdf_readers: The value must be one of: liteparse, pdf_inspector, pypdfium2, pypdf.",
    )
    assert harness.text() == ""


@pytest.mark.parametrize("value", [[], ["pypdf", "pypdf"], ["auto"], ["pypdf", ""], "pypdf"])
def test_4_bad_reader_lists(harness: Harness, client: TestClient, value: Any) -> None:
    harness.launch()
    refused(put(client, {"pdf_readers": value}), 400)
    assert harness.text() == ""


def test_4_engine_name_with_a_path(harness: Harness, client: TestClient) -> None:
    harness.launch()
    message = refused(put(client, {"ocr_engines": ["../other"]}), 400)
    assert message.startswith("ocr_engines: The engine name must start")
    assert harness.text() == ""


def test_6_stale_revision(harness: Harness, client: TestClient) -> None:
    harness.write("{}")
    harness.launch()
    revision = file_revision(harness.folder)
    harness.write('{ "web_port": 9100 }')
    refused(
        put(client, {"pdf_readers": ["pypdf"]}, revision),
        409,
        "omrs.jsonc changed on disk. Reload to see the new values.",
    )


def test_7_broken_file(harness: Harness, client: TestClient) -> None:
    harness.write('{ "pdf_reader": ')
    harness.launch()
    refused(
        put(client, {"pdf_readers": ["pypdf"]}, file_revision(harness.folder)),
        409,
        "omrs.jsonc could not be read. Fix it, then save again.",
    )


def test_8_disk_refuses_the_write(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.config import settings_file_write

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise settings_file_write.SettingsFileWriteError(settings_file_write.WRITE_FAILED)

    monkeypatch.setattr(settings_file_write, "_write_atomically", refuse)
    harness.launch()
    refused(put(client, {"pdf_readers": ["pypdf"]}), 500, "omrs.jsonc could not be written.")


@pytest.mark.parametrize(
    "values",
    [
        {"pdf_readers": [SUBMITTED]},
        {"pdf_reader": SUBMITTED},
        {"ocr_engines": [f"../{SUBMITTED}"]},
        {"ocr_engines": SUBMITTED},
        {"ocr_fallback_enabled": SUBMITTED},
        {"ocr_maths_routing_enabled": SUBMITTED},
        {"ocr_routing_unit": SUBMITTED},
    ],
)
def test_no_message_holds_the_submitted_value(
    harness: Harness, client: TestClient, values: dict[str, Any]
) -> None:
    harness.launch()
    response = put(client, values)
    assert response.status_code == 400
    assert SUBMITTED not in response.text


def test_no_shape_message_holds_the_submitted_value(harness: Harness, client: TestClient) -> None:
    harness.launch()
    body = {"values": {"pdf_readers": ["x"]}, "revision": SUBMITTED * 10}
    response = client.put(URL, json=body, headers=ORIGIN)
    assert response.status_code == 400 and SUBMITTED not in response.text


# ── Contract ─────────────────────────────────────────────────────────────


def test_responses_conform_to_the_contract(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCR_WORKERS_DIR", str(tmp_path / "workers"))
    monkeypatch.setenv("OCR_ROUTING_UNIT", "page")
    check = ContractChecker()
    harness.write('{ "ocr_engine_fallback": "" }')
    harness.launch()
    body = check.check(client.get(URL), 200)
    check.check(put(client, {"pdf_readers": ["pypdf"]}, body["revision"]), 200)
    check.check(put(client, {"pdf_readers": ["pypdf"]}, "stale"), 409)
    check.check(put(client, {"pdf_reader": "pypdf"}), 400)
    check.check(put(client, {"ocr_routing_unit": "page"}), 409)
    check.check(put(client, {"embed_provider": "x"}), 400)
    check.check(client.put(URL, json={"values": {}}, headers=ORIGIN), 400)
    assert check.operations >= FAMILIES["document_reading"]
