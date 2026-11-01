"""The llama.cpp Chat card's view of the shared ``chat`` runtime (managed-llamacpp-runtimes D1, D8).

:class:`LlamacppServer` is a thin adapter over the process's
:class:`~omrs.integrations.llamacpp_runtime.RuntimeManager`. Start joins the
``chat`` runtime as a client (it starts or adopts the server), Stop is an
operator stop, and the status reads the runtime state files. The methods
block, so the routes call them through ``run_in_threadpool``.

The server is detached and may belong to another OMRS process, so the status
has no exit code. Its output goes to ``server.log`` in the runtime folder,
which no route reads. The CLI and the stdio MCP server do not import this
module.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi.concurrency import run_in_threadpool

from ...integrations.llamacpp_runtime import (
    RuntimeLease,
    RuntimeManager,
    RuntimeSpec,
    RuntimeUnavailable,
    chat_spec,
    read_server_record,
    rules,
    runtime_dir,
)
from ...integrations.llamacpp_runtime import process as runtime_process

logger = logging.getLogger(__name__)

State = Literal["stopped", "starting", "running", "failed"]

#: The runtime id of the Chat server.
CHAT = "chat"


@dataclass(frozen=True)
class LaunchConfig:
    """The saved values one launch uses.

    Attributes:
        binary: Program path.
        model: ``.gguf`` path or Hugging Face id.
        context_window: Tokens passed as ``-c``.
        chat_url: The chat address. Its port is the port of the server.
    """

    binary: str
    model: str
    context_window: int
    chat_url: str


@dataclass(frozen=True)
class StartedWith:
    """What the running process was started with, to detect a pending restart."""

    binary: str
    model: str
    model_kind: rules.ModelKind
    context_window: int


@dataclass(frozen=True)
class ServerStatus:
    """The state of the Chat server. ``reason`` is one of ``rules.REASONS`` or ``None``."""

    state: State
    reason: str | None = None
    exit_code: int | None = None
    pid_running: bool = False
    started_with: StartedWith | None = None


def _check(config: LaunchConfig) -> str | RuntimeSpec:
    """Return a refusal reason, or the managed ``chat`` spec when every rule holds."""
    if not config.binary.strip() or not config.model.strip():
        return "not-configured"
    if not rules.check_binary(config.binary):
        return "binary-invalid"
    kind = rules.model_kind(config.model)
    if kind is None:
        return "model-invalid"
    port = rules.loopback_port(config.chat_url)
    if port is None:
        return "not-loopback"
    return chat_spec(
        mode="managed",
        binary=config.binary,
        model=config.model,
        port=port,
        window=config.context_window,
        kind=kind,
    )


def _started_with(spec: RuntimeSpec) -> StartedWith:
    flag = "-hf" if "-hf" in spec.argv else "-m"
    window = int(spec.argv[spec.argv.index("-c") + 1])
    model = spec.argv[spec.argv.index(flag) + 1]
    return StartedWith(spec.binary, model, "hf" if flag == "-hf" else "file", window)


class LlamacppServer:
    """The Chat card's start, stop and status over the shared ``chat`` runtime.

    Args:
        manager: The runtime manager of this process.
    """

    def __init__(self, manager: RuntimeManager) -> None:
        self.manager = manager
        self._lease: RuntimeLease | None = None
        self._refusal: str | None = None

    @property
    def log_path(self) -> Path:
        """``server.log`` in the Chat runtime folder. No route reads it."""
        return runtime_dir(self.manager.root, CHAT) / runtime_process.LOG_FILE

    # ── Status ───────────────────────────────────────────────────────────

    def status(self, config: LaunchConfig | None = None) -> ServerStatus:
        """Return the state from the runtime files. Starts and writes nothing.

        Args:
            config: The saved values; a server started with them reports them
                as ``started_with``.
        """
        record = read_server_record(runtime_dir(self.manager.root, CHAT))
        if record is not None and runtime_process.owns(record.pid, record.binary):
            state: State = "running" if record.state == "running" else "starting"
            return ServerStatus(state, pid_running=True, started_with=self._known(record, config))
        if self._refusal is not None:
            return ServerStatus("failed", self._refusal)
        if record is not None and record.reason:
            return ServerStatus("failed", record.reason)
        if record is not None and record.state != "stopped":
            return ServerStatus("failed", "exited")  # gone with no stop recorded: it crashed
        return ServerStatus("stopped")

    def _known(self, record: Any, config: LaunchConfig | None) -> StartedWith | None:
        """Return what the running server started with, when this process knows its spec."""
        candidates = [self._lease.spec] if self._lease is not None else []
        if config is not None and isinstance(spec := _check(config), RuntimeSpec):
            candidates.append(spec)
        for spec in candidates:
            if spec.digest == record.digest:
                return _started_with(spec)
        return None

    # ── Control ──────────────────────────────────────────────────────────

    def start(self, config: LaunchConfig) -> ServerStatus:
        """Join the ``chat`` runtime with *config*; it starts the server when none runs.

        A server that runs with other values is left alone (Restart applies
        them). Every refusal is a ``failed`` status with one fixed reason.
        """
        checked = _check(config)
        if isinstance(checked, str):
            self._refusal = checked
            return self.status(config)
        self._refusal = None
        record = read_server_record(runtime_dir(self.manager.root, CHAT))
        running = record is not None and runtime_process.owns(record.pid, record.binary)
        if running and record is not None and record.digest != checked.digest:
            return self.status(config)  # running with other values
        lease = self.manager.lease(checked)
        if lease.operator_stopped:
            lease.leave()  # the operator's own Start: join again
        self._lease = lease
        try:
            lease.join()
        except RuntimeUnavailable as refused:
            self._refusal = refused.reason
        return self.status(config)

    def stop(self) -> ServerStatus:
        """Operator stop (design D8). With no recorded server, nothing is signalled.

        The lease stays: a process that joined this server does not start it
        again until it leaves. Start leaves and joins again.
        """
        self._refusal = None
        self.manager.stop(CHAT)
        return self.status()

    def restart(self, config: LaunchConfig) -> ServerStatus:
        """Stop the server, then start it with *config*."""
        self.stop()
        return self.start(config)

    def shutdown(self) -> None:
        """Leave the ``chat`` lease when ``omrs web`` exits; the last client stops the server."""
        if self._lease is not None:
            self._lease.leave()


def owning_lifespan(inner: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Wrap an app lifespan with the runtime sweep at start and the Chat leave at shutdown.

    At start-up the manager stops every owned server that no OMRS process
    uses (design D9). At shutdown the Chat adapter leaves its lease. Both
    read ``app.state`` then, so a test can replace them. A failure is logged
    and never raised.
    """

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[None]:
        manager = getattr(app.state, "runtime_manager", None)
        if manager is not None:
            try:
                await run_in_threadpool(manager.sweep)
            except Exception:
                logger.exception("The llama.cpp runtime sweep failed.")
        try:
            async with inner(app):
                yield
        finally:
            server = getattr(app.state, "llamacpp_server", None)
            if server is not None:
                try:
                    await run_in_threadpool(server.shutdown)
                except Exception:
                    logger.exception("The llama.cpp Chat runtime could not be left cleanly.")

    return lifespan
