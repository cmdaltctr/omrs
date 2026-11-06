"""Help, ``config`` and ``llamacpp`` commands never build the embedding runtime.

Change one-llamacpp-router, bug "upgraded install cannot start". The CLI root
callback built the embedder for every subcommand before Click handled the
subcommand's ``--help``. An install whose embedding model is outside the model
list then failed even on ``omrs config show`` and ``omrs llamacpp install --help``.

The repro uses a scratch settings folder, state folder and HOME. No command
reads the real ``~/.config/omrs`` or ``~/.omrs``, and no server starts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from omrs.transports.cli import app

runner = CliRunner()

#: The model of the upgraded install: it is not in the shipped ``llamacpp_models`` list.
UNLISTED = "qwen3-embedding:0.6b"

#: A subcommand path for each command group, deepest group first.
HELP_PATHS = [
    ["ingest"],
    ["search"],
    ["list"],
    ["watch"],
    ["delete"],
    ["benchmark"],
    ["answer"],
    ["set-profile"],
    ["list-collections"],
    ["install-login-watcher"],
    ["config"],
    ["config", "show"],
    ["llamacpp"],
    ["llamacpp", "install"],
    ["web"],
    ["experiments"],
]


def _repro_env(tmp_path: Path) -> dict[str, str]:
    """Return a clean process environment that holds only the repro settings file."""
    config = tmp_path / "config"
    config.mkdir()
    (config / "omrs.jsonc").write_text(
        json.dumps({"embed_provider": "llamacpp", "llamacpp_embed_model": UNLISTED})
    )
    home = tmp_path / "home"
    home.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_STATE_HOME": str(home / ".state"),
        "OMRS_CONFIG_DIR": str(config),
        "OMRS_STATE_DIR": str(state),
        "LANCEDB_URI": str(tmp_path / "lancedb"),
    }


def _omrs(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(Path(sys.executable).with_name("omrs")), *args],
        env=_repro_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
    )


# ── A help option never builds the runtime ──────────────────────────────────────────────────


@pytest.mark.parametrize("path", HELP_PATHS, ids=" ".join)
def test_a_subcommand_help_does_not_initialise_the_runtime(path: list[str]) -> None:
    with patch("omrs.transports.cli.compose.ensure_runtime_setup") as setup:
        result = runner.invoke(app, [*path, "--help"], env={"EMBED_PROVIDER": "not-a-provider"})
    assert result.exit_code == 0, result.output
    setup.assert_not_called()


# ── Commands that read Settings themselves skip the runtime ─────────────────────────────────


def test_config_show_does_not_initialise_the_runtime() -> None:
    with patch("omrs.transports.cli.compose.ensure_runtime_setup") as setup:
        result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0, result.output
    setup.assert_not_called()


def test_llamacpp_commands_do_not_initialise_the_runtime() -> None:
    with patch("omrs.transports.cli.compose.ensure_runtime_setup") as setup:
        result = runner.invoke(app, ["llamacpp", "install", "--help"])
    assert result.exit_code == 0, result.output
    setup.assert_not_called()


def test_a_command_that_sends_requests_still_initialises_the_runtime() -> None:
    with patch("omrs.transports.cli.compose.ensure_runtime_setup") as setup:
        runner.invoke(app, ["list"])
    setup.assert_called_once()


# ── The repro install: an unlisted model, a managed router ──────────────────────────────────


@pytest.mark.parametrize(
    "args",
    [
        ["config", "show"],
        ["llamacpp", "--help"],
        ["llamacpp", "install", "--help"],
        ["search", "--help"],
        ["ingest", "--help"],
    ],
    ids=" ".join,
)
def test_the_repro_install_runs_these_commands(tmp_path: Path, args: list[str]) -> None:
    done = _omrs(tmp_path, *args)
    assert done.returncode == 0, done.stderr[-800:]
    # The refusal line, not the config-show problem line that names the same rule.
    assert "Error: The embeddings model is not in the list." not in done.stderr
