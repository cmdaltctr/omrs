"""The single job that adds or removes an allowed extra on this server (design D1, D3).

One :class:`InstallJob` lives on ``WebRuntime``, so one install or uninstall
runs per server at a time. The job runs
``uv pip install --python <this Python> <requirements>`` or
``uv pip uninstall --python <this Python> <names>`` (its ``action``) as an
argument list with no shell and no stdin. The names come from the installed
package metadata; no request text reaches the argument list.

The process gets the server environment without any ``*_API_KEY``
variable. Its output (stderr merged into stdout) is redacted line by line
and only the last :data:`MAX_OUTPUT_LINES` lines are kept. The job stops
the process after :data:`INSTALL_TIMEOUT_SECONDS`.

After exit code 0 the job runs ``uv pip check --python <this Python>``
with the same limits, because an install can move a package another one
needs (ADR-094). A conflict fails the job with ``check-failed``.

After a successful check the extra goes into ``restart_needed`` with its
action (``install`` or ``uninstall``): the running process cannot use the
changed modules safely until it restarts. The map, not the last job, is what
the catalogue reports as ``pending_restart``, so a later job cannot change
what an earlier entry shows. The state is kept in memory, so a restart shows
``idle`` again.

The same job also runs the marimo tool action (:meth:`InstallJob.start_tool`,
ADR-101): a fixed ``uv tool install`` or ``uv tool uninstall`` argument list,
with the same guards. After exit code 0 it runs the caller's check function in
a thread instead of ``uv pip check``, and it sets no ``restart_needed``,
because the server's own environment did not change.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .install_environment import InstallEnvironment, detect_environment, extra_requirements
from .security import redact
from .uninstall_plan import Installed, installed_requirements, saved_settings

logger = logging.getLogger(__name__)

#: Seconds one install may take before the job stops it (10 minutes).
INSTALL_TIMEOUT_SECONDS = 600.0
#: Output lines kept for the status route.
MAX_OUTPUT_LINES = 40

IDLE = "idle"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"

#: The two job actions; each is also the ``uv pip`` subcommand.
ACTIONS: frozenset[str] = frozenset({"install", "uninstall"})


#: The step after exit code 0; returns 0 when the job succeeds.
_After = Callable[[dict[str, str], Callable[[str], str]], Awaitable[int]]


class InstallRunning(RuntimeError):
    """Raised when an install starts while another one runs."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _child_environment() -> tuple[dict[str, str], list[str]]:
    """Return the server environment without ``*_API_KEY`` variables, and their values."""
    env: dict[str, str] = {}
    removed: list[str] = []
    for name, value in os.environ.items():
        if name.upper().endswith("_API_KEY"):
            removed.append(value)
        else:
            env[name] = value
    return env, removed


