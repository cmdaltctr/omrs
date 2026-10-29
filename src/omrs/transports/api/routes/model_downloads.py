"""Model search and download routes (ADR-106, design D9).

Five thin routes over ``core/providers/model_sources.py`` (the name rules),
``integrations/huggingface_models.py`` and ``integrations/ollama_pull.py``
(the outside requests) and the one :class:`ModelDownloadJob` on ``WebRuntime``.

* ``GET /v1/model-downloads/search`` and ``/files`` contact the model host.
* ``POST /v1/model-downloads`` checks names, free space and the gated flag,
  then starts the job. ``GET`` and ``DELETE /v1/model-downloads/current`` read
  and cancel it.

Every route needs the browser session with the ``manage`` scope, because each
call can make the server contact an outside host. A bearer credential never
passes. A provider takes part only when its registry entry declares a
``model_source``. A name that breaks a rule gets 400 before any request, file
path or process. The routes change no setting and return or log no token.
"""

from __future__ import annotations

import functools
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ....compose_providers import ProviderValues, provider_settings
from ....config.user_config import display_path
from ....core.providers import model_sources as rules
from ....core.providers.llm.connection import ConnectionDescriptor
from ....core.providers.model_sources import ModelSourceKind
from ....integrations import huggingface_models as hf_models
from ..engine_access import RuntimeDep, admitted, require_session
from ..errors import API_HEADERS, error_response
from ..lifespan import WebRuntime
from ..model_download_job import DownloadBusy, DownloadRequest
from ..provider_state import descriptor_of
from ..security import Principal, redact
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
ProviderQuery = Annotated[str, Query(max_length=64, pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
SearchText = Annotated[str, Query(min_length=1, max_length=100)]
RepoQuery = Annotated[str, Query(max_length=200)]

#: Seconds a cancel waits for the transfer to stop before it answers.
CANCEL_WAIT_SECONDS = 5.0

#: Plain-English line for each 409 reason of the start route.
REASONS: dict[str, str] = {
    "busy": "A model download is already running. Wait for it to end, or cancel it first.",
    "no-space": (
        "This download needs {needed} and the cache disk has {free} free. The app keeps "
        "1 GiB spare. Free some space, or set HF_HUB_CACHE to a folder on a larger disk."
    ),
    "gated": (
        "This repo is gated. Accept its licence on huggingface.co, set HF_TOKEN in the "
        "environment of omrs web, and restart the server."
    ),
}
_NOT_FOUND = "The repo, revision or quantisation was not found, or it holds no GGUF file."
_NOT_A_SOURCE = "This provider has no model source, so the app cannot search or download for it."

#: Built-in library names that a search puts first, by source kind.
_LIBRARY: dict[ModelSourceKind, Callable[[str], list[str]]] = {
    "huggingface-gguf": lambda _query: [],
    "ollama-pull": rules.filter_ollama_names,
}
#: How a Hugging Face repo id is written in the search results, by source kind.
_HF_ID_PREFIX: dict[ModelSourceKind, str] = {"huggingface-gguf": "", "ollama-pull": "hf.co/"}


class StartBody(BaseModel):
    """Body of ``POST /v1/model-downloads``. The rules for each field run in the route."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(max_length=64)
    repo: str | None = Field(default=None, max_length=200)
    revision: str | None = Field(default=None, min_length=40, max_length=40)
    label: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)


def _source(provider: str) -> tuple[ConnectionDescriptor, ModelSourceKind] | None:
    """Return the descriptor and source kind of *provider*, or ``None`` without a source."""
    descriptor = descriptor_of(provider)
    if descriptor is None or descriptor.model_source is None:
        return None
    return descriptor, descriptor.model_source


def _bad(message: str) -> Response:
    return error_response(400, message)


def _not_found(message: str = _NOT_FOUND) -> Response:
    body = {"status": "error", "message": redact(message), "reason": "not-found"}
    return JSONResponse(body, status_code=404, headers=API_HEADERS)


def _refused(reason: str, **sizes: str) -> Response:
    """Return the 409 body of the contract: ``status``, ``message`` and ``reason`` only."""
    message = redact(REASONS[reason].format(**sizes))
    body = {"status": "error", "message": message, "reason": reason}
    return JSONResponse(body, status_code=409, headers=API_HEADERS)


def _size(count: int) -> str:
    return f"{count / 1e9:.1f} GB"


def _free_bytes(folder: str) -> int:
    """Return the free bytes of the disk that holds *folder*, or its nearest existing parent."""
    probe = Path(folder).expanduser()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free


# ── Search and file list ─────────────────────────────────────────────────


def _library_result(name: str) -> dict[str, Any]:
    return {
        "id": name,
        "source": "ollama-library",
        "downloads": None,
        "likes": None,
        "gated": False,
        "last_modified": None,
    }


def _hub_result(hit: hf_models.RepoSummary, prefix: str) -> dict[str, Any]:
    return {
        "id": f"{prefix}{hit.id}",
        "source": "huggingface",
        "downloads": hit.downloads,
        "likes": hit.likes,
        "gated": hit.gated,
        "last_modified": hit.last_modified,
    }


@router.get("/model-downloads/search", operation_id="searchModels")
async def search_models(_: ManageScope, provider: ProviderQuery, q: SearchText) -> Response:
    """Search the model host of *provider*; 400 for a bad query or a provider with no source."""
    found = _source(provider)
    if found is None:
        return _bad(_NOT_A_SOURCE)
    kind = found[1]
    if not rules.is_valid_query(q):
        return _bad("The search text must be 1 to 100 characters with no control character.")
    results = [_library_result(name) for name in _LIBRARY[kind](q)]
    reason = None
    try:
        hits = await run_in_threadpool(hf_models.search_models, q)
    except hf_models.ModelHostError:
        reason = "network"
    else:
        results += [_hub_result(hit, _HF_ID_PREFIX[kind]) for hit in hits]
    logger.info("Model search for %s: %s", provider, reason or "answered")
    return ok({"provider": provider, "results": results, "reason": reason})


def _entries(files: tuple[tuple[str, int], ...]) -> list[dict[str, Any]]:
    grouped = rules.group_gguf_files(files)
    preferred = rules.preferred_label(grouped)
    return [
        {
            "label": entry.label,
            "files": list(entry.files),
            "size_bytes": entry.size_bytes,
            "recommended": entry.label == preferred,
            "closest_to_full": entry.label == rules.FULL_QUALITY_LABEL,
        }
        for entry in grouped
    ]


@router.get("/model-downloads/files", operation_id="listModelFiles")
async def list_model_files(_: ManageScope, provider: ProviderQuery, repo: RepoQuery) -> Response:
    """List the GGUF files of *repo* by quantisation, pinned to its current revision."""
    if _source(provider) is None:
        return _bad(_NOT_A_SOURCE)
    if not rules.is_valid_repo_id(repo):
        return _bad("The repo must be written org/name with letters, digits, '.', '_' and '-'.")
    try:
        found = await run_in_threadpool(hf_models.list_repo_files, repo)
    except hf_models.ModelHostError as exc:
        if exc.reason == "not-found":
            return _not_found()
        empty = {"repo": repo, "revision": None, "gated": False, "entries": [], "reason": "network"}
        return ok(empty)
    entries = _entries(found.files)
    if not entries:
        return _not_found()
    return ok(
        {
            "repo": repo,
            "revision": found.revision,
            "gated": found.gated,
            "entries": entries,
            "reason": None,
        }
    )


# ── Start ────────────────────────────────────────────────────────────────

#: Checks a start body and returns the request, or the response that refuses it.
Planner = Callable[
    [StartBody, WebRuntime, ConnectionDescriptor], Awaitable[DownloadRequest | Response]
]


def _failed_check(
    runtime: WebRuntime, base: DownloadRequest, exc: hf_models.ModelHostError
) -> Response:
    """Answer a Hugging Face check that failed: 404, 409 gated, or a job failed with network."""
    reason = exc.reason
    if reason == "not-found":
        return _not_found()
    if reason == "gated":
        return _refused("gated")
    runtime.model_downloads.fail(base, "network")
    return ok(runtime.model_downloads.snapshot(), 202)


async def _plan_gguf(
    body: StartBody, runtime: WebRuntime, descriptor: ConnectionDescriptor
) -> DownloadRequest | Response:
    """Plan a llama.cpp download: list the files at the revision, then gate and space checks."""
    if body.name is not None or None in (body.repo, body.revision, body.label):
        return _bad("A llama.cpp download needs repo, revision and label, and no name.")
    repo, revision, label = body.repo or "", body.revision or "", body.label or ""
    if not (
        rules.is_valid_repo_id(repo)
        and rules.is_valid_revision(revision)
        and rules.is_valid_label(label)
    ):
        return _bad("The repo, revision or label breaks the naming rules.")
    if runtime.model_downloads.running:
        return _refused("busy")
    folder = hf_models.hub_cache_folder()
    shown = rules.hf_model_value(repo, label)
    base = DownloadRequest(
        kind="huggingface-gguf",
        provider=body.provider,
        display=shown,
        model_value=shown,
        cache_folder=display_path(folder),
        repo=repo,
        revision=revision,
    )
    try:
        found = await run_in_threadpool(
            functools.partial(hf_models.list_repo_files, repo, revision=revision)
        )
    except hf_models.ModelHostError as exc:
        return _failed_check(runtime, base, exc)
    entry = next((e for e in rules.group_gguf_files(found.files) if e.label == label), None)
    if entry is None:
        return _not_found()
    token = os.environ.get("HF_TOKEN") or None
    if found.gated and token is None:
        return _refused("gated")
    try:
        needed = await run_in_threadpool(
            hf_models.bytes_to_download, repo, revision, entry.files, token=token
        )
    except hf_models.ModelHostError as exc:
        return _failed_check(runtime, base, exc)
    free = _free_bytes(folder)
    if not hf_models.has_room(needed, free):
        return _refused("no-space", needed=_size(needed), free=_size(free))
    return replace(base, files=entry.files, bytes_total=needed, token=token)


async def _address(runtime: WebRuntime, descriptor: ConnectionDescriptor) -> str:
    """Return the provider address in use: the saved value, else the environment, else default."""
    state = runtime.providers
    settings = await run_in_threadpool(
        provider_settings, lambda: state.values if state else ProviderValues()
    )
    spec = next(field for field in descriptor.fields if field.kind == "url")
    return str(getattr(settings, spec.settings_field))


def _pull_name(body: StartBody) -> str | Response:
    """Return the Ollama pull name of a start body, or the 400 for a body that breaks a rule."""
    if body.name is not None:
        if body.repo is not None or body.label is not None or body.revision is not None:
            return _bad("An Ollama library name takes no repo, revision or label.")
        return body.name
    if body.repo is None or body.label is None:
        return _bad("An Ollama download needs a name, or a repo and a label.")
    if not (rules.is_valid_repo_id(body.repo) and rules.is_valid_label(body.label)):
        return _bad("The repo or label breaks the naming rules.")
    if body.revision is not None and not rules.is_valid_revision(body.revision):
        return _bad("The revision must be 40 lower-case hexadecimal characters.")
    return rules.ollama_hf_name(body.repo, body.label)


async def _plan_pull(
    body: StartBody, runtime: WebRuntime, descriptor: ConnectionDescriptor
) -> DownloadRequest | Response:
    """Plan an Ollama pull. There is no size before the pull, so no space check runs."""
    name = _pull_name(body)
    if isinstance(name, Response):
        return name
    if not rules.is_valid_ollama_name(name):
        return _bad("The Ollama name breaks the naming rules.")
    base_url = await _address(runtime, descriptor)
    return DownloadRequest(
        kind="ollama-pull",
        provider=body.provider,
        display=name,
        model_value=name,
        name=name,
        base_url=base_url,
    )


#: The planner of each source kind. A third source adds one entry here.
_PLANNERS: dict[ModelSourceKind, Planner] = {
    "huggingface-gguf": _plan_gguf,
    "ollama-pull": _plan_pull,
}


@router.post("/model-downloads", operation_id="startModelDownload")
async def start_model_download(_: ManageScope, body: StartBody, runtime: RuntimeDep) -> Response:
    """Check the request and start the one download: 202, 400, 404, or 409 with a reason."""
    found = _source(body.provider)
    if found is None:
        return _bad(_NOT_A_SOURCE)
    descriptor, kind = found
    job = runtime.model_downloads
    async with admitted(runtime):
        try:
            planned = await _PLANNERS[kind](body, runtime, descriptor)
            if isinstance(planned, Response):
                return planned
            job.start(planned)
        except DownloadBusy:
            return _refused("busy")
    return ok(job.snapshot(), 202)


# ── Status and cancel ────────────────────────────────────────────────────


@router.get("/model-downloads/current", operation_id="getModelDownload")
async def get_model_download(_: ManageScope, runtime: RuntimeDep) -> Response:
    """Return the state of the running or last download, or ``idle``."""
    return ok(runtime.model_downloads.snapshot())


@router.delete("/model-downloads/current", operation_id="cancelModelDownload")
async def cancel_model_download(_: ManageScope, runtime: RuntimeDep) -> Response:
    """Stop the running download and wait up to 5 seconds. 409 when none runs."""
    job = runtime.model_downloads
    if not job.cancel():
        return error_response(409, "No model download is running.")
    await job.wait(CANCEL_WAIT_SECONDS)
    return ok(job.snapshot())
