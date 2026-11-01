"""The llama.cpp idle sleep setting is gone (managed-llamacpp-runtimes, design D12, task 5.4).

OMRS stops an idle managed runtime after a fixed 10 minutes. The environment
name fails start-up, whether it comes from the shell or from ``.env``. The
``omrs.jsonc`` key is ignored and listed in the problem list. Every test
points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from omrs.config import Settings, check_legacy_env_vars, provenance
from omrs.config.settings_file import KIND_RETIRED, read_settings_file
from omrs.core.settings import EffectiveSettings

NAME = "LLAMACPP_IDLE_SLEEP_SECONDS"
KEY = "llamacpp_idle_sleep_seconds"


@pytest.fixture
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    monkeypatch.delenv(NAME, raising=False)
    return root


def test_a_leftover_variable_fails_and_names_the_fixed_idle_stop() -> None:
    with pytest.raises(ValueError) as refused:
        check_legacy_env_vars({NAME: "300"})

    message = str(refused.value)
    assert NAME in message
    assert "10 minutes" in message
    assert "300" not in message


def test_a_dotenv_entry_fails_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``.env`` joins the environment at import, so the same check sees it."""
    work = tmp_path / "work"
    work.mkdir()
    (work / ".env").write_text(f"{NAME}=300\n", encoding="utf-8")
    monkeypatch.chdir(work)
    monkeypatch.setattr(os, "environ", dict(os.environ))  # load_dotenv leaves no trace
    monkeypatch.delenv(NAME, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())

    provenance.load_project_dotenv()

    with pytest.raises(ValueError) as refused:
        check_legacy_env_vars()
    assert NAME in str(refused.value)
    assert "10 minutes" in str(refused.value)


def test_the_config_file_key_is_listed_as_a_problem_and_never_read(
    folder: Path, tmp_path: Path
) -> None:
    (folder / "omrs.jsonc").write_text(f'{{ "{KEY}": 300 }}', encoding="utf-8")

    (problem,) = read_settings_file().problems

    assert (problem.kind, problem.key) == (KIND_RETIRED, KEY)
    assert "10 minutes" in problem.message
    assert "300" not in problem.message
    assert KEY not in read_settings_file().values
    env_file = tmp_path / "none.env"
    env_file.write_text("", encoding="utf-8")
    assert not hasattr(Settings(_env_file=env_file), KEY)


def test_neither_settings_model_has_the_field() -> None:
    assert KEY not in Settings.model_fields
    assert KEY not in EffectiveSettings.model_fields


def test_the_starter_file_has_no_idle_sleep_key() -> None:
    from omrs.transports.cli.config_template import build_template

    assert KEY not in build_template()
