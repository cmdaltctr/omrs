"""Decision model routes: list, save, delete and Test (ADR-110, task 4.1).

``GET /v1/settings/decision-models`` lists the valid ``decision_models``
entries of ``omrs.jsonc`` with their key state, never a key. ``PUT`` and
``DELETE`` write one entry through the settings writer
(``config.settings_maps_write``), which keeps comments, checks the revision and
refuses a literal key. ``POST .../test`` runs the model checks, which contact
the entry's server, so it needs ``manage`` like the writes. A bearer credential
never passes ``manage``. Nothing contacts a model on a list.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi import Path as PathParam
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ....config.rules import ENTRY_NAME_PATTERN
from ....config.settings_file import SettingsFile
from ....config.settings_file_write import SettingsFileError
from ....config.settings_maps import DECISION_MODELS, DOCUMENT_ROUTERS
from ....config.settings_maps_write import write_map_entries
from ..engine_access import ReadScope, require_session
from ..errors import API_HEADERS, error_response
from ..router_maps import (
    CONFLICT_REASONS,
    NOT_FOUND,
    TEST_NOT_FOUND,
    decision_model_list,
    decision_test_body,
)
from ..security import Principal, redact
from ..settings_store import refusal_response
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
EntryName = Annotated[str, PathParam(max_length=64, pattern=f"^{ENTRY_NAME_PATTERN.pattern}$")]
WHAT = "decision model"


class DecisionModelSave(BaseModel):
    """Body of ``PUT /v1/settings/decision-models/{name}``.

    Attributes:
        entry: The entry's fields. The settings writer checks each one.
        revision: The ``revision`` the page last read.
    """

    model_config = ConfigDict(extra="forbid")

    entry: dict[str, Any]
    revision: Annotated[str, Field(max_length=128)]


class RouterMapRevision(BaseModel):
    """Body of a delete: the ``revision`` the page last read."""

    model_config = ConfigDict(extra="forbid")

    revision: Annotated[str, Field(max_length=128)]


def conflict(reason: str, **words: str) -> JSONResponse:
    """Return a 409 with a fixed *reason* and its plain line, filled from *words*."""
    message = CONFLICT_REASONS[reason].format(**words)
    body = {"status": "error", "message": redact(message), "reason": reason}
    return JSONResponse(body, status_code=409, headers=API_HEADERS)


def store_of(request: Request) -> Any:
    """Return the server's ``SettingsFileStore``."""
    return request.app.state.mcp_http.store


def raw_entry(store: Any, map_key: str, name: str) -> Any:
    """Return the raw JSON value of one map entry, or ``None`` when the file lacks it.

    A broken entry is found too, so the page can still remove it.
    """
    return store.raw([f"{map_key}.{name}"])[f"{map_key}.{name}"]


async def write(store: Any, changes: dict[str, Any], revision: str, **options: Any) -> Any:
    """Run the map writer off the event loop. Returns ``None``, or the refusal response."""
    try:
        await run_in_threadpool(
            lambda: write_map_entries(
                changes, revision=revision, directory=store.directory, **options
            )
        )
    except SettingsFileError as exc:
        return refusal_response(exc)
    return None


async def _list(store: Any) -> Response:
    file: SettingsFile = await run_in_threadpool(store.read)
    return ok(decision_model_list(file))


@router.get("/settings/decision-models", operation_id="listDecisionModels")
async def list_decision_models(_: ReadScope, request: Request) -> Response:
    """Return the valid decision models of ``omrs.jsonc``. Contacts no model."""
    return await _list(store_of(request))


@router.put("/settings/decision-models/{name}", operation_id="saveDecisionModel")
async def save_decision_model(
    _: ManageScope, name: EntryName, body: DecisionModelSave, request: Request
) -> Response:
    """Add or replace one decision model in ``omrs.jsonc``.

    The list never returns the key reference, so an edit that leaves ``key``
    out keeps the saved reference. An explicit ``key: null`` clears it.
    """
    store = store_of(request)
    entry = dict(body.entry)
    if "key" not in entry:
        saved = await run_in_threadpool(raw_entry, store, DECISION_MODELS, name)
        if isinstance(saved, dict) and isinstance(saved.get("key"), str):
            entry["key"] = saved["key"]
    refused = await write(store, {f"{DECISION_MODELS}.{name}": entry}, body.revision)
    return refused or await _list(store)


@router.delete("/settings/decision-models/{name}", operation_id="deleteDecisionModel")
async def delete_decision_model(
    _: ManageScope, name: EntryName, body: RouterMapRevision, request: Request
) -> Response:
    """Remove one decision model; refused while a router names it."""
    store = store_of(request)
    if await run_in_threadpool(raw_entry, store, DECISION_MODELS, name) is None:
        return error_response(404, NOT_FOUND.format(what=WHAT))
    routers = await run_in_threadpool(store.raw, [DOCUMENT_ROUTERS])
    users = sorted(
        router_name
        for router_name, entry in (routers[DOCUMENT_ROUTERS] or {}).items()
        if isinstance(entry, dict) and entry.get("model") == name
    )
    if users:
        return conflict("in-use", who=f"The router {', '.join(users)}", what=WHAT)
    refused = await write(store, {f"{DECISION_MODELS}.{name}": None}, body.revision)
    return refused or await _list(store)


@router.post("/settings/decision-models/{name}/test", operation_id="testDecisionModel")
async def run_decision_model_test(_: ManageScope, name: EntryName, request: Request) -> Response:
    """Run the model checks of one entry: quantisation, one text request, the smoke test."""
    file: SettingsFile = await run_in_threadpool(store_of(request).read)
    if name not in file.maps.get(DECISION_MODELS, {}):
        return error_response(404, TEST_NOT_FOUND)
    from .... import compose_decision  # lazy: builds the adapters only on request

    now = _FileSettings(file)
    result = await run_in_threadpool(compose_decision.test_decision_model, now, name)
    return ok(decision_test_body(name, result))


class _FileSettings:
    """The router maps as ``omrs.jsonc`` holds them now, shaped like ``Settings``.

    The Test button checks the entry the page just saved, which the launch
    settings do not hold yet.
    """

    def __init__(self, file: SettingsFile) -> None:
        self.decision_models = dict(file.maps.get(DECISION_MODELS, {}))
        self.document_routers = dict(file.maps.get(DOCUMENT_ROUTERS, {}))
        self.document_router = str(file.values.get("document_router") or "")
