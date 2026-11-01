"""A second, third or fifth OMRS client for the shared runtime manager tests.

The tests start this file as a process (``python client.py``). It reads one
JSON command per line from standard input and answers one JSON line per
command on standard output. Each answer is flushed at once, so a test can
drive several clients in lockstep. The process joins runtimes through the
real :class:`~omrs.integrations.llamacpp_runtime.manager.RuntimeManager`,
with its ``atexit`` hook, and turns SIGTERM into a normal exit as the CLI
entry point does.

Commands:

``{"cmd": "join", "spec": <spec dict>}``
    Join the runtime. Answers ``{"ok": true, "url_base": ..., "generation": n}``
    or ``{"ok": false, "reason": ..., "reason_text": ...}``.
``{"cmd": "request", "path": "/v1/chat/completions", "body": {}, "timeout": 30}``
    Send one POST through the lease (join on first use, request lock, crash
    restart once). Answers ``{"ok": true, "status": 200, "body": ...}``, or
    ``{"ok": false, "phase": "before"|"after"|"client", "reason": ...}``.
``{"cmd": "leave"}``
    Leave the lease (the server stops only when this was the last client).
``{"cmd": "stop", "runtime_id": "chat"}``
    Operator stop through this process's manager.
``{"cmd": "sweep"}``
    Run the ``omrs web`` start-up sweep; answers the stopped runtime ids.
``{"cmd": "config", ...}``
    Test hooks: ``idle_stop_seconds``, ``idle_check_seconds``,
    ``health_poll_seconds`` and ``request_lock`` (``false`` turns the
    request lock off).
``{"cmd": "ping"}``
    Answers ``{"ok": true, "pid": <pid>}`` without touching any runtime.
``{"cmd": "exit"}``
    Ends the process with status 0; the ``atexit`` hook leaves.
``{"cmd": "abandon"}``
    Ends the process at once with no leave (a test hook for an orphan).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _say(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, default=str), flush=True)


def _post(lease: Any, path: str, body: Any, timeout: float) -> dict[str, Any]:
    import httpx

    from omrs.integrations.llamacpp_runtime.manager import (
        RuntimeRequestFailed,
        RuntimeUnavailable,
    )

    def send(base_url: str) -> httpx.Response:
        return httpx.post(f"{base_url}{path}", json=body, timeout=timeout)

    try:
        answer = lease.request(send)
    except RuntimeUnavailable as error:
        return {"ok": False, "phase": "before", "reason": error.reason}
    except RuntimeRequestFailed as error:
        return {"ok": False, "phase": "after", "reason": error.reason}
    except httpx.TimeoutException:
        return {"ok": False, "phase": "client", "reason": "client-timeout"}
    except httpx.HTTPError as error:
        return {"ok": False, "phase": "client", "reason": type(error).__name__}
    return {"ok": True, "status": answer.status_code, "body": answer.json()}


def _config(payload: dict[str, Any]) -> None:
    from omrs.integrations.llamacpp_runtime import manager as manager_module
    from omrs.integrations.llamacpp_runtime import process

    if "idle_stop_seconds" in payload:
        manager_module.IDLE_STOP_SECONDS = float(payload["idle_stop_seconds"])
    if "idle_check_seconds" in payload:
        manager_module.IDLE_CHECK_SECONDS = float(payload["idle_check_seconds"])
    if "health_poll_seconds" in payload:
        process.HEALTH_POLL_SECONDS = float(payload["health_poll_seconds"])
    if payload.get("request_lock") is False:
        manager_module.RuntimeLease._uses_request_lock = lambda self: False  # type: ignore[method-assign]


def main() -> int:
    """Read command lines until ``exit`` or end of input."""
    from omrs.integrations.llamacpp_runtime.manager import (
        RuntimeManager,
        RuntimeUnavailable,
        install_sigterm_exit,
    )
    from omrs.integrations.llamacpp_runtime.spec import RuntimeSpec

    install_sigterm_exit()
    manager = RuntimeManager()
    lease = None
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            _say({"ok": False, "reason": "bad-command"})
            continue
        cmd = payload.get("cmd")
        if cmd == "ping":
            _say({"ok": True, "pid": os.getpid()})
        elif cmd == "config":
            _config(payload)
            _say({"ok": True})
        elif cmd == "join":
            lease = manager.lease(RuntimeSpec.from_dict(payload["spec"]))
            try:
                url = lease.join()
            except RuntimeUnavailable as error:
                _say({"ok": False, "reason": error.reason, "reason_text": error.reason_text})
                continue
            _say({"ok": True, "url_base": url, "generation": lease.generation})
        elif cmd == "request":
            if lease is None:
                _say({"ok": False, "reason": "not-joined"})
                continue
            _say(_post(lease, payload["path"], payload.get("body"), payload.get("timeout", 30)))
        elif cmd == "leave":
            if lease is not None:
                lease.leave()
            _say({"ok": True})
        elif cmd == "stop":
            _say({"ok": True, "stopped": manager.stop(payload["runtime_id"])})
        elif cmd == "sweep":
            _say({"ok": True, "stopped": manager.sweep()})
        elif cmd == "abandon":
            sys.stdout.flush()
            os._exit(0)
        elif cmd == "exit":
            _say({"ok": True})
            return 0
        else:
            _say({"ok": False, "reason": "bad-command"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
