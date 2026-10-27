"""Experiment project and library routes (experiments-in-web-workspace D1, D4 to D7).

The browser session adds a project folder that holds an ``experiments/``
directory, lists its experiments, reads their text files and creates new ones.
Adding a project and creating an experiment read or write files outside the
workspace, so they need the session-only ``manage`` scope. The reads need the
browser session. A bearer credential never passes. The routes delegate to
``omrs.core.workspace.experiment_pages`` and ``experiment_notebooks``, which
scan the folders again on each request.

* ``GET`` and ``POST /v1/experiment-projects``; ``DELETE .../{project_id}``.
* ``GET`` and ``POST /v1/experiment-projects/{project_id}/experiments``.
* ``GET .../experiments/{folder}`` and ``GET .../experiments/{folder}/files/{name}``.
* ``PUT .../experiments/{folder}/files/{name}`` saves ``protocol.md`` or the report
  (edit-experiment-files-in-library D4 and D6). It needs ``manage``.
"""

from __future__ import annotations

import threading
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .... import __version__
from ....core.experiment_records.record import Category, Purpose, Size
from ....core.workspace import experiment_file_edits as edits
from ....core.workspace import experiment_notebooks as notebooks
from ....core.workspace import experiment_pages as pages
from ....core.workspace.experiment_library import (
    MAX_PROJECT_NAME,
    MAX_PROJECT_PATH,
    ProjectPathError,
)
from ....integrations.workspace_sqlite.experiment_library import DuplicateError
from ..engine_access import RuntimeDep, admitted, require_session
from ..errors import API_HEADERS, error_response
from ..security import Principal
from .graphs import ok

router = APIRouter(prefix="/v1")

ReadSession = Annotated[Principal, Depends(require_session("read"))]
ManageSession = Annotated[Principal, Depends(require_session("manage"))]

_UNKNOWN = "That project, experiment or file does not exist."

#: Plain line for each 409 reason of ``writeExperimentFile``.
EDIT_REASONS: dict[str, str] = {
    "changed_on_disk": (
        "This file changed on disk after you opened it. "
        "Copy your text, select Reload, then add your changes again."
    ),
    "edit_log_unusable": (
        "edits.jsonl in this experiment folder is a link or not a regular file, "
        "so the app cannot record the edit. Replace it with a regular file."
    ),
}

# One lock per (project id, folder), so two saves to one folder never interleave.
_EDIT_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_EDIT_LOCKS_GUARD = threading.Lock()


class ProjectBody(BaseModel):
    """Body of ``POST /v1/experiment-projects`` (schema ``ExperimentProjectRequest``)."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=MAX_PROJECT_PATH)
    name: str = Field(min_length=1, max_length=MAX_PROJECT_NAME)


class NewExperimentBody(BaseModel):
    """Body of ``POST .../experiments`` (schema ``ProjectExperimentRequest``)."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    category: Category
    size: Size
    follow_up: str | None = Field(default=None, max_length=16)
    # An unknown value fails validation, whose message names both allowed values.
    purpose: Purpose = Purpose.OPTIMISATION


class FileWriteBody(BaseModel):
    """Body of ``PUT .../files/{name}`` (schema ``ExperimentFileWrite``)."""

    model_config = ConfigDict(extra="forbid")

    text: str
    base_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


def get_library(runtime: RuntimeDep) -> Any:
    """Route dependency returning the launch's project and notebook store.

    Raises:
        HTTPException: 503 when the server has no store.
    """
    if runtime.experiment_library is None:
        raise HTTPException(503, "The experiment library is not available in this server.")
    return runtime.experiment_library


LibraryDep = Annotated[Any, Depends(get_library)]


def unknown(runtime: Any) -> Response:
    """Return the 404 envelope for an unknown project, notebook, experiment or file."""
    return error_response(404, _UNKNOWN, redactor=runtime.engine.redact)


def invalid(runtime: Any, exc: ValueError) -> Response:
    """Return the 400 validation envelope with the refusal message."""
    return error_response(400, str(exc), error_type="validation", redactor=runtime.engine.redact)


def conflict(runtime: Any, exc: ValueError) -> Response:
    """Return the 409 envelope for a duplicate project root or notebook name."""
    return error_response(409, str(exc), redactor=runtime.engine.redact)


