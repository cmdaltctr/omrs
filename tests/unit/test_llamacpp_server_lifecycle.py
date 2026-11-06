"""The router adapter of the Router panel stays inside its limits (task 7.1).

The adapter maps the runtime state files to the panel's status. These checks read
source: the runtime code looks up no process by name or port, and the CLI and
stdio MCP transports do not import the adapter. The start, stop and restart
behaviour has its tests in ``test_web_llamacpp_router.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from omrs.integrations.llamacpp_runtime import process  # noqa: E402
from omrs.transports.api import llamacpp_server as adapter  # noqa: E402

RUNTIME = Path(process.__file__).parent
ROUTES = Path(adapter.__file__).parent / "routes"
SCANNED = [
    Path(adapter.__file__),
    *sorted(RUNTIME.glob("*.py")),
    *sorted(ROUTES.glob("llamacpp_router*.py")),
]


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.name)
def test_the_runtime_code_looks_up_no_process_by_name_or_port(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for word in ("pkill", "killall", "lsof", "pgrep", "psutil", "process_iter", "netstat"):
        assert word not in source
    assert "shell=True" not in source


def test_the_adapter_is_not_imported_by_the_cli_or_stdio_transports() -> None:
    root = Path(adapter.__file__).parents[1]
    for folder in ("cli", "mcp"):
        for path in (root / folder).rglob("*.py"):
            assert "llamacpp_server" not in path.read_text(encoding="utf-8"), path
