"""marimo card routes and the ``tools`` list (install-marimo-from-integrations, D6, D7, D9).

marimo is an external tool, not an extra (ADR-101). It goes into its own
``uv tool`` environment, so the server's Python does not change and no
restart is needed. ``POST /v1/integrations/tools/marimo/install`` runs the
fixed ``uv tool install`` command from the shipped manifest range, and
``POST /v1/integrations/tools/marimo/uninstall`` runs ``uv tool uninstall
marimo`` only when the uv receipt holds exactly what the card installs. Both
use the one install job and need the browser session with the ``manage``
scope; a bearer credential never passes. The path value only selects the
tool: any other value gets 404 and starts nothing, and no request text
reaches the command. The install does not register the editor (D4).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from ..engine_access import RuntimeDep, admitted, require_session
from ..errors import API_HEADERS, error_response
from ..install_job import InstallRunning
from ..security import Principal, redact
from ..tool_environment import (
    NOT_INSTALLED,
    READY,
    TOOL,
    UNINSTALL_COMMAND,
    UNKNOWN,
    ToolStatus,
    install_argv,
    install_caution,
    install_command,
    requirement,
    uninstall_argv,
)
from .graphs import ok

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
ToolParam = Annotated[str, PathParam(max_length=64)]

UNKNOWN_TOOL = "This tool is not in the integrations list."
PURPOSE = (
    "Notebook editor for the Library and the Code editor. "
    "It goes into its own uv tool environment, outside OMRS."
)

#: Plain-English message for each 409 reason of the two tool routes.
TOOL_REASONS: dict[str, str] = {
    "already-installed": (
        "marimo with jupytext is already installed in its own uv tool environment."
    ),
    "status-unknown": (
        "The server could not read the marimo tool environment. "
        "Use the command on the card in a terminal instead."
    ),
    "uv-not-found": "The uv program was not found. Use the command on the card in a terminal.",
    "install-running": "Another install is running. Wait until it finishes, then try again.",
    "editor-running": (
        "A marimo editor that OMRS started is running. "
        "Stop it in Experiments, Code editor, then try again."
    ),
    "not-installed": "marimo is not installed as a uv tool, so there is nothing to remove.",
    "not-installed-by-app": (
        "This marimo was not installed from this card, so the app does not remove it. "
        "Use the command on the card in a terminal."
    ),
}


def editor_running(runtime: Any) -> bool:
    """Return whether a marimo editor that this server started is running."""
    host = runtime.plugins
    return host is not None and any(item.plugin == TOOL for item in host.editors.sessions())


def tool_job_running(runtime: Any) -> bool:
    """Return whether the install job runs a marimo install or uninstall now."""
    job = runtime.installs
    return bool(job.running and job.snapshot()["tool"] == TOOL)


def _plugin_status(runtime: Any) -> str | None:
    host = runtime.plugins
    if host is None:
        return None
    try:
        return str(host.registry.state(TOOL).status)
    except KeyError:
        return None
    except Exception:  # a broken record must not hide the card
        logger.warning("Could not read the marimo plugin state.", exc_info=True)
        return None


def _unknown(status: ToolStatus) -> str | None:
    if status.availability != UNKNOWN:
        return None
    return "uv-not-found" if status.uv is None else (status.problem or "status-unknown")


def _install_reason(status: ToolStatus, running: bool, editor: bool) -> str | None:
    """Return why Install cannot start now, or ``None``. The checks run in this order."""
    if (reason := _unknown(status)) is not None:
        return reason
    if status.availability == READY:
        return "already-installed"
    if running:
        return "install-running"
    return "editor-running" if editor else None


def _uninstall_reason(status: ToolStatus, running: bool, editor: bool) -> str | None:
    """Return why Uninstall cannot start now, or ``None``. The checks run in this order."""
    if (reason := _unknown(status)) is not None:
        return reason
    if status.availability == NOT_INSTALLED:
        return "not-installed"
    if not status.installed_by_card:
        return "not-installed-by-app"
    if running:
        return "install-running"
    return "editor-running" if editor else None


def describe_tool(runtime: Any) -> tuple[ToolStatus, dict[str, Any]]:
    """Return the marimo state and its ``ExternalTool`` entry. May run ``uv tool dir``.

    Raises:
        RuntimeError: The shipped marimo manifest is missing.
    """
    detector = runtime.tools
    tested = detector.tested()
    status = detector.detect()
    running, editor = runtime.installs.running, editor_running(runtime)
    install_reason = _install_reason(status, running, editor)
    uninstall_reason = _uninstall_reason(status, running, editor)
    return status, {
        "id": TOOL,
        "name": "marimo",
        "purpose": PURPOSE,
        "availability": status.availability,
        "version": status.version,
        "jupytext": status.jupytext,
        "executable": status.executable,
        "requirement": requirement(tested),
        "install_command": install_command(tested),
        "uninstall_command": UNINSTALL_COMMAND,
        "installable": install_reason is None,
        "install_reason": install_reason,
        "install_caution": install_caution(status, tested),
        "uninstallable": uninstall_reason is None,
        "uninstall_reason": uninstall_reason,
        "plugin_status": _plugin_status(runtime),
    }


def tool_entries(runtime: Any) -> list[dict[str, Any]]:
    """Return the ``tools`` list of ``GET /v1/integrations``.

    A package without a readable marimo manifest (for example a zip import)
    gives an empty list, so the extras still show.
    """
    try:
        return [describe_tool(runtime)[1]]
    except RuntimeError:
        logger.warning("The shipped marimo manifest is missing; the marimo card is hidden.")
        return []


def _conflict(reason: str) -> JSONResponse:
    body = {"status": "error", "message": redact(TOOL_REASONS[reason]), "reason": reason}
    return JSONResponse(body, status_code=409, headers=API_HEADERS)


async def _start(runtime: Any, tool: str, action: str) -> Response:
    if tool != TOOL:
        return error_response(404, UNKNOWN_TOOL)
    async with admitted(runtime):
        status, entry = await run_in_threadpool(describe_tool, runtime)
    reason = entry["install_reason" if action == "install" else "uninstall_reason"]
    if reason is not None or status.uv is None:
        return _conflict(reason or "uv-not-found")
    detector = runtime.tools
    if action == "install":
        argv, goal = install_argv(status.uv, detector.tested()), READY
    else:
        argv, goal = uninstall_argv(status.uv), NOT_INSTALLED

    def check() -> bool:
        return bool(detector.detect().availability == goal)

    try:
        runtime.installs.start_tool(
            TOOL, argv, check, action=action, redactor=getattr(runtime.engine, "redact", None)
        )
    except InstallRunning:
        return _conflict("install-running")
    return ok({"install": runtime.installs.snapshot()}, 202)


@router.post("/integrations/tools/{tool}/install", operation_id="installTool")
async def install_tool(_: ManageScope, tool: ToolParam, runtime: RuntimeDep) -> Response:
    """Start installing marimo with jupytext into its own ``uv tool`` environment."""
    return await _start(runtime, tool, "install")


@router.post("/integrations/tools/{tool}/uninstall", operation_id="uninstallTool")
async def uninstall_tool(_: ManageScope, tool: ToolParam, runtime: RuntimeDep) -> Response:
    """Start removing the marimo tool environment that the card installed."""
    return await _start(runtime, tool, "uninstall")
