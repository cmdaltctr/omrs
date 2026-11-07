"""The documented ``omrs llamacpp install`` commands run as written (one-llamacpp-router, 6.3).

``docs/guides/configuration.md`` and ``docs/guides/cli-reference.md`` show the
provisioning command. Each shown command runs here against the local archive
server of the provisioning tests, in a temporary data folder, and must succeed.
The pinned build tag in the docs is read from ``pins``.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
from tests.unit.test_llamacpp_router_provision_support import (
    CUDA_DEVICE_LINE,
    ArchiveServer,
    _archive_server,  # noqa: F401 - fixture "archive_server"
    data_folder,
)
from typer.testing import CliRunner

from omrs.integrations.llamacpp_runtime import pins
from omrs.transports.cli import app

ROOT = Path(__file__).resolve().parent.parent
DOCS = ("docs/guides/configuration.md", "docs/guides/cli-reference.md")
COMMAND = re.compile(r"^\s*(omrs llamacpp install\b.*?)\s*(?:#.*)?$", re.MULTILINE)

runner = CliRunner()


def documented_commands(name: str) -> list[str]:
    """Return the ``omrs llamacpp install`` lines inside fenced blocks of a doc."""
    found = []
    fenced = False
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        elif fenced and (match := COMMAND.match(line)):
            found.append(match.group(1))
    return found


@pytest.mark.parametrize("name", DOCS)
def test_the_doc_shows_the_install_command(name: str) -> None:
    commands = documented_commands(name)
    assert commands, f"{name} shows no `omrs llamacpp install` command"
    assert any("--flavour" not in command for command in commands), "show the plain command"


@pytest.mark.parametrize("name", DOCS)
def test_the_doc_names_the_pinned_build(name: str) -> None:
    assert pins.LLAMA_TAG in (ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", DOCS)
def test_every_documented_command_runs_as_written(
    name: str, archive_server: ArchiveServer, tmp_path: Path
) -> None:
    archive_server.publish("cpu")
    archive_server.publish("cuda", devices=CUDA_DEVICE_LINE)
    (archive_server.root / "nvidia-version").write_text("NVRM version\n")
    for command in documented_commands(name):
        words = shlex.split(command)
        result = runner.invoke(app, words[1:])
        assert result.exit_code == 0, f"{command!r}: {result.stderr}"
        assert result.stdout == ""
        assert "is ready" in " ".join(result.stderr.split())
    assert any(data_folder(tmp_path).glob(f"{pins.LLAMA_TAG}-*/llama-server"))
