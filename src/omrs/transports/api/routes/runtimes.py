"""Routes of the local model runtimes (managed-llamacpp-runtimes D8, D11).

``GET /v1/runtimes`` lists the runtimes in force: Chat, embeddings and one OCR
runtime for each OCR route whose engine declares one. It reads the runtime
state files, the recorded process's memory and a non-blocking lock attempt;
it starts, stops and writes nothing. ``POST /v1/runtimes/{runtime_id}/stop``
is an operator stop. It needs a browser session with ``manage``, so a bearer
token never reaches it. Both call the process's runtime manager (on
``app.state.runtime_manager``) through ``run_in_threadpool``. No route returns
server output.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from .... import compose_runtimes
from ..engine_access import ReadScope, RuntimeDep
from ..errors import API_HEADERS, error_response
from ..security import redact
from .experiments import ManageScope

router = APIRouter(prefix="/v1")

#: The plain line of each 409 reason (``transports/api/AGENTS.md`` rule 4).
CONFLICT_REASONS = {
    "external-runtime": (
        "OMRS does not run this server: it is a server you run yourself. "
        "Stop it where you started it."
    ),
}
NOT_FOUND = "No runtime has this id."


def _values(runtime: Any) -> Any:
    return runtime.providers.values if runtime is not None and runtime.providers else None


def _json(body: dict[str, Any]) -> JSONResponse:
    """A success body as the contract shapes it: no ``status`` field."""
    return JSONResponse(body, headers=API_HEADERS)


@router.get("/runtimes", operation_id="listRuntimes")
async def list_runtimes(_: ReadScope, request: Request, runtime: RuntimeDep) -> Response:
    """Return one item per runtime in force. Starts nothing and writes nothing."""
    manager = request.app.state.runtime_manager
    items = await run_in_threadpool(compose_runtimes.list_runtimes, _values(runtime), manager)
    return _json({"runtimes": items})


@router.post("/runtimes/{runtime_id}/stop", operation_id="stopRuntime")
async def stop_runtime(
    _: ManageScope, runtime_id: str, request: Request, runtime: RuntimeDep
) -> Response:
    """Stop a managed runtime (operator stop); return its item after the stop.

    404 for an id that is not in the list (a malformed id never is); 409 ``external-runtime``
    for an external runtime, with no signal sent.
    """
    values = _values(runtime)
    spec = await run_in_threadpool(compose_runtimes.find_runtime, runtime_id, values)
    if spec is None:
        return error_response(404, NOT_FOUND)
    if spec.mode == "external":
        body = {
            "status": "error",
            "message": redact(CONFLICT_REASONS["external-runtime"]),
            "reason": "external-runtime",
        }
        return JSONResponse(body, status_code=409, headers=API_HEADERS)
    manager = request.app.state.runtime_manager
    await run_in_threadpool(manager.stop, runtime_id)
    items = await run_in_threadpool(compose_runtimes.list_runtimes, values, manager)
    return _json(next(item for item in items if item["id"] == runtime_id))
