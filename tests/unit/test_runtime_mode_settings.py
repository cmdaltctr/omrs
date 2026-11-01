"""Embedding and OCR runtime mode settings (change managed-llamacpp-runtimes, task 5.3).

``llamacpp_embed_server`` (``external`` or ``managed``, default ``external``)
and ``ocr_runtime_url`` (blank means managed) are read from the environment,
``.env`` and ``omrs.jsonc``. The Settings page never writes either key. Every
test points ``OMRS_CONFIG_DIR`` at a temporary folder; none reads the real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from tests.unit import test_web_configuration as base
from tests.unit.test_web_configuration import URL, Harness
from tests.unit.test_web_documents_support import ORIGIN

from omrs.config import Settings
from omrs.config.rules import ACCEPTED, ADDRESS_FIELDS
from omrs.config.settings_file import KIND_INVALID, read_settings_file
from omrs.config.settings_file_write import ALLOWED_KEYS, read_only_reason

harness = base.harness
client = base.client

EMBED = "llamacpp_embed_server"
OCR = "ocr_runtime_url"
VARIABLES = ("LLAMACPP_EMBED_SERVER", "OCR_RUNTIME_URL")


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    root = tmp_path / "mode-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def build(tmp_path: Path, dotenv: str = "") -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text(dotenv, encoding="utf-8")
    return Settings(_env_file=env_file)


def write_config(folder: Path, text: str) -> None:
    (folder / "omrs.jsonc").write_text(text, encoding="utf-8")


# ── llamacpp_embed_server ────────────────────────────────────────────────


def test_embed_server_defaults_to_external(tmp_path: Path) -> None:
    settings = build(tmp_path)
    assert getattr(settings, EMBED) == "external"
    assert ACCEPTED[EMBED] == ("external", "managed")
    assert EMBED not in settings.provider_explicit


def test_embed_server_from_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLAMACPP_EMBED_SERVER", "managed")
    settings = build(tmp_path)
    assert getattr(settings, EMBED) == "managed"
    assert settings.setting_sources[EMBED] == "env"


def test_embed_server_from_dotenv(tmp_path: Path) -> None:
    settings = build(tmp_path, "LLAMACPP_EMBED_SERVER=managed\n")
    assert getattr(settings, EMBED) == "managed"
    assert settings.setting_sources[EMBED] == "dotenv"


def test_embed_server_from_the_config_file(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "llamacpp_embed_server": "managed" }')
    settings = build(tmp_path)
    assert getattr(settings, EMBED) == "managed"
    assert settings.setting_sources[EMBED] == "config-file"
    assert EMBED in settings.config_file_fields


def test_an_unknown_embed_server_in_the_environment_fails_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LLAMACPP_EMBED_SERVER", "router")
    with pytest.raises(ValidationError, match="LLAMACPP_EMBED_SERVER"):
        build(tmp_path)


def test_an_unknown_embed_server_in_the_config_file_is_listed_and_ignored(
    folder: Path, tmp_path: Path
) -> None:
    write_config(folder, '{ "llamacpp_embed_server": "router" }')
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key) == (KIND_INVALID, EMBED)
    assert "external, managed" in problem.message
    assert getattr(build(tmp_path), EMBED) == "external"


# ── ocr_runtime_url ──────────────────────────────────────────────────────


def test_ocr_runtime_url_defaults_to_blank(tmp_path: Path) -> None:
    settings = build(tmp_path)
    assert getattr(settings, OCR) == ""


def test_ocr_runtime_url_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCR_RUNTIME_URL", "http://127.0.0.1:9100")
    settings = build(tmp_path)
    assert getattr(settings, OCR) == "http://127.0.0.1:9100"
    assert settings.setting_sources[OCR] == "env"


def test_ocr_runtime_url_from_dotenv(tmp_path: Path) -> None:
    settings = build(tmp_path, "OCR_RUNTIME_URL=http://127.0.0.1:9100\n")
    assert getattr(settings, OCR) == "http://127.0.0.1:9100"
    assert settings.setting_sources[OCR] == "dotenv"


def test_ocr_runtime_url_from_the_config_file(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "ocr_runtime_url": "http://127.0.0.1:9100" }')
    settings = build(tmp_path)
    assert getattr(settings, OCR) == "http://127.0.0.1:9100"
    assert settings.setting_sources[OCR] == "config-file"


def test_a_blank_ocr_runtime_url_in_the_environment_means_managed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCR_RUNTIME_URL", "  ")
    assert getattr(build(tmp_path), OCR) == ""


@pytest.mark.parametrize("value", ["ftp://127.0.0.1:9100", "127.0.0.1:9100", "http://u:p@h:1"])
def test_a_bad_ocr_runtime_url_in_the_environment_fails_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    monkeypatch.setenv("OCR_RUNTIME_URL", value)
    with pytest.raises(ValidationError) as caught:
        build(tmp_path)
    assert "OCR_RUNTIME_URL" in str(caught.value)
    assert value not in str(caught.value)


def test_a_bad_ocr_runtime_url_in_the_config_file_is_listed_and_ignored(
    folder: Path, tmp_path: Path
) -> None:
    write_config(folder, '{ "ocr_runtime_url": "ftp://127.0.0.1:9100" }')
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key) == (KIND_INVALID, OCR)
    assert getattr(build(tmp_path), OCR) == ""


def test_ocr_runtime_url_uses_the_address_rule() -> None:
    assert OCR in ADDRESS_FIELDS


# ── The Settings page never writes either key ────────────────────────────


@pytest.mark.parametrize(("key", "value"), [(EMBED, "managed"), (OCR, "http://127.0.0.1:9100")])
def test_neither_key_is_writable_by_the_page(key: str, value: str) -> None:
    assert key not in ALLOWED_KEYS
    assert read_only_reason(key) == "Set this in the environment, .env or omrs.jsonc."


@pytest.mark.parametrize(("key", "value"), [(EMBED, "managed"), (OCR, "http://127.0.0.1:9100")])
def test_the_put_route_refuses_the_key_and_writes_nothing(
    harness: Harness, client: object, key: str, value: str
) -> None:
    harness.launch()
    response = client.put(  # type: ignore[attr-defined]
        URL, json={"revision": "absent", "changes": {key: value}}, headers=ORIGIN
    )
    assert response.status_code == 400, response.text
    assert response.json()["message"] == f"{key} is not a setting that can be changed here."
    assert not (harness.folder / "omrs.jsonc").exists()


def test_the_starter_file_lists_both_keys() -> None:
    from omrs.transports.cli.config_template import build_template

    template = build_template()
    assert '"llamacpp_embed_server": "external"' in template
    assert '"ocr_runtime_url": ""' in template
