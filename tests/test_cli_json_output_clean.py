"""Contract: ``--json`` output on stderr is JSON only, whatever logging ran before.

``--json`` output goes to stderr (stdout is the MCP channel). The CLI callback
logs the runtime summary before the command runs, so a real ``omrs set-profile
--json`` wrote log lines ahead of the JSON and no JSON parser could read it.
In tests it failed only when an earlier test on the same worker had run the
CLI logging setup, which made ``test_cli_profile`` fail at random in CI.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from tests.test_cli_profile import _patched
from typer.testing import CliRunner

from omrs.transports import cli
from omrs.transports.cli import app

runner = CliRunner()


@pytest.fixture
def cli_logging() -> Iterator[None]:
    """Run the real CLI logging setup, then restore the logging state."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    details = cli._runtime_details_enabled
    cli._setup_logging()
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
        cli._runtime_details_enabled = details


@pytest.mark.usefixtures("cli_logging")
def test_set_profile_json_is_parseable_after_cli_logging_setup() -> None:
    c, a, r = _patched()
    with c, a, r:
        result = runner.invoke(app, ["set-profile", "-c", "docs", "-p", "codebase", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stderr)["new_profile"] == "codebase"


@pytest.mark.usefixtures("cli_logging")
def test_json_mode_restores_logging_when_the_command_ends() -> None:
    before = logging.root.manager.disable
    c, a, r = _patched()
    with c, a, r:
        runner.invoke(app, ["set-profile", "-c", "docs", "-p", "codebase", "--json"])
    assert logging.root.manager.disable == before


@pytest.mark.usefixtures("cli_logging")
def test_without_json_the_runtime_summary_still_logs() -> None:
    c, a, r = _patched()
    with c, a, r:
        result = runner.invoke(app, ["set-profile", "-c", "docs", "-p", "codebase", "--yes"])
    assert result.exit_code == 0
    assert "Embedding model" in result.stderr
