"""A second, third or fifth OMRS client for the shared runtime manager tests.

The tests start this file as a process (``python client.py``). It reads one
JSON command per line from standard input and answers one JSON line per
command on standard output. Each answer is flushed at once, so a test can
drive two clients in lockstep.

Commands:

``{"cmd": "join", "spec": <spec dict>}``
    Join the runtime through the manager. The spec dict is the JSON form
    of ``RuntimeSpec`` (see ``omrs.integrations.llamacpp_runtime.spec``).
    Answers ``{"ok": true, "url_base": ..., "started": bool}`` or
    ``{"ok": false, "reason": ..., "reason_text": ...}``.
``{"cmd": "request", "path": "/v1/chat/completions", "body": {}, "timeout": 30}``
    Send one POST through the lease (the request lock runs inside). A
    connection refused by a crashed server is restarted once, as in the
    manager. Answers ``{"ok": true, "status": 200, "body": ...}``.
``{"cmd": "leave"}``
    Leave the lease (the server stops only when this was the last client).
``{"cmd": "ping"}``
    Answers ``{"ok": true, "pid": <pid>}`` without touching any runtime.
``{"cmd": "exit"}``
    Leaves the lease and ends the process with status 0.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    """Read command lines until ``exit`` or end of input."""
    lease = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            print(json.dumps({"ok": False, "reason": "bad-command"}), flush=True)
            continue
        cmd = payload.get("cmd")
        if cmd == "ping":
            import os

            print(json.dumps({"ok": True, "pid": os.getpid()}), flush=True)
        elif cmd == "join":
            if lease is not None:
                print(json.dumps({"ok": False, "reason": "already-joined"}), flush=True)
                continue
            try:
                from omrs.integrations.llamacpp_runtime.manager import RuntimeManager

                manager = RuntimeManager()
                lease = manager.lease_from_json(payload["spec"])
                outcome = lease.join()
            except Exception as error:  # noqa: BLE001 - reported as a line
                print(
                    json.dumps({"ok": False, "reason": "error", "reason_text": str(error)}),
                    flush=True,
                )
                lease = None
                continue
            if outcome.ok:
                print(
                    json.dumps(
                        {"ok": True, "url_base": outcome.url_base, "started": outcome.started}
                    ),
                    flush=True,
                )
            else:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "reason": outcome.reason,
                            "reason_text": outcome.reason_text,
                        }
                    ),
                    flush=True,
                )
                lease = None
        elif cmd == "request":
            if lease is None:
                print(json.dumps({"ok": False, "reason": "not-joined"}), flush=True)
                continue
            answer = lease.request(
                path=payload["path"], body=payload.get("body"), timeout=payload.get("timeout", 30)
            )
            print(json.dumps(answer, default=str), flush=True)
        elif cmd == "leave":
            if lease is not None:
                lease.leave()
                lease = None
            print(json.dumps({"ok": True}), flush=True)
        elif cmd == "exit":
            if lease is not None:
                lease.leave()
            print(json.dumps({"ok": True}), flush=True)
            return 0
        else:
            print(json.dumps({"ok": False, "reason": "bad-command"}), flush=True)
    if lease is not None:  # end of input: a normal client exit
        lease.leave()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
