"""The body of ``/v1/settings/document-reading`` (document-reading-settings, task 1.6).

The builder imports no web framework, so these tests need no ``fastapi``. A
plain namespace stands in for ``ConfigurationState``. Every test points
``OMRS_CONFIG_DIR`` at a temporary folder and never reads the real one.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrs import capabilities
from omrs.config import Settings, provenance
from omrs.config.rules import DOCUMENT_READING_KEYS, OLD_READING_KEYS
from omrs.config.settings_file import file_revision, read_settings_file
from omrs.transports.api import document_reading
from omrs.transports.api.document_reading import (
    build_document_reading,
    lock_reason,
    reset_reader_in_use,
    update_refusal,
)
from omrs.transports.api.restart_snapshot import capture

OLD_KEYS = tuple(old for olds in OLD_READING_KEYS.values() for old in olds)
VARIABLES = tuple(key.upper() for key in (*DOCUMENT_READING_KEYS, *OLD_KEYS)) + ("OCR_WORKERS_DIR",)
DEFAULTS = {
    "pdf_readers": ["pdf_inspector", "liteparse", "pypdf"],
    "ocr_fallback_enabled": True,
    "ocr_routing_unit": "page",
    "ocr_engines": ["dots-mocr", "paddleocr-vl"],
    "ocr_maths_routing_enabled": True,
    "ocr_non_latin_routing": "off",
}
OPTIONS = {"pypdf": None, "pypdfium2": "The package 'pypdfium2' is not installed."}


class Harness:
    """A config folder, an empty ``.env`` and the launch state."""

    def __init__(self, folder: Path, empty_env: Path) -> None:
        self.folder = folder
        self.empty_env = empty_env
        self.state: Any = None

    def write(self, text: str) -> None:
        (self.folder / "omrs.jsonc").write_text(text, encoding="utf-8")

    def launch(self) -> None:
        file = read_settings_file(self.folder)
        self.state = SimpleNamespace(
            launch_settings=Settings(_env_file=self.empty_env),
            snapshot=capture(file),
            read_file=lambda: read_settings_file(self.folder),
        )

    def body(self) -> dict[str, Any]:
        return build_document_reading(self.state)

    def rows(self) -> dict[str, dict[str, Any]]:
        return {row["key"]: row for row in self.body()["settings"]}


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
    yield Harness(folder, empty_env)
    reset_reader_in_use()


# ── Shape ────────────────────────────────────────────────────────────────


def test_five_rows_in_key_order_with_defaults(harness: Harness) -> None:
    harness.launch()
    body = harness.body()
    assert set(body) == {"revision", "settings", "pdf_readers", "pdf_reader_in_use", "ocr"}
    assert [row["key"] for row in body["settings"]] == list(DOCUMENT_READING_KEYS)
    assert body["revision"] == "absent"
    for row in body["settings"]:
        assert row["default"] == DEFAULTS[row["key"]]
        assert row["value"] == DEFAULTS[row["key"]]
        assert (row["saved"], row["source"], row["locked"]) == (None, "default", False)
        assert (row["lock_reason"], row["restart_pending"]) == (None, False)


def test_readers_list_auto_first_then_the_registry_order(harness: Harness) -> None:
    harness.launch()
    body = harness.body()
    assert body["pdf_readers"] == [
        {"name": "auto", "available": True, "reason": None},
        {"name": "pypdf", "available": True, "reason": None},
        {"name": "pypdfium2", "available": False, "reason": OPTIONS["pypdfium2"]},
    ]
    assert body["pdf_reader_in_use"] == "pypdf"


def test_the_reader_in_use_is_computed_once_per_process(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        capabilities, "resolve_pdf_reader", lambda settings: calls.append("x") or "liteparse"
    )
    harness.launch()
    assert harness.body()["pdf_reader_in_use"] == "liteparse"
    assert harness.body()["pdf_reader_in_use"] == "liteparse"
    assert calls == ["x"]


def test_a_failing_reader_probe_gives_null(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(settings: Any) -> str:
        raise RuntimeError("probe failed")

    monkeypatch.setattr(capabilities, "resolve_pdf_reader", explode)
    harness.launch()
    assert harness.body()["pdf_reader_in_use"] is None


# ── Sources and locks ────────────────────────────────────────────────────


def test_a_file_value_reads_config_file_and_is_saved(harness: Harness) -> None:
    harness.write('{ "pdf_readers": ["liteparse"], "ocr_fallback_enabled": false }')
    harness.launch()
    found = harness.rows()
    assert (found["pdf_readers"]["value"], found["pdf_readers"]["saved"]) == (
        ["liteparse"],
        ["liteparse"],
    )
    assert found["pdf_readers"]["source"] == "config-file"
    assert found["ocr_fallback_enabled"]["value"] is False
    assert harness.body()["revision"] == file_revision(harness.folder)


def test_env_and_dotenv_lock_the_row(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_READERS", "pypdf")
    monkeypatch.setenv("OCR_ROUTING_UNIT", "page")
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset({"OCR_ROUTING_UNIT"}))
    harness.launch()
    found = harness.rows()
    assert (found["pdf_readers"]["source"], found["pdf_readers"]["locked"]) == ("env", True)
    assert found["pdf_readers"]["value"] == ["pypdf"]
    assert found["pdf_readers"]["lock_reason"] == (
        "Remove PDF_READERS from the environment or .env to edit it here."
    )
    unit = found["ocr_routing_unit"]
    assert (unit["value"], unit["source"], unit["locked"]) == ("page", "dotenv", True)
    assert unit["lock_reason"] == lock_reason("ocr_routing_unit")
    assert lock_reason("ocr_routing_unit") == (
        "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here."
    )


@pytest.mark.parametrize(
    ("variable", "key", "value"),
    [
        ("OCR_ENGINE_PRIMARY", "ocr_engines", ["x", "paddleocr-vl"]),
        ("OCR_ENGINE_FALLBACK", "ocr_engines", ["dots-mocr", "x"]),
        ("PDF_READER", "pdf_readers", ["pypdf"]),
    ],
)
def test_an_old_variable_locks_the_list_row_and_is_named(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, variable: str, key: str, value: list[str]
) -> None:
    monkeypatch.setenv(variable, value[0] if key == "pdf_readers" else "x")
    harness.launch()
    row = harness.rows()[key]
    assert (row["value"], row["locked"], row["source"]) == (value, True, "env")
    assert row["lock_reason"] == f"Remove {variable} from the environment or .env to edit it here."
    assert update_refusal({key: None}, harness.state.launch_settings) == (409, row["lock_reason"])


def test_an_explicit_option_reads_default(harness: Harness) -> None:
    harness.launch()
    harness.state.launch_settings = Settings(
        _env_file=harness.empty_env, ocr_engine_primary="paddleocr-vl"
    )
    row = harness.rows()["ocr_engines"]
    assert (row["value"], row["source"], row["locked"]) == (
        ["paddleocr-vl", "paddleocr-vl"],
        "default",
        False,
    )


# ── restart_pending and saved ────────────────────────────────────────────


def test_a_file_change_after_launch_is_pending(harness: Harness) -> None:
    harness.launch()
    harness.write('{ "pdf_readers": ["liteparse"] }')
    row = harness.rows()["pdf_readers"]
    assert (row["value"], row["saved"], row["restart_pending"]) == (
        ["pdf_inspector", "liteparse", "pypdf"],
        ["liteparse"],
        True,
    )
    assert not any(r["restart_pending"] for k, r in harness.rows().items() if k != "pdf_readers")


def test_an_old_key_in_the_file_reads_as_the_list_it_means(harness: Harness) -> None:
    harness.write('{ "ocr_engine_primary": "mine", "pdf_reader": "pypdf" }')
    harness.launch()
    found = harness.rows()
    assert found["ocr_engines"]["saved"] == ["mine", "paddleocr-vl"]
    assert found["ocr_engines"]["value"] == ["mine", "paddleocr-vl"]
    assert found["pdf_readers"]["saved"] == ["pypdf"]
    assert found["pdf_readers"]["value"] == ["pypdf"]
    assert found["pdf_readers"]["source"] == "config-file"


def test_a_change_to_an_old_key_after_launch_is_pending_on_the_list_row(harness: Harness) -> None:
    harness.launch()
    harness.write('{ "pdf_reader": "liteparse" }')
    row = harness.rows()["pdf_readers"]
    assert (row["saved"], row["restart_pending"]) == (["liteparse"], True)


def test_a_locked_key_is_never_pending(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_READERS", "pypdf")
    harness.launch()
    harness.write('{ "pdf_readers": ["liteparse"] }')
    row = harness.rows()["pdf_readers"]
    assert (row["locked"], row["restart_pending"]) == (True, False)


def test_saved_is_null_for_a_value_that_breaks_its_rule(harness: Harness) -> None:
    harness.write(
        '{ "pdf_readers": ["pdfminer"], "ocr_engines": ["../x"], "ocr_maths_routing_enabled": 3 }'
    )
    harness.launch()
    found = harness.rows()
    assert found["pdf_readers"]["saved"] is None
    assert found["ocr_engines"]["saved"] is None
    assert found["ocr_maths_routing_enabled"]["saved"] is None


def test_a_hand_written_blank_fallback_comes_back_as_not_set(harness: Harness) -> None:
    # The file reader treats blank text as not set, so the engine keeps paddleocr-vl (D8).
    harness.write('{ "ocr_engine_fallback": "" }')
    harness.launch()
    assert harness.rows()["ocr_engines"]["saved"] is None


def test_a_missing_state_uses_the_launch_settings_and_nothing_is_pending(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs import compose

    harness.write('{ "pdf_readers": ["liteparse"] }')
    monkeypatch.setattr(compose, "get_settings", lambda: Settings(_env_file=harness.empty_env))
    body = build_document_reading(None)
    row = {r["key"]: r for r in body["settings"]}["pdf_readers"]
    assert (row["value"], row["saved"], row["restart_pending"]) == (
        ["liteparse"],
        ["liteparse"],
        False,
    )


# ── The OCR block ────────────────────────────────────────────────────────


def test_the_ocr_block_without_a_workers_folder(harness: Harness) -> None:
    harness.launch()
    ocr = harness.body()["ocr"]
    assert ocr["workers_dir"] is None and "worker_command_set" not in ocr
    assert [engine["name"] for engine in ocr["engines"]] == ["dots-mocr", "paddleocr-vl"]
    assert {engine["available"] for engine in ocr["engines"]} == {False}


def test_the_ocr_block_lists_saved_engines_without_a_worker_command(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OCR_WORKERS_DIR", str(tmp_path / "workers"))
    harness.write('{ "ocr_engines": ["dots-mocr", "my-engine"] }')
    harness.launch()
    harness.write('{ "ocr_engines": ["dots-mocr", "other-engine"] }')
    ocr = harness.body()["ocr"]
    assert ocr["workers_dir"] == "~/workers"
    assert "worker_command_set" not in ocr
    names = [engine["name"] for engine in ocr["engines"]]
    assert names == ["dots-mocr", "my-engine", "other-engine"]


# ── PUT checks 2 to 5 ────────────────────────────────────────────────────


def test_update_checks_follow_the_contract_order(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ROUTING_UNIT", "page")
    monkeypatch.setenv("OCR_ENGINE_FALLBACK", "x")
    harness.launch()
    launch = harness.state.launch_settings
    assert update_refusal({"embed_provider": "local"}, launch) == (
        400,
        "embed_provider is not a document reading setting.",
    )
    assert update_refusal({"ocr_engines": None, "ocr_routing_unit": 1}, launch) == (
        409,
        "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here.",
    )
    assert update_refusal({"ocr_fallback_page_fraction": 0.5}, launch) == (
        400,
        "ocr_fallback_page_fraction is not a document reading setting.",
    )
    assert update_refusal({"ocr_maths_routing_enabled": "yes"}, launch) == (
        400,
        "ocr_maths_routing_enabled: The value must be true or false.",
    )
    assert update_refusal({"pdf_readers": ["pdfminer"]}, launch) == (
        400,
        "pdf_readers: The value must be one of: liteparse, pdf_inspector, pypdfium2, pypdf.",
    )
    assert (
        update_refusal({"pdf_readers": ["pypdf"], "ocr_maths_routing_enabled": False}, launch)
        is None
    )


@pytest.mark.parametrize(
    ("key", "list_key"),
    [
        ("pdf_reader", "pdf_readers"),
        ("ocr_engine_primary", "ocr_engines"),
        ("ocr_engine_fallback", "ocr_engines"),
    ],
)
def test_an_old_key_is_refused_naming_the_list_key(
    harness: Harness, key: str, list_key: str
) -> None:
    harness.launch()
    assert update_refusal({key: "pypdf"}, harness.state.launch_settings) == (
        400,
        f"{key}: Replaced by {list_key}. Write {list_key} instead.",
    )


@pytest.mark.parametrize(
    ("value", "rule"),
    [
        ([], "The list must not be empty. Send null to use the default."),
        (["pypdf", "pypdf"], "The list must not name the same item twice."),
        (["auto"], "The value must be one of: liteparse, pdf_inspector, pypdfium2, pypdf."),
        (["pypdf", ""], "The value must not be blank. Send null to use the default."),
        ("pypdf", "The value must be a list of names."),
    ],
)
def test_a_reader_list_that_breaks_a_rule_is_refused(
    harness: Harness, value: object, rule: str
) -> None:
    harness.launch()
    assert update_refusal({"pdf_readers": value}, harness.state.launch_settings) == (
        400,
        f"pdf_readers: {rule}",
    )


def test_a_listed_reader_that_is_not_installed_is_allowed(harness: Harness) -> None:
    harness.launch()
    assert (
        update_refusal({"pdf_readers": ["pypdfium2", "pypdf"]}, harness.state.launch_settings)
        is None
    )


def test_an_engine_list_follows_the_engine_name_rule(harness: Harness) -> None:
    harness.launch()
    launch = harness.state.launch_settings
    assert update_refusal({"ocr_engines": ["dots-mocr"]}, launch) is None
    refusal = update_refusal({"ocr_engines": ["../other"]}, launch)
    assert refusal is not None and refusal[1].startswith("ocr_engines: The engine name must start")


def test_update_refuses_the_document_unit(harness: Harness) -> None:
    harness.launch()
    assert update_refusal({"ocr_routing_unit": "document"}, harness.state.launch_settings) == (
        400,
        "ocr_routing_unit: The value must be one of: page.",
    )


def test_the_builder_module_imports_no_web_framework() -> None:
    source = Path(document_reading.__file__).read_text(encoding="utf-8")
    assert "fastapi" not in source and "starlette" not in source
