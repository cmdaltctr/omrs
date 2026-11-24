"""Find the direct SSH address of a RunPod pod for mac_watch35.py (P2, 2026-11-24).

The public IP and port of a new pod come 1 to 3 minutes after create. When the watcher
gets no ``--ssh-host``, it asks RunPod: ``GET https://api.runpod.io/v2/pods/{id}``
(REST API v2, operation ``getPod``, scope ``pods:read``; checked against
https://api.runpod.io/v2/openapi.json on 2026-11-24), every 15 s for up to 15 min.
The address is the ``runtime.ports`` entry with ``private`` 22 and ``type`` tcp, a
public IP and a public port, on a pod whose ``status`` is RUNNING. The RunPod SSH
proxy is never used: it carries a shell only, not scp.

This module only reads. It never creates, stops or deletes a pod. The key comes from
RUNPOD_API_KEY, else from ``apikey`` in ``~/.runpod/config.toml``. It goes into the
Authorization header only: no message, log line or file holds it.
"""

from __future__ import annotations

import ipaddress
import json
import os
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

API = "https://api.runpod.io/v2/pods/"
CONFIG = Path("~/.runpod/config.toml")
POLL_S, WAIT_S = 15, 15 * 60
_FATAL = {401: "the key was refused", 403: "the key may not read pods", 404: "no such pod"}


class AddressError(RuntimeError):
    """No usable direct SSH address. The message never holds the key."""


def api_key(env: Mapping[str, str] = os.environ, config: Path = CONFIG) -> str:
    """Return RUNPOD_API_KEY, else ``apikey`` from the RunPod config file."""
    if key := env.get("RUNPOD_API_KEY", "").strip():
        return key
    path = config.expanduser()
    try:
        key = str(tomllib.loads(path.read_text(encoding="utf-8")).get("apikey") or "").strip()
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        why = f"cannot be read ({type(error).__name__}) for its apikey"
    else:
        why = "holds no apikey"
    if not key:
        raise AddressError(f"RUNPOD_API_KEY is not set and {path} {why}; set either one")
    return key


def arg_problems(host: str | None, port: int | None) -> list[str]:
    """Return the problems of ``--ssh-host``/``--ssh-port``: both, or neither and a key."""
    if (host is None) != (port is None):
        return ["give --ssh-host and --ssh-port together, or neither (RunPod is asked)"]
    if host is None:
        try:
            api_key()
        except AddressError as error:
            return [str(error)]
    return []


def get_pod(pod_id: str, key: str, opener: Callable[..., Any] = urllib.request.urlopen) -> Any:
    """Return the pod record: one GET, the key in the Authorization header only."""
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    headers["User-Agent"] = "exp35-mac-watcher"
    url = API + urllib.parse.quote(pod_id, safe="")  # fixed https host: no file: or other scheme
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    with opener(request, timeout=30) as reply:
        return json.loads(reply.read().decode("utf-8"))


def _public(ip: Any) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def direct_address(pod: Mapping[str, Any]) -> tuple[str, int] | None:
    """Return (public IP, public port) of the pod's 22/tcp, or ``None`` while there is none."""
    if pod.get("status") != "RUNNING":
        return None
    for port in (pod.get("runtime") or {}).get("ports") or ():
        public = port.get("public")
        if port.get("private") == 22 and port.get("type") == "tcp" and type(public) is int:
            if _public(port.get("ip")):
                return port["ip"], public
    return None


def wait_for_address(
    pod_id: str,
    key: str,
    *,
    now: Callable[[], float],
    pause: Callable[[float], None],
    say: Callable[[str], None],
    get: Callable[[str, str], Any] | None = None,
    limit: float = WAIT_S,
    step: float = POLL_S,
) -> tuple[str, int]:
    """Poll the pod record until it shows a direct address; report each wait.

    Raises:
        AddressError: The key was refused or the pod is unknown (at once), or no
            public address came within *limit* seconds.
    """
    start = now()
    while True:
        try:
            pod = (get or get_pod)(pod_id, key)
            if found := direct_address(pod):
                return found
            why = f"status {pod.get('status')}, no public IP for 22/tcp"
        except urllib.error.HTTPError as error:
            if error.code in _FATAL:
                raise AddressError(f"RunPod API: HTTP {error.code}, {_FATAL[error.code]}") from None
            why = f"HTTP {error.code}"
        except (OSError, ValueError, AttributeError) as error:  # network, JSON or shape
            why = type(error).__name__
        if now() - start >= limit:
            raise AddressError(
                f"no public IP for 22/tcp after {limit / 60:g} min ({why}); "
                "the RunPod SSH proxy cannot carry scp, so the session cannot start"
            )
        say(f"  SSH address not ready yet ({why}); next check in {step:g} s")
        pause(step)


def find(
    args: Any, *, now: Callable[[], float], pause: Callable[[float], None], say: Callable
) -> tuple[str, int] | None:
    """Step 2b of mac_watch35.py: the address given, else the direct address RunPod reports.

    Returns ``None`` after a ``NO SSH ADDRESS`` line when RunPod gives none.
    """
    if args.ssh_host:
        return args.ssh_host, args.ssh_port
    say(f"step 2b: GET {API}{args.pod_id} every {POLL_S} s, up to {WAIT_S // 60} min, for 22/tcp")
    try:
        host, port = wait_for_address(args.pod_id, api_key(), now=now, pause=pause, say=say)
    except AddressError as error:
        say(f"NO SSH ADDRESS: {error}")
        return None
    say(f"  direct SSH address: {host}:{port}")
    return host, port
