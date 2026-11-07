"""Routes of the llama.cpp Router panel: settings and control (one-llamacpp-router, D2, D9).

``GET /v1/llamacpp/router`` reports the router state, the saved settings with their
source and lock, and the list models (``llamacpp_router_view``). ``PUT`` writes the
program, the router mode, the address and the two limits to ``omrs.jsonc``; it may
send the ``revision`` it read. ``POST`` start, stop and restart control the shared
``router`` runtime through the process's runtime manager (``run_in_threadpool``).
The list entries have their own routes (``llamacpp_router_models``) and the pinned
build has its own (``llamacpp_router_install``).

Every write and control route needs the browser session with ``manage``. Changing
the program or the router mode also needs ``credentials``. With the mode
``external`` Start, Stop and Restart do nothing and give 409. No route returns the
log file or any text of the child process.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....config import Settings
from ....config.llamacpp_router_rules import router_url_problem
from ....config.settings_file_write import SettingsFileError
from ....integrations.llamacpp_runtime import rules
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import error_response
from ..llamacpp_chat_rule import BINARY_RULE, reasoned
from ..llamacpp_server import RouterControl
from ..provider_state import EngineRefused, validate_int
from ..settings_store import refusal_response
from .experiments import ManageScope
from .graphs import ok
from .llamacpp_router_downloads import downloads_needed
from .llamacpp_router_view import (
    FIELD_IDS,
    INT_SPECS,
    LoadedRouter,
    load_router,
    saved_fields,
    status_body,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

CHOICES = ("external", "managed")
CHOICE_RULE = "The router mode must be external or managed."
CREDENTIALS_RULE = "Changing the program or the router mode needs the credentials scope."
MODEL_RETIRED = "Models are set in the model table, not here."
IDLE_SLEEP_RETIRED = (
    "idle_sleep is retired. OMRS stops an idle llama.cpp server after a fixed 10 minutes."
)
EXTERNAL_LINE = (
    "OMRS does not run the router: the mode is the Llama app or another server you run. "
    "Choose OMRS's own llama-server first."
)
_REFUSED = "The running engine cannot take this change. Restart the server to apply it."
#: Keys that change what OMRS launches, so they need ``credentials``.
_CREDENTIAL_KEYS = frozenset({"binary", "router_server"})


class RouterBody(BaseModel):
    """Body of ``PUT /v1/llamacpp/router``. A key that is absent stays as it is; ``null`` clears.

    ``model`` is retired: it stays here only so a body that holds it gets the plain
    "Models are set in the model table." instead of a generic validation message.
    """

    model_config = ConfigDict(extra="forbid")

    binary: str | None = Field(None, max_length=2048)
    model: str | None = Field(None, max_length=2048)
    router_server: str | None = Field(None, max_length=16)
    router_url: str | None = Field(None, max_length=2048)
    models_max: int | float | str | bool | None = None
    memory_margin_mib: int | float | str | bool | None = None
    revision: Annotated[str, Field(max_length=128)] | None = None


async def reject_idle_sleep(request: Request) -> None:
    """Refuse a body that holds ``idle_sleep`` with 400 and the fixed 10-minute idle stop.

    The key is not in the contract, so the body model forbids it and would give a generic
    validation message. This check reads the raw body after the session check, before the
    model validates it. A body that is not a JSON object passes on to the model.
    """
    try:
        data = await request.json()
    except ValueError:
        return
    if isinstance(data, dict) and "idle_sleep" in data:
        raise HTTPException(status_code=400, detail=IDLE_SLEEP_RETIRED)


def control_of(request: Request) -> RouterControl:
    """Return the adapter of this app."""
    return request.app.state.llamacpp_router  # type: ignore[no-any-return]


def store_of(request: Request) -> Any:
    """Return the server's ``SettingsFileStore``."""
    return request.app.state.mcp_http.store


async def respond(runtime: Any, request: Request) -> Response:
    """Return the status body of the saved values in force."""
    loaded = await run_in_threadpool(load_router, runtime, store_of(request))
    status = await run_in_threadpool(control_of(request).status, loaded.config)
    return ok(status_body(loaded, status))


def _external_conflict() -> Response:
    return reasoned(409, EXTERNAL_LINE, "external-server")


@router.get("/llamacpp/router", operation_id="getLlamacppRouter")
async def get_router(_: ReadScope, request: Request, runtime: RuntimeDep) -> Response:
    """Return the state, the saved settings and the model list. Starts nothing."""
    async with admitted(runtime):
        return await respond(runtime, request)


def check_value(key: str, value: object) -> tuple[str | None, str | None]:
    """Check one value. Returns ``(text to save or None to clear, rule broken or None)``."""
    if value is None:
        return None, None
    if key in INT_SPECS:
        return validate_int(INT_SPECS[key], value)
    text = str(value).strip() if isinstance(value, str) else ""
    if key == "binary":
        return (text, None) if rules.check_binary(text) else (None, BINARY_RULE)
    if key == "router_server":
        return (text, None) if text in CHOICES else (None, CHOICE_RULE)
    return text, None  # router_url: judged with the mode, under the lock


