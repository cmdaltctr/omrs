"""SIGTERM becomes a normal exit in the CLI, stdio MCP and watcher (task 4.7; D9).

A normal exit runs the ``atexit`` hook of the runtime manager, which leaves
every lease. Each entry point installs the handler before it does anything
else, so a SIGTERM at any later moment still leaves.
"""

from __future__ import annotations

import os
import signal
import sys
from collections.abc import Iterator

import pytest

from omrs.integrations.llamacpp_runtime import manager as manager_module


@pytest.fixture(autouse=True)
def _restore_sigterm() -> Iterator[None]:
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _is_exit_handler() -> bool:
    handler = signal.getsignal(signal.SIGTERM)
    if not callable(handler):
        return False
    with pytest.raises(SystemExit):
        handler(signal.SIGTERM, None)
    return True


def test_the_handler_turns_sigterm_into_system_exit() -> None:
    manager_module.install_sigterm_exit()
    with pytest.raises(SystemExit) as caught:
        os.kill(os.getpid(), signal.SIGTERM)  # the handler runs on return
    assert caught.value.code == 128 + signal.SIGTERM


def test_the_handler_keeps_an_existing_handler() -> None:
    def own(_signum: int, _frame: object) -> None:
        return None

    signal.signal(signal.SIGTERM, own)
    manager_module.install_sigterm_exit()
    assert signal.getsignal(signal.SIGTERM) is own


def test_the_cli_entry_point_installs_it(monkeypatch: pytest.MonkeyPatch) -> None:
    import omrs.transports.cli as cli

    seen: list[bool] = []
    monkeypatch.setattr(cli, "app", lambda: seen.append(_is_exit_handler()))
    monkeypatch.setattr(sys, "argv", ["omrs", "--help"])
    cli.run_cli()
    assert seen == [True]


def test_the_stdio_mcp_entry_point_installs_it(monkeypatch: pytest.MonkeyPatch) -> None:
    import omrs.transports.mcp as mcp

    def refuse(**_kwargs: object) -> None:
        raise ValueError("stop here")

    monkeypatch.setattr(mcp.compose, "build_engine", refuse)
    with pytest.raises(SystemExit):
        mcp.main()
    assert _is_exit_handler()


def test_the_watcher_entry_point_installs_it(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from omrs.daemon.runner import watch_directory

    with pytest.raises(SystemExit):
        watch_directory(str(tmp_path / "missing"))
    assert _is_exit_handler()
