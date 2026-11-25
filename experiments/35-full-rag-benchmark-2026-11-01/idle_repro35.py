"""Reproduce the router idle stop during Ragas (task 16.31, P17; A5 R-5, H-17; gap G14).

Saved pre-freeze cause, not proven: the Ragas embedding calls go straight to the
router, not through the OMRS lease, so the lease sees no request, leaves after
600 idle seconds (``IDLE_STOP_SECONDS``) and stops the router. Later calls fail
with ``APIConnectionError`` (5 of 20 rows scored).

This script starts (or joins) OMRS's managed router with the plan's 4B
embedding file only, like the pre-freeze path (Experiment 48
``router_config.start_router``). It sends one direct embedding call, waits
``--idle-seconds`` (default 660: the 600-second limit plus one 60-second idle
check) with no lease request, sends one more call, and writes
``<out>/idle.json`` (router build, wall and monotonic times, both results,
``/health``). ``--hold`` is the control: one router session
(``router_config.held``) spans both calls and the wait, so the router must stay up.

The calls use the ``openai`` client, the client that Ragas ``OpenAIEmbeddings``
wraps, with no retries. Exit 0: the record is written. Exit 2: the router did
not start or the first call failed (``reproduced`` is null; no wait).

Usage (test pod session; no key, no paid call)::

    uv run --no-sync python idle_repro35.py --out "$OUT_DIR/idle"
    uv run --no-sync python idle_repro35.py --out "$OUT_DIR/idle-held" --hold
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import arms  # noqa: E402
from experiments._lib import router_env  # noqa: E402

IDLE_LIMIT_SECONDS = 600  # omrs.integrations.llamacpp_runtime.manager.IDLE_STOP_SECONDS
DEFAULT_IDLE_SECONDS = 660
STOP_ERROR = "APIConnectionError"


def embed_entry(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the plan model of the 4B baseline embedder (the Ragas embedder)."""
    return next(m for m in plan["runtime"]["models"] if m["role"] == arms.EMBED_ROLES["4b"])


def router_values(entry: Mapping[str, Any], folder: Path, url: str) -> dict[str, Any]:
    """Return scratch ``omrs.jsonc`` values: a managed router on *url* with *entry* only."""
    return {
        "embed_provider": "llamacpp",
        "local_backend": "llamacpp",
        "llamacpp_router_server": "managed",
        "llamacpp_router_url": url,
        "llamacpp_router_models_max": 1,
        "llamacpp_embed_model": router_env.model_name(entry),
        "llamacpp_models": router_env.model_entries({"runtime": {"models": [dict(entry)]}}, folder),
    }


def embed_once(url: str, model: str) -> dict[str, Any]:
    """Send one embedding call straight to the router; return ``ok`` and the error class."""
    from openai import OpenAI, OpenAIError

    client = OpenAI(base_url=url, api_key="local-router", max_retries=0, timeout=60.0)
    try:
        client.embeddings.create(model=model, input=["idle probe"])
    except OpenAIError as exc:
        return {"ok": False, "error": type(exc).__name__}
    finally:
        client.close()
    return {"ok": True, "error": None}


def probe(url: str) -> dict[str, Any]:
    """Return the router build (``/props`` ``build_info``) and the ``/health`` status."""
    base = url.rstrip("/").removesuffix("/v1")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    found: dict[str, Any] = {"build": None, "health": None}
    try:
        with opener.open(base + "/props", timeout=10) as reply:
            found["build"] = json.loads(reply.read()).get("build_info")
    except (OSError, ValueError, AttributeError):
        pass
    try:
        with opener.open(base + "/health", timeout=10) as reply:
            found["health"] = reply.status
    except OSError as exc:
        found["health"] = type(exc).__name__
    return found


def reproduce(
    *,
    url: str,
    model: str,
    idle_seconds: float,
    embed: Callable[[str, str], dict[str, Any]],
    probe: Callable[[str], dict[str, Any]],
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    session: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Embed, wait *idle_seconds* with no lease request, embed again; return the record."""

    def point() -> dict[str, Any]:
        result = embed(url, model)
        state = probe(url)
        return {"at": datetime.now(UTC).isoformat(), "clock": clock(), "embed": result, **state}

    record: dict[str, Any] = {
        "task": "16.31",
        "router_url": url,
        "model": model,
        "idle_limit_seconds": IDLE_LIMIT_SECONDS,
        "held_session": session is not None,
        "waited_seconds": 0,
        "after": None,
        "router_stopped": None,
        "reproduced": None,
    }
    with session() if session is not None else contextlib.nullcontext():
        record["before"] = before = point()
        record["build"] = before.pop("build")
        if not before["embed"]["ok"]:
            return record
        sleep(idle_seconds)
        record["waited_seconds"] = idle_seconds
        record["after"] = after = point()
    after.pop("build")
    record["router_stopped"] = after["health"] != 200
    record["reproduced"] = after["embed"]["error"] == STOP_ERROR
    return record


def managed_router(router_config: Any, files: list[str], plan: Mapping[str, Any]) -> Any:
    """Start the managed router; raise its refusal as ``router_env.RouterConfigError`` (exit 2)."""
    try:
        return router_config.start_router(files, plan)
    except router_config.RouterConfigError as exc:
        raise router_env.RouterConfigError(str(exc)) from exc


@contextlib.contextmanager
def start_router(url: str, out: Path, hold: bool) -> Iterator[tuple[str, Any]]:
    """Start or join the scratch managed router with the 4B file; yield name and session."""
    plan = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    entry = embed_entry(plan)
    config = out / "config"
    router_env.prepare_environment({}, config_dir=config, state_dir=out / "state")
    values = router_values(entry, router_env.gguf_dir(), url)
    router_env.write_settings(values, config)
    router_env.check_settings_file(config)
    router_env.check_resolved(router_env.load_settings(), values)
    exp48 = str(EXP_DIR.parent / "48-pipeline-sweep-llamacpp-2026-11-01")
    if exp48 not in sys.path:
        sys.path.insert(0, exp48)
    import router_config

    one = {"runtime": {"models": [dict(entry)]}}
    router = managed_router(router_config, [entry["file"]], one)
    session = (lambda: router_config.held(router, one, entry["file"])) if hold else None
    yield router_env.model_name(entry), session  # the router stops when the process exits


def main(
    argv: Sequence[str] | None = None,
    *,
    start: Callable[[str, Path, bool], Any] = start_router,
    embed: Callable[[str, str], dict[str, Any]] = embed_once,
    probe: Callable[[str], dict[str, Any]] = probe,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run one reproduction and write ``<out>/idle.json``; return 0, or 2 (see module text)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=router_env.ROUTER_URL, help="router URL ending in /v1")
    parser.add_argument("--idle-seconds", type=float, default=DEFAULT_IDLE_SECONDS)
    parser.add_argument("--out", type=Path, required=True, help="folder for idle.json")
    parser.add_argument("--hold", action="store_true", help="control: hold one router session")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        with start(args.url, args.out, args.hold) as (model, session):
            record = reproduce(
                url=args.url,
                model=model,
                idle_seconds=args.idle_seconds,
                embed=embed,
                probe=probe,
                sleep=sleep,
                clock=time.monotonic,
                session=session,
            )
    except router_env.RouterConfigError as exc:
        print(f"[idle] {exc}", file=sys.stderr, flush=True)
        return 2
    tmp = args.out / "idle.json.tmp"
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.out / "idle.json")
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record["reproduced"] is not None else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
