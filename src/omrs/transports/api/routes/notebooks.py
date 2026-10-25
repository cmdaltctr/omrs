"""Experiment notebook routes (experiments-in-web-workspace D2 and D5).

Every project is a notebook with the id ``project:<project_id>``. User
notebooks group experiments from any project. Notebook writes change only the
user's own grouping, so they need the browser session with the ``read`` scope,
as chat folders do. A bearer credential never passes. A project notebook
cannot be renamed, deleted or changed (400). The routes delegate to
``omrs.core.workspace.experiment_notebooks``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....core.workspace import experiment_notebooks as notebooks
from ....core.workspace.experiment_library import MAX_FOLDER_NAME, MAX_NOTEBOOK_NAME
from ....core.workspace.experiment_pages import ExperimentRefusedError
from ....integrations.workspace_sqlite.experiment_library import DuplicateError
from ..engine_access import RuntimeDep
from .experiment_library import LibraryDep, ReadSession, call, conflict, invalid, unknown
from .graphs import ok

router = APIRouter(prefix="/v1")


class NotebookBody(BaseModel):
    """Body of ``POST /v1/notebooks`` and ``PATCH /v1/notebooks/{notebook_id}``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_NOTEBOOK_NAME)


class EntryBody(BaseModel):
    """Body of ``PUT /v1/notebooks/{notebook_id}/entries`` (schema ``NotebookEntryRequest``)."""

    model_config = ConfigDict(extra="forbid")

    project_id: Annotated[str, Field(min_length=1, max_length=128)]
    folder: Annotated[str, Field(min_length=1, max_length=MAX_FOLDER_NAME)]


def _rename(library: Any, notebook_id: str, name: str) -> dict[str, Any]:
    notebooks.refuse_project_notebook(notebook_id)
    library.rename_notebook(notebook_id, name)
    return notebooks.user_notebook(library, notebook_id)


def _delete(library: Any, notebook_id: str) -> None:
    notebooks.refuse_project_notebook(notebook_id)
    library.delete_notebook(notebook_id)


def _create(library: Any, name: str) -> dict[str, Any]:
    return notebooks.user_notebook(library, library.create_notebook(name)["notebook_id"])


@router.get("/notebooks", operation_id="listNotebooks")
async def list_notebooks(_: ReadSession, runtime: RuntimeDep, library: LibraryDep) -> Response:
    """List the project notebooks first, then the user notebooks."""
    return ok({"notebooks": await call(runtime, notebooks.list_notebooks, library)})


@router.post("/notebooks", status_code=201, operation_id="createNotebook")
async def create_notebook(
    _: ReadSession, body: NotebookBody, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """Create a user notebook. The name must be unique."""
    try:
        notebook = await call(runtime, _create, library, body.name)
    except DuplicateError as exc:
        return conflict(runtime, exc)
    except ValueError as exc:
        return invalid(runtime, exc)
    return ok({"notebook": notebook}, 201)


@router.get("/notebooks/{notebook_id}", operation_id="getNotebook")
async def get_notebook(
    _: ReadSession, notebook_id: str, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """Return a notebook and its entries. An entry whose folder is gone is ``missing``."""
    try:
        return ok(await call(runtime, notebooks.get_notebook, library, notebook_id))
    except KeyError:
        return unknown(runtime)


@router.patch("/notebooks/{notebook_id}", operation_id="renameNotebook")
async def rename_notebook(
    _: ReadSession, notebook_id: str, body: NotebookBody, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """Rename a user notebook."""
    try:
        notebook = await call(runtime, _rename, library, notebook_id, body.name)
    except KeyError:
        return unknown(runtime)
    except DuplicateError as exc:
        return conflict(runtime, exc)
    except ValueError as exc:
        return invalid(runtime, exc)
    return ok({"notebook": notebook})


@router.delete("/notebooks/{notebook_id}", operation_id="deleteNotebook")
async def delete_notebook(
    _: ReadSession, notebook_id: str, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """Delete a user notebook and its entries. No experiment file changes."""
    try:
        await call(runtime, _delete, library, notebook_id)
    except KeyError:
        return unknown(runtime)
    except ExperimentRefusedError as exc:
        return invalid(runtime, exc)
    return ok({"removed": True})


@router.put("/notebooks/{notebook_id}/entries", operation_id="addNotebookEntry")
async def add_entry(
    _: ReadSession, notebook_id: str, body: EntryBody, runtime: RuntimeDep, library: LibraryDep
) -> Response:
    """Add one experiment to a user notebook. Adding it again keeps one entry."""
    try:
        entry = await call(
            runtime, notebooks.add_entry, library, notebook_id, body.project_id, body.folder
        )
    except KeyError:
        return unknown(runtime)
    except ExperimentRefusedError as exc:
        return invalid(runtime, exc)
    return ok({"entry": entry})


@router.delete(
    "/notebooks/{notebook_id}/entries/{project_id}/{folder}", operation_id="removeNotebookEntry"
)
async def remove_entry(
    _: ReadSession,
    notebook_id: str,
    project_id: str,
    folder: str,
    runtime: RuntimeDep,
    library: LibraryDep,
) -> Response:
    """Remove one entry from a user notebook, also when its folder is missing."""
    try:
        await call(runtime, notebooks.remove_entry, library, notebook_id, project_id, folder)
    except KeyError:
        return unknown(runtime)
    except ExperimentRefusedError as exc:
        return invalid(runtime, exc)
    return ok({"removed": True})
