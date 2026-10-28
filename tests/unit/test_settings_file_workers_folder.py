"""The OCR workers folder is writable after a folder check.

Change integrations-show-runtime-components, task 3.1.

The writer and the configuration route both refuse a relative path, a
missing folder and a folder without ``engines/``. A valid folder under the
home folder is stored with ``~``; an empty value removes the key. A value
that the environment sets stays locked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.config import Settings
from omrs.config.settings_file_write import (
    SettingsFileRefused,
    read_only_reason,
    write_settings,
)
from omrs.config.user_config import parse_jsonc
from omrs.transports.api.configuration_update import update_refusal

ORIGINAL = '{\n  "ollama_base_url": "http://a:1"\n}\n'


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    return folder


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "cfg"
    root.mkdir()
    (root / "omrs.jsonc").write_text(ORIGINAL, encoding="utf-8")
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def _workers(parent: Path) -> Path:
    folder = parent / "workers"
    (folder / "engines").mkdir(parents=True)
    return folder


def _text(config: Path) -> str:
    return (config / "omrs.jsonc").read_text(encoding="utf-8")


def test_the_workers_folder_is_no_longer_read_only() -> None:
    assert read_only_reason("ocr_workers_dir") is None


@pytest.mark.parametrize("make", ["relative", "missing", "no-engines"])
def test_a_bad_folder_is_refused_and_the_file_stays(
    make: str, config: Path, tmp_path: Path
) -> None:
    if make == "relative":
        value = "ocr-workers"
    elif make == "missing":
        value = str(tmp_path / "nowhere")
    else:
        (tmp_path / "bare").mkdir()
        value = str(tmp_path / "bare")

    with pytest.raises(SettingsFileRefused) as refused:
        write_settings({"ocr_workers_dir": value}, revision=None, directory=config)

    assert value not in str(refused.value)
    assert _text(config) == ORIGINAL


def test_a_folder_under_home_is_stored_with_a_tilde(home: Path, config: Path) -> None:
    folder = _workers(home)

    write_settings({"ocr_workers_dir": str(folder)}, revision=None, directory=config)

    assert parse_jsonc(_text(config))["ocr_workers_dir"] == "~/workers"


def test_an_empty_value_removes_the_key(home: Path, config: Path) -> None:
    write_settings({"ocr_workers_dir": str(_workers(home))}, revision=None, directory=config)

    write_settings({"ocr_workers_dir": ""}, revision=None, directory=config)

    assert "ocr_workers_dir" not in parse_jsonc(_text(config))


def test_the_route_check_refuses_a_folder_without_engines(config: Path, tmp_path: Path) -> None:
    (tmp_path / "bare").mkdir()

    status, message = update_refusal({"ocr_workers_dir": str(tmp_path / "bare")}, Settings()) or (
        0,
        "",
    )

    assert status == 400
    assert message.startswith("ocr_workers_dir: ")
    assert str(tmp_path) not in message


def test_an_environment_value_stays_locked(
    monkeypatch: pytest.MonkeyPatch, config: Path, home: Path
) -> None:
    folder = _workers(home)
    monkeypatch.setenv("OCR_WORKERS_DIR", str(folder))

    refusal = update_refusal({"ocr_workers_dir": str(folder)}, Settings())

    assert refusal is not None
    assert refusal[0] == 409
    assert "OCR_WORKERS_DIR" in refusal[1]
