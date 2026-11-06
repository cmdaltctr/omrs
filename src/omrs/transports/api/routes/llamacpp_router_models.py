"""Routes of the router model list: add, change and remove one entry (one-llamacpp-router, D3, D7).

``PUT /v1/llamacpp/router/models/{id}`` sets some fields of one ``llamacpp_models``
entry; a field that is absent stays and ``null`` removes it. It adds an entry or
replaces one, so Use this model (task 7.2) is a ``PUT`` with ``model``, ``file`` and
the ``sha256`` of the download status. ``DELETE`` removes an entry that holds no role.
Both write ``omrs.jsonc`` through ``write_llamacpp_models`` (revision check, atomic
replace), and the first page edit writes the shipped list plus the change.

A change to ``model``, ``file``, ``projector`` or a SHA-256, and a removal, need
``credentials``: they decide which file the router loads. A change to ``preset``
needs ``manage`` only. A bearer credential never passes. After a save the router
that runs with the saved arguments reloads only the changed model (design D7). A
save never changes a role setting.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....config.llamacpp_models import ID_PATTERN
from ....config.settings_file_write import SettingsFileError
from ....config.settings_maps_write import write_llamacpp_models
from ..engine_access import RuntimeDep, admitted
from ..errors import error_response
from ..llamacpp_chat_rule import reasoned
from ..settings_store import refusal_response
from .experiments import ManageScope
from .llamacpp_router import control_of, respond, store_of
from .llamacpp_router_entry import EntryChange, EntryRefused, merge_entry
from .llamacpp_router_view import LoadedRouter, load_router, role_arguments

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

EntryId = Annotated[str, PathParam(max_length=40, pattern=f"^{ID_PATTERN.pattern}$")]
CREDENTIALS_RULE = (
    "Changing a model name, a model file or a SHA-256, or removing an entry, "
    "needs the credentials scope."
)
IN_USE_LINE = "This entry holds a role. Choose another model for the role in Settings first."
NOT_FOUND = "There is no model entry with this id."
#: Entry fields whose change decides which file the router loads.
_CREDENTIAL_FIELDS = frozenset({"model", "file", "projector", "sha256", "projector_sha256"})


class EntryBody(BaseModel):
    """Body of ``PUT /v1/llamacpp/router/models/{id}``. Absent stays; ``null`` removes."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(None, max_length=200)
    file: str | None = Field(None, max_length=2048)
    projector: str | None = Field(None, max_length=2048)
    sha256: str | None = Field(None, max_length=64)
    projector_sha256: str | None = Field(None, max_length=64)
    preset: dict[str, Any] | None = None
    revision: Annotated[str, Field(max_length=128)] | None = None


def _write(request: Request, changes: dict[str, Any], revision: str | None) -> None:
    store = store_of(request)
    write_llamacpp_models(changes, revision=revision, directory=store.directory)


async def _applied(runtime: Any, request: Request) -> Response:
    """Apply the reload rule to a running router, then answer with the new status."""
    loaded = await run_in_threadpool(load_router, runtime, store_of(request))
    await run_in_threadpool(control_of(request).apply_models, loaded.config)
    return await respond(runtime, request)


@router.put("/llamacpp/router/models/{id}", operation_id="saveLlamacppRouterModel")
async def save_model(
    principal: ManageScope,
    id: EntryId,  # noqa: A002 - the path parameter is named by the contract
    body: EntryBody,
    request: Request,
    runtime: RuntimeDep,
) -> Response:
    """Add an entry or change some fields of one. Answers with the router status.

    400 for a broken rule (``preset-key-unknown``, ``preset-invalid`` or ``role-mismatch``
    carry a ``reason``), 403 when the body changes the name, a file or a SHA-256 and the
    session lacks ``credentials``, 409 when ``omrs.jsonc`` changed since ``revision``.
    """
    entry_id = id
    sent = {name: getattr(body, name) for name in body.model_fields_set if name != "revision"}
    if _CREDENTIAL_FIELDS & set(sent) and "credentials" not in principal.scopes:
        return error_response(403, CREDENTIALS_RULE)
    state = runtime.providers
    if state is None:
        return error_response(404, "Provider settings are not available.")
    async with admitted(runtime), state.lock:
        loaded = await run_in_threadpool(load_router, runtime, store_of(request))
        change = EntryChange(sent, managed=loaded.config.mode == "managed")
        try:
            entry = await run_in_threadpool(
                merge_entry,
                entry_id,
                loaded.config.entries,
                change,
                role_arguments(loaded.settings, loaded.file),
            )
            await run_in_threadpool(_write, request, {entry_id: entry}, body.revision)
        except EntryRefused as refused:
            if refused.reason:
                return reasoned(400, str(refused), refused.reason)
            return error_response(400, str(refused))
        except SettingsFileError as exc:
            return refusal_response(exc)
        return await _applied(runtime, request)


def _held_roles(loaded: LoadedRouter, entry_id: str) -> bool:
    return bool(loaded.roles.roles.get(entry_id))


@router.delete("/llamacpp/router/models/{id}", operation_id="deleteLlamacppRouterModel")
async def delete_model(
    principal: ManageScope,
    id: EntryId,  # noqa: A002 - the path parameter is named by the contract
    request: Request,
    runtime: RuntimeDep,
    revision: Annotated[str | None, Query(max_length=128)] = None,
) -> Response:
    """Remove an entry that holds no role. 404 for an unknown id, 409 ``in-use`` for a role."""
    entry_id = id
    if "credentials" not in principal.scopes:
        return error_response(403, CREDENTIALS_RULE)
    state = runtime.providers
    if state is None:
        return error_response(404, "Provider settings are not available.")
    async with admitted(runtime), state.lock:
        loaded = await run_in_threadpool(load_router, runtime, store_of(request))
        if entry_id not in loaded.config.entries:
            return error_response(404, NOT_FOUND)
        if _held_roles(loaded, entry_id):
            return reasoned(409, IN_USE_LINE, "in-use")
        try:
            await run_in_threadpool(_write, request, {entry_id: None}, revision)
        except SettingsFileError as exc:
            return refusal_response(exc)
        return await _applied(runtime, request)
