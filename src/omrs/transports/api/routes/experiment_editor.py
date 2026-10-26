"""Open a Library experiment in marimo (open-experiment-in-marimo, design D3 to D5).

``POST /v1/experiment-projects/{project_id}/experiments/{folder}/editor``
needs the browser session with the ``manage`` scope and ``consent: true`` on
every call. A bearer credential never launches. The request names no path,
flag or argument: the project comes from the Library record, the folder must
be a listed experiment, and the notebook is always ``analysis.marimo.py``
inside it.

The checks run cheapest first, in the order of the design D5 table. The
notebook is written only after every check passes, just before the launch.
``omrs.core.workspace.experiment_editor`` does the file checks and the
notebook preparation; the plugin supervisor converts and launches. The
kernel runs in ``<project root>/.venv`` (full access). The editor access
token is returned once in the response body and never logged.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, StrictBool

from ....core.plugins.editor import KernelEnvironment, PluginLaunchError
from ....core.plugins.manifest import PROJECT_ENVIRONMENT
from ....core.plugins.shipped import empty_notebook_text
from ....core.workspace import experiment_editor as editor
from ....core.workspace import experiment_notebooks as notebooks
from ....core.workspace import experiment_pages as pages
from ....core.workspace.experiment_library import ProjectPathError, check_project_path
from ..engine_access import RuntimeDep, require_session
from ..errors import API_HEADERS, error_response
from ..lifespan import PluginHost
from ..security import Principal, redact
from .experiment_library import LibraryDep, call, invalid, unknown
from .experiments import TRUST_NOTICE
from .graphs import ok

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")

ManageSession = Annotated[Principal, Depends(require_session("manage"))]

#: The plugin a Library launch uses.
PLUGIN = "marimo"
#: Plain line for each 409 reason; a refusal may carry its own text instead.
EDITOR_REASONS: dict[str, str] = {
    "editor_unavailable": (
        "marimo is not ready. Register it in Experiments, Code editor, and run a check."
    ),
    "editor_unsupported": (
        "The registered marimo manifest cannot open Library experiments. "
        "Register the manifest that OMRS ships again."
    ),
    "no_project_environment": (
        "This project has no .venv folder. Run `uv sync` (or `python -m venv .venv`) "
        "in the project folder, then open again."
    ),
    "python_mismatch": "The project's Python version differs from marimo's.",
    "project_config_runs_on_open": (
        "The project's pyproject.toml makes marimo run cells on open. Turn it off, then open again."
    ),
    "notebook_not_regular": "analysis.marimo.py is a link or not a regular file. Remove it.",
    "editor_running": "marimo already runs for this experiment. Use it, or stop it first.",
    "converter_missing": (
        "marimo needs jupytext to convert analysis.py. Run "
        '`uv tool install "marimo>=0.25.1,<0.26" --with jupytext`, then open again.'
    ),
    "conversion_failed": "marimo could not convert analysis.py.",
    "no_free_port": (
        "Ports 2719 to 2721 are busy. Close the program that uses them, then open again."
    ),
    "launch_failed": "marimo did not start. Check the plugin in Experiments, Code editor.",
}

# One Library launch at a time, so two opens cannot convert or launch one notebook twice.
_LAUNCH_LOCK = threading.Lock()


class ExperimentEditorBody(BaseModel):
    """Body of the open route (schema ``ExperimentEditorRequest``)."""

    model_config = ConfigDict(extra="forbid")

    consent: StrictBool


class _Refused(Exception):
    def __init__(self, reason: str, message: str | None = None, **extra: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message = message or EDITOR_REASONS[reason]
        self.extra = extra


def _refusal(runtime: Any, refused: _Refused) -> Response:
    message = redact(runtime.engine.redact(refused.message))
    body = {"status": "error", "message": message, "reason": refused.reason, **refused.extra}
    return JSONResponse(body, status_code=409, headers=API_HEADERS)


def _running(host: PluginHost, project_id: str, folder: str) -> str | None:
    live = {session.launch_id for session in host.editors.sessions()}
    for launch_id, place in host.editor_experiments.items():
        if place == (project_id, folder) and launch_id in live:
            return launch_id
    return None


def _manifest(host: PluginHost) -> Any:
    try:
        state = host.registry.state(PLUGIN)
    except KeyError:
        raise _Refused("editor_unavailable") from None
    if not state.launchable:
        raise _Refused("editor_unavailable", f"marimo cannot start: {state.message}")
    if PROJECT_ENVIRONMENT not in state.manifest.capabilities:
        raise _Refused("editor_unsupported")
    return state


def _converter(host: PluginHost) -> editor.Converter:
    def convert(source: Path, output: Path) -> tuple[int, str]:
        result = host.editors.convert(PLUGIN, source, output)
        return result.returncode, result.output_tail

    return convert


def _open(runtime: Any, library: Any, project_id: str, folder: str) -> dict[str, Any]:
    host: PluginHost | None = runtime.plugins
    project = library.get_project(project_id)  # KeyError: 404
    try:
        root = check_project_path(project["root"])
    except ProjectPathError:
        raise KeyError(project_id) from None
    path = pages.experiment_folder(notebooks.experiments_of(project), folder)
    if host is None:
        raise _Refused("editor_unavailable")
    state = _manifest(host)
    try:
        # Checks run in the order of the design D5 table.
        environment = editor.check_project_environment(root, Path(state.executable))
        editor.check_runs_on_open(path)
        editor.notebook_exists(path)
        if editor.needs_conversion(path) and state.manifest.convert is None:
            raise _Refused("editor_unsupported")
    except editor.EditorRefusal as exc:
        raise _Refused(exc.reason, exc.message) from None
    running = _running(host, project_id, folder)
    if running is not None:
        raise _Refused("editor_running", launch_id=running)
    scratch = runtime.config.workspace / "run" / "convert"
    try:
        prepared = editor.prepare_notebook(
            path, convert=_converter(host), scratch_parent=scratch, template=empty_notebook_text()
        )
    except editor.EditorRefusal as exc:
        if exc.output_tail:
            logger.warning(
                "marimo conversion failed (%s):\n%s",
                exc.reason,
                redact(runtime.engine.redact(exc.output_tail)),
            )
        raise _Refused(exc.reason, exc.message) from None
    try:
        session = host.editors.open(
            PLUGIN,
            prepared.path,
            consent=True,
            kernel_environment=KernelEnvironment(environment.venv),
        )
    except KeyError:  # the registration went away after the check
        _discard_new(prepared)
        raise _Refused("editor_unavailable") from None
    except PluginLaunchError as exc:
        _discard_new(prepared)
        reason = exc.reason if exc.reason in EDITOR_REASONS else "launch_failed"
        message = str(exc) if reason == "editor_unavailable" else None
        raise _Refused(reason, message) from None
    host.editor_experiments[session.launch_id] = (project_id, folder)
    return {
        "launch_id": session.launch_id,
        "plugin": session.plugin,
        "project_id": project_id,
        "folder": folder,
        "notebook": editor.NOTEBOOK_NAME,
        "notebook_state": prepared.state,
        "source_newer": prepared.source_newer,
        "environment": {
            "kind": "project",
            "python": environment.python,
            "marimo_in_project": environment.marimo_in_project,
            "shadowed": list(environment.shadowed),
        },
        "url_without_token": f"http://{session.host}:{session.port}/",
        "token_delivery": {"method": "response_body_once", "token": session.token},
        "trust_notice": TRUST_NOTICE,
    }


def _discard_new(prepared: editor.PreparedNotebook) -> None:
    """Remove a notebook this request made when the launch then fails.

    A refused launch leaves the experiment folder as it was. An existing
    notebook is the user's file and is never removed.
    """
    if prepared.state != "existing":
        prepared.path.unlink(missing_ok=True)


def _locked_open(runtime: Any, library: Any, project_id: str, folder: str) -> dict[str, Any]:
    with _LAUNCH_LOCK:
        return _open(runtime, library, project_id, folder)


@router.post(
    "/experiment-projects/{project_id}/experiments/{folder}/editor",
    status_code=201,
    operation_id="openExperimentEditor",
)
async def open_experiment_editor(
    _: ManageSession,
    project_id: str,
    folder: str,
    body: ExperimentEditorBody,
    runtime: RuntimeDep,
    library: LibraryDep,
) -> Response:
    """Open the experiment's ``analysis.marimo.py`` in marimo after consent.

    The response carries the editor access token once
    (``token_delivery.token``); the URL never holds it.
    """
    if not body.consent:
        return error_response(
            403,
            "Opening marimo runs the notebook with your full access; consent is required.",
        )
    try:
        pages.check_name(folder, "folder name")
        opened = await call(runtime, _locked_open, runtime, library, project_id, folder)
    except _Refused as refused:
        return _refusal(runtime, refused)
    except (KeyError, OSError):  # unknown project, unavailable folder or unlisted experiment
        return unknown(runtime)
    except pages.ExperimentRefusedError as exc:
        return invalid(runtime, exc)
    return ok(opened, 201)