def _address_rule(loaded: LoadedRouter, updates: dict[str, Any]) -> str | None:
    """Return the rule that the mode and the address in force after the write break."""
    if "llamacpp_router_server" not in updates and "llamacpp_router_url" not in updates:
        return None

    def after(path: str, current: str) -> str:
        if path not in updates:
            return current
        return str(updates[path] or Settings.model_fields[path].default)

    mode = after("llamacpp_router_server", loaded.config.mode)
    url = after("llamacpp_router_url", loaded.config.url)
    return router_url_problem(mode, url)


@router.put("/llamacpp/router", operation_id="saveLlamacppRouter")
async def save_router(
    principal: ManageScope,
    _retired: Annotated[None, Depends(reject_idle_sleep)],
    body: RouterBody,
    request: Request,
    runtime: RuntimeDep,
) -> Response:
    """Save the program, the router mode, the address and the two limits.

    400 for a broken rule (the message names the rule, never the value) or a
    ``model`` key or an ``idle_sleep`` key (see :func:`reject_idle_sleep`), 403 when the
    body sets the program or the router mode and the session lacks the ``credentials``
    scope, 409 for a locked field or a stale ``revision``. A running router keeps running.
    """
    if "model" in body.model_fields_set:
        return error_response(400, MODEL_RETIRED)
    keys = [k for k in FIELD_IDS if k in body.model_fields_set]
    if not keys:
        return error_response(400, "Send at least one setting to save.")
    if _CREDENTIAL_KEYS & set(keys) and "credentials" not in principal.scopes:
        return error_response(403, CREDENTIALS_RULE)
    updates: dict[str, str | int | None] = {}
    for key in keys:
        text, rule = check_value(key, getattr(body, key))
        if rule:
            return error_response(400, rule)
        updates[FIELD_IDS[key]] = int(text) if key in INT_SPECS and text else text
    state = runtime.providers
    if state is None:
        return error_response(404, "Provider settings are not available.")
    async with admitted(runtime), state.lock:
        loaded = await run_in_threadpool(load_router, runtime, store_of(request))
        saved = saved_fields(loaded.settings)
        for key in keys:
            if saved[key]["locked"]:
                return error_response(409, saved[key]["lock_reason"] or "This field is locked.")
        if rule := _address_rule(loaded, updates):
            return error_response(400, rule)
        try:
            await run_in_threadpool(state.save_fields, runtime.engine, updates, body.revision)
        except SettingsFileError as exc:
            return refusal_response(exc)
        except EngineRefused:
            return error_response(409, _REFUSED)
        return await respond(runtime, request)


@router.get("/llamacpp/router/downloads-needed", operation_id="getLlamacppRouterDownloads")
async def get_downloads_needed(_: ManageScope, request: Request, runtime: RuntimeDep) -> Response:
    """List the models with no file and their download sizes, for the dialog before a Start.

    Reads the model host, so it needs the browser session with ``manage`` (as the model
    search does). It contacts the host only here, only for an entry with no file, and
    starts and writes nothing. 409 ``external-server`` when the mode is ``external``.
    """
    async with admitted(runtime):
        loaded = await run_in_threadpool(load_router, runtime, store_of(request))
        if loaded.config.mode != "managed":
            return _external_conflict()
        return ok(await run_in_threadpool(downloads_needed, loaded.config))


@router.post("/llamacpp/router/start", operation_id="startLlamacppRouter")
async def start_router(_: ManageScope, request: Request, runtime: RuntimeDep) -> Response:
    """Start the router with the saved values.

    409 ``external-server`` when the mode is ``external``. A refusal of the launch rules
    is state ``failed`` with one fixed reason. A router that already runs is left alone.
    """
    async with admitted(runtime):
        loaded = await run_in_threadpool(load_router, runtime, store_of(request))
        if loaded.config.mode != "managed":
            return _external_conflict()
        status = await run_in_threadpool(control_of(request).start, loaded.config)
        return ok(status_body(loaded, status))


@router.post("/llamacpp/router/stop", operation_id="stopLlamacppRouter")
async def stop_router(_: ManageScope, request: Request, runtime: RuntimeDep) -> Response:
    """Operator stop of the recorded router. With none recorded, nothing is signalled."""
    async with admitted(runtime):
        loaded = await run_in_threadpool(load_router, runtime, store_of(request))
        if loaded.config.mode != "managed":
            return _external_conflict()
        status = await run_in_threadpool(control_of(request).stop, loaded.config)
        return ok(status_body(loaded, status))


@router.post("/llamacpp/router/restart", operation_id="restartLlamacppRouter")
async def restart_router(_: ManageScope, request: Request, runtime: RuntimeDep) -> Response:
    """Stop the router, then start it with the saved values."""
    async with admitted(runtime):
        loaded = await run_in_threadpool(load_router, runtime, store_of(request))
        if loaded.config.mode != "managed":
            return _external_conflict()
        status = await run_in_threadpool(control_of(request).restart, loaded.config)
        return ok(status_body(loaded, status))