async def call(runtime: Any, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run blocking store or file work in the thread pool under runtime admission."""
    async with admitted(runtime):
        return await run_in_threadpool(fn, *args, **kwargs)


def _add_project(library: Any, path: str, name: str) -> dict[str, Any]:
    # The check and the count run before the store, so a failed add stores nothing.
    root, count = notebooks.check_new_project(path)
    stored = library.add_project(name, str(root))
    return {**stored, "available": True, "experiment_count": count}


def _listing(library: Any, project_id: str) -> dict[str, Any]:
    return notebooks.project_listing(library.get_project(project_id))


def _detail(library: Any, project_id: str, folder: str) -> dict[str, Any]:
    project = library.get_project(project_id)
    detail = pages.experiment_detail(notebooks.experiments_of(project), folder)
    return {"project": notebooks.project_view(project), **detail}


def _file(library: Any, project_id: str, folder: str, name: str) -> dict[str, Any]:
    # Refuse a bad name before the store or the disk is read (design D6).
    pages.check_name(name, "file name")
    pages.check_name(folder, "folder name")
    project = library.get_project(project_id)
    return pages.read_file(notebooks.experiments_of(project), folder, name)


def _edit_lock(project_id: str, folder: str) -> threading.Lock:
    with _EDIT_LOCKS_GUARD:
        return _EDIT_LOCKS.setdefault((project_id, folder), threading.Lock())


def _save(library: Any, project_id: str, folder: str, name: str, body: FileWriteBody) -> Any:
    # Refuse a bad name before the store or the disk is read (design D1).
    pages.check_name(name, "file name")
    pages.check_name(folder, "folder name")
    if name not in edits.EDITABLE_NAMES:
        raise pages.ExperimentRefusedError("The workspace edits only protocol.md and the report.")
    project = library.get_project(project_id)
    with _edit_lock(project_id, folder):
        return edits.save_file(
            notebooks.experiments_of(project),
            folder,
            name,
            body.text,
            body.base_revision,
            f"omrs web {__version__}",  # core cannot import the version (design D10)
        )


def _create(library: Any, project_id: str, body: NewExperimentBody) -> dict[str, Any]:
    project = library.get_project(project_id)
    return pages.new_experiment(
        notebooks.experiments_of(project),
        slug=body.slug,
        title=body.title,
        category=body.category,
        size=body.size,
        day=date.today(),
        follow_up=body.follow_up,
        purpose=body.purpose,
    )


@router.get("/experiment-projects", operation_id="listExperimentProjects")
async def list_projects(_: ReadSession, runtime: RuntimeDep, library: LibraryDep) -> Response:
    """List the projects, each checked again, with ``available`` and an experiment count."""

    def build() -> list[dict[str, Any]]:
        return [notebooks.project_view(project) for project in library.list_projects()]

    return ok({"projects": await call(runtime, build)})


@router.post("/experiment-projects", status_code=201, operation_id="addExperimentProject")
async def add_project(
    _: ManageSession, body: ProjectBody, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """Add a project folder after the path check of design D1."""
    try:
        project = await call(runtime, _add_project, library, body.path, body.name)
    except DuplicateError as exc:
        return conflict(runtime, exc)
    except (ProjectPathError, ValueError) as exc:
        return invalid(runtime, exc)
    return ok({"project": project}, 201)


@router.delete("/experiment-projects/{project_id}", operation_id="removeExperimentProject")
async def remove_project(
    _: ManageSession, project_id: str, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """Remove a project and its notebook entries. No file on disk changes."""
    try:
        await call(runtime, library.remove_project, project_id)
    except KeyError:
        return unknown(runtime)
    return ok({"removed": True})


@router.get("/experiment-projects/{project_id}/experiments", operation_id="listProjectExperiments")
async def list_experiments(
    _: ReadSession, project_id: str, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """List the experiments, reserved numbers and project-level findings of a project."""
    try:
        return ok(await call(runtime, _listing, library, project_id))
    except KeyError:
        return unknown(runtime)


@router.post(
    "/experiment-projects/{project_id}/experiments",
    status_code=201,
    operation_id="createProjectExperiment",
)
async def create_experiment(
    _: ManageSession,
    project_id: str,
    body: NewExperimentBody,
    runtime: RuntimeDep,
    library: LibraryDep,
) -> Response:
    """Create an experiment folder, then rewrite the project index when it has markers."""
    try:
        created = await call(runtime, _create, library, project_id, body)
    except KeyError:
        return unknown(runtime)
    except pages.ExperimentRefusedError as exc:
        return invalid(runtime, exc)
    return ok(created, 201)


@router.get(
    "/experiment-projects/{project_id}/experiments/{folder}", operation_id="getProjectExperiment"
)
async def get_experiment(
    _: ReadSession, project_id: str, folder: str, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """Return one experiment, its top-level files and the names in ``output/``."""
    try:
        return ok(await call(runtime, _detail, library, project_id, folder))
    except (KeyError, OSError):  # an unreadable folder reads as unknown
        return unknown(runtime)
    except pages.ExperimentRefusedError as exc:
        return invalid(runtime, exc)


@router.get(
    "/experiment-projects/{project_id}/experiments/{folder}/files/{name}",
    operation_id="readExperimentFile",
)
async def read_file(
    _: ReadSession,
    project_id: str,
    folder: str,
    name: str,
    runtime: RuntimeDep,
    library: LibraryDep,
) -> Response:
    """Return the text of one top-level file as JSON, at most 1 MiB (design D6)."""
    try:
        return ok(await call(runtime, _file, library, project_id, folder, name))
    except (KeyError, OSError):  # an unreadable folder reads as unknown
        return unknown(runtime)
    except pages.ExperimentRefusedError as exc:
        return invalid(runtime, exc)


@router.put(
    "/experiment-projects/{project_id}/experiments/{folder}/files/{name}",
    operation_id="writeExperimentFile",
)
async def write_file(
    _: ManageSession,
    project_id: str,
    folder: str,
    name: str,
    body: FileWriteBody,
    runtime: RuntimeDep,
    library: LibraryDep,
) -> Response:
    """Save ``protocol.md`` or the report, then log the save in ``edits.jsonl`` (D4)."""
    try:
        return ok(await call(runtime, _save, library, project_id, folder, name, body))
    except (KeyError, pages.ExperimentNotFoundError):
        return unknown(runtime)
    except pages.ExperimentRefusedError as exc:
        return invalid(runtime, exc)
    except edits.ExperimentEditConflictError as exc:
        payload = {"status": "error", "message": EDIT_REASONS[exc.reason], "reason": exc.reason}
        return JSONResponse(payload, status_code=409, headers=API_HEADERS)
    except edits.ExperimentEditFailedError as exc:
        return error_response(500, str(exc), redactor=runtime.engine.redact)
