"""The Mac stops the pod after a clean end (mac_watch35.py).

After a hash-checked final pull and a verified off-site copy, the watcher sends the stop:
``POST https://api.runpod.io/v2/pods/{id}/action`` with ``{"action":"stop"}`` (REST API v2,
the call that pod_test_session.sh also uses). It then reads ``GET /v2/pods/{id}`` every 10 s
for up to 3 min until the status is ``EXITED``. A failed POST or an unconfirmed stop falls
back to the old wait for the pod's own stop (the pod still stops itself when it sees PULLED).

The only action sent is ``stop``. The watcher never deletes or terminates a pod. The key
comes from ``runpod_ssh35.api_key()`` and goes in the Authorization header only: no message,
log line or file holds it.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

import runpod_ssh35

STOP_BODY = '{"action":"stop"}'
STOPPED = "EXITED"  # the status RunPod reports for a stopped pod
CONFIRM_S, CONFIRM_STEP_S = 3 * 60, 10  # read the status for this long, this far apart
STOP_WAIT_S, STOP_POLL_S = 5 * 60, 10  # fallback: wait for the pod's own stop


def post_stop(pod_id: str, key: str, opener: Callable[..., Any] = urllib.request.urlopen) -> None:
    """Send one stop request: the key in the Authorization header only."""
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers["User-Agent"] = "exp35-mac-watcher"
    url = runpod_ssh35.API + urllib.parse.quote(pod_id, safe="") + "/action"
    request = urllib.request.Request(  # noqa: S310 - fixed https host
        url, data=STOP_BODY.encode("utf-8"), headers=headers, method="POST"
    )
    with opener(request, timeout=30) as reply:
        reply.read()


def _why(error: Exception) -> str:
    return (
        f"HTTP {error.code}" if isinstance(error, urllib.error.HTTPError) else type(error).__name__
    )


def stop_via_api(
    pod_id: str,
    *,
    say: Callable[[str], None],
    now: Callable[[], float],
    pause: Callable[[float], None],
    post: Callable[[str, str], None] = post_stop,
    get: Callable[[str, str], Any] = runpod_ssh35.get_pod,
) -> bool:
    """Stop the pod through the API and wait for ``EXITED``; ``False`` when not confirmed."""
    try:
        key = runpod_ssh35.api_key()
    except runpod_ssh35.AddressError as error:  # the message never holds the key
        say(f"  Mac stop skipped: {error}")
        return False
    say(f"  Mac stop: POST {runpod_ssh35.API}{pod_id}/action {STOP_BODY}")
    try:
        post(pod_id, key)
    except (urllib.error.URLError, OSError, ValueError) as error:  # only the type goes out
        say(f"  Mac stop failed: {_why(error)}")
        return False
    start, status = now(), "unknown"
    while True:
        try:
            status = str(get(pod_id, key).get("status"))
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            pass  # a lost reply is tried again until the time is up
        if status == STOPPED:
            say(f"  Mac stop confirmed: pod status {STOPPED}")
            return True
        if now() - start >= CONFIRM_S:
            say(f"  Mac stop not confirmed after {CONFIRM_S // 60} min (last status {status})")
            return False
        pause(CONFIRM_STEP_S)


def finish(
    pod_id: str,
    w: Any,
    wait: Callable[[Callable[[], bool], float, float], bool | None],
    *,
    clean: bool,
    keep: bool,
    say: Callable[[str], None],
    now: Callable[[], float],
    pause: Callable[[float], None],
    stop: Callable[..., bool] = stop_via_api,
) -> str:
    """Return the pod-stop verdict: ``mac-api``, else what the pod's own stop did.

    *clean* is true for a ``done`` end with ``outputs == "ok"`` and no hold. The Mac stops
    the pod only then, and not when the chain kept it (``POD_KEPT``) or when a stage failed:
    the chain then stops or holds the pod itself. *keep* is not used for this decision.
    """
    # Any failed stage is left to the chain: it stops the pod or holds it (KEEP_POD_ON_FAIL),
    # so an --attach without the chain's keep flag cannot stop a pod the chain keeps.
    own = w.done and not w.kept and not w.stop_failed and not w.failed_stages
    if clean and own and stop(pod_id, say=say, now=now, pause=pause):
        return "mac-api"
    seen: bool | None = True
    ended = lambda: w.stop_sent or w.stop_failed or w.kept or not w.alive  # noqa: E731
    if not ended():
        say(f"waiting up to {STOP_WAIT_S // 60} min for the pod to stop itself")
        seen = wait(ended, STOP_WAIT_S, STOP_POLL_S)
    if w.kept:
        return "kept"
    if w.stop_failed or w.stop_sent:
        return "FAILED" if w.stop_failed else "sent"
    return "ssh-closed" if seen is None else "not-seen"
