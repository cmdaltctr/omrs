"""Make one router model ready before its request is timed (design D8; task 4.2).

The router answers ``/health`` with no model loaded. Before the first request
to model X in a lease, OMRS reads ``GET /v1/models``; when X is not
``loaded`` it sends ``POST /models/load`` and polls until ``loaded`` or
``failed``, up to :data:`MODEL_LOAD_TIMEOUT_SECONDS`. The caller's request
timeout starts only after this returns.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from . import process
from .model_reasons import ModelUnavailable

#: Longest wait for one model load, in seconds (design D8). Fixed, not a setting.
MODEL_LOAD_TIMEOUT_SECONDS = 300
#: Seconds between two status reads while a model loads.
LOAD_POLL_SECONDS = 0.5
_HTTP_TIMEOUT = 10.0


def router_models(url: str) -> dict[str, dict[str, object]]:
    """Return ``{model: status object}`` from ``GET /v1/models``; ``{}`` when unreachable."""
    status, body = process.http_get_json(f"{url.rstrip('/')}/v1/models", _HTTP_TIMEOUT)
    if status != 200 or not isinstance(body, dict):
        return {}
    found: dict[str, dict[str, object]] = {}
    for item in body.get("data") or []:
        if isinstance(item, dict) and isinstance(item.get("status"), dict):
            found[str(item.get("id"))] = item["status"]
    return found


def status_word(status: dict[str, object]) -> str:
    """Return the state word of one router ``status`` object.

    llama.cpp b11941 has no ``failed`` value. A load that failed reads ``unloaded``
    with ``failed: true`` and the child's ``exit_code`` (``server-models.cpp``,
    ``is_failed()`` in ``server-models.h``). The flag stays until the next load
    starts, and a load that starts sets ``loading`` first, so a read after a load
    was asked never shows an old failure.
    """
    if status.get("failed") is True:
        return "failed"
    return str(status.get("value"))


def model_state(url: str, model: str) -> str | None:
    """Return the state word of *model* (see :func:`status_word`), ``None`` when not listed."""
    status = router_models(url).get(model)
    return None if status is None else status_word(status)


def _post_load(url: str, model: str) -> int:
    request = urllib.request.Request(  # noqa: S310 - loopback router address
        f"{url.rstrip('/')}/models/load",
        data=json.dumps({"model": model}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as answer:  # noqa: S310
            return int(answer.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except (OSError, ValueError):
        return 0


def ensure_loaded(url: str, model: str) -> None:
    """Return once *model* is ``loaded`` on the router at *url*.

    Raises:
        ModelUnavailable: ``model-not-listed`` when the router does not list
            *model*; ``model-load-failed`` when the load fails, the load
            request is refused, or the wait passes
            :data:`MODEL_LOAD_TIMEOUT_SECONDS`.
    """
    state = model_state(url, model)
    if state == "loaded":
        return
    if state is None:
        raise ModelUnavailable(model, "model-not-listed")
    if state != "loading":
        answer = _post_load(url, model)
        if answer not in (200, 400):  # 400: another process started this load
            raise ModelUnavailable(model, "model-load-failed")
    deadline = time.monotonic() + MODEL_LOAD_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = model_state(url, model)
        if state == "loaded":
            return
        if state in ("failed", None):
            raise ModelUnavailable(model, "model-load-failed")
        time.sleep(LOAD_POLL_SECONDS)
    raise ModelUnavailable(model, "model-load-failed")


def reload_presets(url: str) -> bool:
    """Ask the router to re-read ``models.ini`` (``GET /models?reload=1``); return success."""
    status, _ = process.http_get_json(f"{url.rstrip('/')}/models?reload=1", _HTTP_TIMEOUT)
    return status == 200
