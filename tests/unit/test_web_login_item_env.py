"""The login item keeps the local OCR model folder (spec ``web-login-item``, design D7).

``install`` carries ``INDRA_OCR_MODEL_DIR`` into the new plist: from the
installing shell when set there, else from the plist it replaces. No other
variable is carried. Every path sits under ``tmp_path``.
"""

from __future__ import annotations

import plistlib
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_web_login_item_support import Harness, flat

from omrs.transports.cli import _web_login_item as wli

FOLDER = "INDRA_OCR_MODEL_DIR"
FIXED_PATH = {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.delenv(FOLDER, raising=False)
    return path


@pytest.fixture
def h(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    monkeypatch.delenv(FOLDER, raising=False)
    return Harness(tmp_path, monkeypatch)


def _write_old_plist(home: Path, environment: dict[str, str], command: str) -> None:
    """Write the plist an earlier install left, with *environment* added by hand."""
    plist_path, _, _ = wli.compute_paths(wli.LABEL, home=home)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    old = {
        "Label": wli.LABEL,
        "ProgramArguments": [command, "web", "--login-item"],
        "EnvironmentVariables": {**FIXED_PATH, **environment},
    }
    plist_path.write_bytes(plistlib.dumps(old))


def _new_environment(home: Path) -> dict[str, Any]:
    plan = wli.build_plan(home=home, command_path="/opt/omrs/bin/omrs")
    return plistlib.loads(wli.render_plist(plan))["EnvironmentVariables"]


def test_reinstall_keeps_the_folder_from_the_old_plist(home: Path) -> None:
    _write_old_plist(home, {FOLDER: "/models/indra"}, "/opt/omrs/bin/omrs")

    assert _new_environment(home) == {**FIXED_PATH, FOLDER: "/models/indra"}


def test_the_shell_value_wins(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_old_plist(home, {FOLDER: "/old/indra"}, "/opt/omrs/bin/omrs")
    monkeypatch.setenv(FOLDER, "/shell/indra")

    assert _new_environment(home) == {**FIXED_PATH, FOLDER: "/shell/indra"}


def test_other_variables_are_not_carried(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    others = {
        "OPENROUTER_API_KEY": "test-not-a-key",
        "PDFIUM_LIB_PATH": "/libs/libpdfium.dylib",
        "ORT_DYLIB_PATH": "/libs/libonnxruntime.dylib",
    }
    _write_old_plist(home, others, "/opt/omrs/bin/omrs")
    for name, value in others.items():
        monkeypatch.setenv(name, value)

    assert _new_environment(home) == FIXED_PATH


def test_nothing_to_carry_leaves_only_the_path(home: Path) -> None:
    assert _new_environment(home) == FIXED_PATH


def test_install_says_it_kept_the_folder_from_the_old_plist(h: Harness) -> None:
    _write_old_plist(h.home, {FOLDER: "/models/indra"}, str(h.command))

    result = h.invoke("install", "--command-path", str(h.command), "--dry-run")

    assert result.exit_code == 0, result.output
    assert f"Carries: {FOLDER} (kept from the old plist)" in flat(result.output)


def test_install_says_the_folder_came_from_the_shell(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(FOLDER, "/shell/indra")

    result = h.invoke("install", "--command-path", str(h.command), "--dry-run")

    assert f"Carries: {FOLDER} (from the installing shell)" in flat(result.output)


def test_install_prints_no_carried_line_when_nothing_is_carried(h: Harness) -> None:
    result = h.invoke("install", "--command-path", str(h.command), "--dry-run")

    assert result.exit_code == 0, result.output
    assert "Carries:" not in result.output


def test_a_forced_reinstall_writes_the_kept_folder(h: Harness) -> None:
    _write_old_plist(h.home, {FOLDER: "/models/indra"}, str(h.command))
    h.serve(link_port=8765)

    result = h.invoke("install", "--command-path", str(h.command), "--force", "--yes")

    assert result.exit_code == 0, result.output
    environment = plistlib.loads(h.plist.read_bytes())["EnvironmentVariables"]
    assert environment == {**FIXED_PATH, FOLDER: "/models/indra"}
