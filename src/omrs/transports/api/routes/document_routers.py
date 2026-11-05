"""Document router routes: list, save, rename and delete (ADR-110, task 4.1).

``GET /v1/settings/document-routers`` lists the valid ``document_routers``
entries of ``omrs.jsonc``, whether each will run, and the saved user profiles
that name each one. The writes go through the settings writer
(``config.settings_maps_write``) and need a browser session with ``manage``.
A rename is a delete of the old name and a save of the new one in one write,
so the router name never enters a source digest. A delete or rename is refused
while the saved ``document_router`` or a saved user profile names the router,
and when the saved profiles cannot be read.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Annotated, Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....config.settings_file import SettingsFile
from ....config.settings_maps import DOCUMENT_ROUTERS, entry_name_problem
from ..engine_access import ReadScope
from ..errors import error_response
from ..router_maps import NOT_FOUND, ProfilesUnreadable, profile_routers, router_list
from .decision_models import (
    EntryName,
    ManageScope,
    RouterMapRevision,
    conflict,
    raw_entry,
    store_of,
    write,
)
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

WHAT = "router"
HOST_SETTING = "The host router setting (document_router)"


class DocumentRouterSave(BaseModel):
    """Body of ``PUT /v1/settings/document-routers/{name}``.

    Attributes:
        entry: The router's fields. The settings writer checks each one.
        revision: The ``revision`` the page last read.
    """

    model_config = ConfigDict(extra="forbid")

    entry: dict[str, Any]
    revision: Annotated[str, Field(max_length=128)]


class DocumentRouterRename(BaseModel):
    """Body of ``POST /v1/settings/document-routers/{name}/rename``."""

    model_config = ConfigDict(extra="forbid")

    new_name: Annotated[str, Field(max_length=64)]
    revision: Annotated[str, Field(max_length=128)]


def _catalogue(request: Request) -> Any:
    """Return the saved-profile catalogue.

    Raises:
        ProfilesUnreadable: The server has not started its profile service yet.
    """
    service = getattr(getattr(request.app.state, "runtime", None), "profiles", None)
    if service is None:
        raise ProfilesUnreadable
    return service.catalogue


def _users(request: Request) -> dict[str, list[str]]:
    """Return router name to profile titles; raises :class:`ProfilesUnreadable`."""
    return profile_routers(_catalogue(request))


async def _list(request: Request) -> Response:
    store = store_of(request)
    file: SettingsFile = await run_in_threadpool(store.read)
    try:
        users = await run_in_threadpool(_users, request)
    except ProfilesUnreadable:
        logger.warning("The saved profiles could not be read for the router list.")
        users = {}
    return ok(router_list(file, users))


async def _in_use(request: Request, name: str) -> Response | None:
    """Return the 409 that blocks removing router *name*, or ``None``."""
    file: SettingsFile = await run_in_threadpool(store_of(request).read)
    if file.values.get("document_router") == name:
        return conflict("in-use", who=HOST_SETTING, what=WHAT)
    try:
        users = await run_in_threadpool(_users, request)
    except ProfilesUnreadable:
        return conflict("profiles-unreadable")
    if users.get(name):
        return conflict("in-use", who=f"The saved profile {', '.join(users[name])}", what=WHAT)
    return None


def _naming(request: Request) -> Any:
    """Return the writer's profile check, run again under the write lock."""

    def profiles_naming(name: str) -> Collection[str]:
        return _users(request).get(name, [])

    return profiles_naming


@router.get("/settings/document-routers", operation_id="listDocumentRouters")
async def list_document_routers(_: ReadScope, request: Request) -> Response:
    """Return the valid routers of ``omrs.jsonc``. Contacts no model."""
    return await _list(request)


@router.put("/settings/document-routers/{name}", operation_id="saveDocumentRouter")
async def save_document_router(
    _: ManageScope, name: EntryName, body: DocumentRouterSave, request: Request
) -> Response:
    """Add or replace one router in ``omrs.jsonc``."""
    refused = await write(
        store_of(request), {f"{DOCUMENT_ROUTERS}.{name}": body.entry}, body.revision
    )
    return refused or await _list(request)


@router.delete("/settings/document-routers/{name}", operation_id="deleteDocumentRouter")
async def delete_document_router(
    _: ManageScope, name: EntryName, body: RouterMapRevision, request: Request
) -> Response:
    """Remove one router; refused while the host setting or a saved profile names it."""
    store = store_of(request)
    if await run_in_threadpool(raw_entry, store, DOCUMENT_ROUTERS, name) is None:
        return error_response(404, NOT_FOUND.format(what=WHAT))
    blocked = await _in_use(request, name)
    if blocked is not None:
        return blocked
    changes = {f"{DOCUMENT_ROUTERS}.{name}": None}
    refused = await write(store, changes, body.revision, profiles_naming=_naming(request))
    return refused or await _list(request)


@router.post("/settings/document-routers/{name}/rename", operation_id="renameDocumentRouter")
async def rename_document_router(
    _: ManageScope, name: EntryName, body: DocumentRouterRename, request: Request
) -> Response:
    """Move one router to ``new_name`` in one write; the digests do not change."""
    store = store_of(request)
    fields = await run_in_threadpool(raw_entry, store, DOCUMENT_ROUTERS, name)
    if fields is None:
        return error_response(404, NOT_FOUND.format(what=WHAT))
    rule = entry_name_problem(DOCUMENT_ROUTERS, body.new_name)
    if rule is not None:
        return error_response(400, f"new_name: {rule}")
    if await run_in_threadpool(raw_entry, store, DOCUMENT_ROUTERS, body.new_name) is not None:
        return conflict("name-taken")
    blocked = await _in_use(request, name)
    if blocked is not None:
        return blocked
    changes = {f"{DOCUMENT_ROUTERS}.{name}": None, f"{DOCUMENT_ROUTERS}.{body.new_name}": fields}
    refused = await write(store, changes, body.revision, profiles_naming=_naming(request))
    return refused or await _list(request)