def _stop(process: asyncio.subprocess.Process) -> None:
    """Kill the process group, so a child of ``uv`` stops too."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        process.kill()


@dataclass
class InstallJob:
    """State and runner of the one install this server may run.

    Attributes:
        timeout: Seconds before the job stops the process.
        python: The Python whose environment receives the packages.
        detect: Returns the install type and ``uv`` path (tests replace it).
        requirements: Returns an extra's requirements (tests replace it).
        installed: Returns the installed distributions and what they
            require (tests replace it).
        saved: Returns the values saved in ``omrs.jsonc`` (tests replace it).
        profiles: Returns the saved-profile catalogue, or ``None``. ``None`` here
            means the route reads the web server's profile service.
        restart_needed: Each extra installed or uninstalled in this launch, with its action.
    """

    timeout: float = INSTALL_TIMEOUT_SECONDS
    python: str = field(default_factory=lambda: sys.executable)
    detect: Callable[[], InstallEnvironment] = detect_environment
    requirements: Callable[[str], list[str]] = extra_requirements
    installed: Callable[[], Installed] = installed_requirements
    saved: Callable[[], Mapping[str, Any]] = saved_settings
    profiles: Callable[[], Any] | None = None
    restart_needed: dict[str, str] = field(default_factory=dict)
    _state: str = IDLE
    _action: str | None = None
    _extra: str | None = None
    _tool: str | None = None
    _started_at: str | None = None
    _finished_at: str | None = None
    _reason: str | None = None
    _exit_code: int | None = None
    _output: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_OUTPUT_LINES))
    _task: asyncio.Task[None] | None = None
    _process: asyncio.subprocess.Process | None = None

    @property
    def running(self) -> bool:
        """Whether an install runs now."""
        return self._state == RUNNING

    def snapshot(self) -> dict[str, Any]:
        """Return the state in the ``IntegrationInstall`` shape."""
        return {
            "state": self._state,
            "action": self._action,
            "extra": self._extra,
            "tool": self._tool,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "reason": self._reason,
            "exit_code": self._exit_code,
            "output": list(self._output),
        }

    def start(
        self,
        extra: str,
        uv: str,
        packages: list[str],
        *,
        action: str = "install",
        redactor: Callable[[str], str] | None = None,
    ) -> None:
        """Install or uninstall *packages* for *extra*. Call it on the event loop.

        Args:
            extra: The allowed extra, already checked by the caller.
            uv: Path of the ``uv`` program.
            packages: The extra's requirements (install) or the names to
                remove (uninstall), from the package metadata.
            action: ``install`` or ``uninstall``.
            redactor: ``Engine.redact``; removes provider credential values.

        Raises:
            InstallRunning: Another job runs.
            ValueError: *action* is not ``install`` or ``uninstall``.
        """
        self._begin(action, extra, None)
        argv = [uv, "pip", action, "--python", self.python, *packages]
        check = [uv, "pip", "check", "--python", self.python]

        async def after(env: dict[str, str], clean: Callable[[str], str]) -> int:
            return await self._exec(check, env, clean)

        self._task = asyncio.get_running_loop().create_task(self._run(argv, redactor, after))

    def start_tool(
        self,
        tool: str,
        argv: list[str],
        check: Callable[[], bool],
        *,
        action: str = "install",
        redactor: Callable[[str], str] | None = None,
    ) -> None:
        """Run a fixed ``uv tool`` argument list for *tool*. Call it on the event loop.

        Args:
            tool: The external tool, already checked by the caller.
            argv: The fixed argument list built by ``tool_environment``.
            check: Runs in a thread after exit code 0; ``True`` means success.
            action: ``install`` or ``uninstall``.
            redactor: ``Engine.redact``; removes provider credential values.

        Raises:
            InstallRunning: Another job runs.
            ValueError: *action* is not ``install`` or ``uninstall``.
        """
        self._begin(action, None, tool)

        async def after(env: dict[str, str], clean: Callable[[str], str]) -> int:
            return 0 if await asyncio.to_thread(check) else 1

        self._task = asyncio.get_running_loop().create_task(self._run(list(argv), redactor, after))

    def _begin(self, action: str, extra: str | None, tool: str | None) -> None:
        """Check that no job runs, then reset the state for a new job."""
        if action not in ACTIONS:
            raise ValueError(f"Unknown job action {action!r}.")
        if self.running:
            raise InstallRunning(f"The {self._extra or self._tool} {self._action} is running.")
        self._state, self._action, self._extra, self._tool = RUNNING, action, extra, tool
        self._started_at, self._finished_at = _now(), None
        self._reason, self._exit_code = None, None
        self._output.clear()

    async def wait(self) -> None:
        """Wait until the current job ends. Returns at once when idle."""
        if self._task is not None:
            await asyncio.shield(self._task)

    def _finish(self, state: str, reason: str | None, exit_code: int | None) -> None:
        self._state, self._reason, self._exit_code = state, reason, exit_code
        self._finished_at = _now()
        if state == SUCCEEDED and self._extra is not None and self._action is not None:
            self.restart_needed[self._extra] = self._action
        target = self._extra or self._tool
        logger.info("%s of %s ended: %s %s", self._action, target, state, reason or "")

    async def _run(
        self, argv: list[str], redactor: Callable[[str], str] | None, after: _After
    ) -> None:
        env, secrets = _child_environment()

        def clean(text: str) -> str:
            return redact(redactor(text) if redactor else text, secrets)

        try:
            reason, code = await asyncio.wait_for(
                self._steps(argv, after, env, clean), self.timeout
            )
        except TimeoutError:
            # Before OSError: TimeoutError is one of its subclasses.
            await self._stop_current()
            self._finish(FAILED, "timed-out", None)
            return
        except OSError:
            logger.warning("Could not start the %s of %s.", self._action, self._extra or self._tool)
            self._finish(FAILED, "start-failed", None)
            return
        except asyncio.CancelledError:
            # The server is shutting down: stop the process and keep no result.
            if self._process is not None:
                _stop(self._process)
            raise
        self._finish(SUCCEEDED if reason is None else FAILED, reason, code)

    async def _steps(
        self, install: list[str], after: _After, env: dict[str, str], clean: Callable[[str], str]
    ) -> tuple[str | None, int]:
        """Run the install or uninstall, then the check.

        Returns:
            The failure reason (or ``None``) and the last exit code. A tool
            check that fails keeps the install's exit code 0.
        """
        code = await self._exec(install, env, clean)
        if code != 0:
            return "exit-code", code
        checked = await after(env, clean)
        if self._tool is not None:
            return (None if checked == 0 else "check-failed"), code
        return (None if checked == 0 else "check-failed"), checked

    async def _exec(self, argv: list[str], env: dict[str, str], clean: Callable[[str], str]) -> int:
        """Run one argument list, keep its redacted output lines and return the exit code."""
        self._process = process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        if process.stdout is not None:
            async for raw in process.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._output.append(clean(line))
        return await process.wait()

    async def _stop_current(self) -> None:
        """Stop the running process after a timeout and wait for it to end."""
        if self._process is not None:
            _stop(self._process)
            await self._process.wait()
