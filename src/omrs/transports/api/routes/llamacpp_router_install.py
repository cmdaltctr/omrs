"""Routes that provision the pinned llama.cpp build (one-llamacpp-router, D12; task 7.1).

``POST /v1/llamacpp/router/install`` starts the one provisioning job: download the
pinned archives, check their SHA-256, unpack, run ``--version`` (and ``--list-devices``
for CUDA) and place ``llama-server`` in the OMRS data folder. The body may name the
flavour (``cpu`` or ``cuda`` on Linux x86-64). ``GET`` reports the pinned build, the
flavour that fits this host, the choices, the program in place and the job.

The job calls ``provision.install_pinned_build`` (the one place that knows the
pins) in a daemon thread, one job at a time. It starts no server and changes no
setting. A failure is one fixed ``reason`` of ``ProvisionError`` and its line.
Both routes need the browser session; the install needs ``manage``.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from ....integrations.llamacpp_runtime import pins, provision
from ..engine_access import ReadScope, RuntimeDep, admitted, require_session
from ..errors import error_response
from ..llamacpp_chat_rule import reasoned
from ..security import Principal, redact
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
BUSY_LINE = "A llama.cpp install is already running. Wait for it to end."
MACOS_LINE = "The flavour does not apply on macOS: Apple silicon has one build."
#: The reason of a failure that no ``ProvisionError`` explains.
FAILED = "failed"


class InstallBody(BaseModel):
    """Body of ``POST /v1/llamacpp/router/install``. No flavour means the detected one."""

    model_config = ConfigDict(extra="forbid")

    flavour: Literal["cpu", "cuda"] | None = None


@dataclass
class ProvisionJob:
    """State and runner of the one install on this server. The state lives in memory.

    Attributes:
        state: ``idle``, ``running``, ``succeeded`` or ``failed``.
        flavour: The flavour asked for (``None`` before a job or for the detected one).
        line: The last progress line.
        reason: The fixed reason of a failure.
        message: The line of the failure.
    """

    state: str = "idle"
    flavour: str | None = None
    line: str | None = None
    reason: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        """Whether a job runs now."""
        with self._lock:
            return self.state == "running"

    def start(self, flavour: str | None) -> bool:
        """Start the job in a daemon thread. Return ``False`` when one already runs."""
        with self._lock:
            if self.state == "running":
                return False
            self.state, self.flavour, self.line = "running", flavour, None
            self.reason = self.message = None
        threading.Thread(target=self._run, args=(flavour,), daemon=True).start()
        return True

    def _say(self, line: str) -> None:
        with self._lock:
            self.line = line

    def _run(self, flavour: str | None) -> None:
        try:
            provision.install_pinned_build(flavour, self._say)
        except provision.ProvisionError as exc:
            self._end("failed", exc.reason, str(exc))
        except Exception as exc:  # noqa: BLE001 - one fixed reason; the type is logged
            logger.warning("llama.cpp install failed: %s", type(exc).__name__)
            self._end("failed", FAILED, "The install failed.")
        else:
            self._end("succeeded", None, None)

    def _end(self, state: str, reason: str | None, message: str | None) -> None:
        with self._lock:
            self.state, self.reason = state, reason
            self.message = None if message is None else redact(message)

    def snapshot(self) -> dict[str, Any]:
        """Return the job in the ``LlamacppInstallJob`` shape."""
        with self._lock:
            return {
                "state": self.state,
                "flavour": self.flavour,
                "line": self.line,
                "reason": self.reason,
                "message": self.message,
            }


def job_of(request: Request) -> ProvisionJob:
    """Return the one job of this app, made on first use."""
    state = request.app.state
    job = getattr(state, "llamacpp_install", None)
    if job is None:
        job = state.llamacpp_install = ProvisionJob()
    return job  # type: ignore[no-any-return]


def detected_flavour() -> str | None:
    """Return the flavour that fits this host, or ``None`` when no build is pinned for it."""
    try:
        return provision.detect_flavour()
    except pins.NotSupported:
        return None


def build_body(job: ProvisionJob) -> dict[str, Any]:
    """Return the body of ``GET /v1/llamacpp/router/install``."""
    detected = detected_flavour()
    return {
        "build": pins.LLAMA_TAG,
        "detected": detected,
        "choices": [] if detected in (None, "metal") else ["cpu", "cuda"],
        "installed_path": provision.resolve_server_binary("") or None,
        "job": job.snapshot(),
    }


@router.get("/llamacpp/router/install", operation_id="getLlamacppBuild")
async def get_build(_: ReadScope, request: Request, runtime: RuntimeDep) -> Response:
    """Return the pinned build, the detected flavour, the choices and the install job."""
    async with admitted(runtime):
        return ok(build_body(job_of(request)))


@router.post("/llamacpp/router/install", operation_id="installLlamacppBuild")
async def install_build(
    _: ManageScope, body: InstallBody, request: Request, runtime: RuntimeDep
) -> Response:
    """Start the install job: 202, 400 for a flavour macOS does not take, or 409 ``busy``."""
    async with admitted(runtime):
        if body.flavour is not None and detected_flavour() == "metal":
            return error_response(400, MACOS_LINE)
        job = job_of(request)
        if not job.start(body.flavour):
            return reasoned(409, BUSY_LINE, "busy")
        return ok(build_body(job), 202)
