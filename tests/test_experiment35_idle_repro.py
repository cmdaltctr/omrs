"""Experiment 35 ``idle_repro35.py``: reproduce the router idle stop (task 16.31, P17, G14).

No test starts a router or calls a hosted service. The core runs on stubs; the
HTTP layer runs against a fake server on 127.0.0.1 that the test stops.
"""

from __future__ import annotations

import contextlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load

idle = load("idle_repro35")
MODEL = "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
URL = "http://127.0.0.1:18080/v1"


class Clock:
    """Fake time: ``sleep`` moves it on."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _embed(results: list[dict], events: list[str]) -> Any:
    def embed(url: str, model: str) -> dict:
        assert (url, model) == (URL, MODEL)
        events.append("embed")
        return results.pop(0)

    return embed


def _probe(health: list[Any]) -> Any:
    return lambda url: {"build": "b11941-abc", "health": health.pop(0)}


def _run(results: list[dict], health: list[Any], events: list[str] | None = None, **kw: Any):
    clock, events = Clock(), [] if events is None else events
    record = idle.reproduce(
        url=URL,
        model=MODEL,
        idle_seconds=kw.pop("idle_seconds", 660),
        embed=_embed(results, events),
        probe=_probe(health),
        sleep=clock.sleep,
        clock=lambda: clock.now,
        **kw,
    )
    return record, clock


OK = {"ok": True, "error": None}
DOWN = {"ok": False, "error": "APIConnectionError"}


def test_a_router_stop_after_the_wait_is_recorded_as_reproduced() -> None:
    record, clock = _run([OK, DOWN], [200, "URLError"])
    assert clock.slept == [660]
    assert record["reproduced"] is True
    assert record["router_stopped"] is True
    assert record["before"]["embed"] == OK and record["after"]["embed"] == DOWN
    assert record["after"]["health"] == "URLError"
    assert record["waited_seconds"] == 660
    assert record["build"] == "b11941-abc"
    assert record["idle_limit_seconds"] == 600
    assert record["after"]["clock"] - record["before"]["clock"] >= 660


def test_an_embedding_that_still_works_after_the_wait_is_not_a_reproduction() -> None:
    record, _ = _run([OK, OK], [200, 200])
    assert record["reproduced"] is False
    assert record["router_stopped"] is False


def test_a_different_error_after_the_wait_is_not_counted_as_the_idle_stop() -> None:
    record, _ = _run([OK, {"ok": False, "error": "APITimeoutError"}], [200, 200])
    assert record["reproduced"] is False


def test_a_failed_first_embedding_stops_before_the_wait() -> None:
    record, clock = _run([DOWN], [200])
    assert clock.slept == []
    assert record["reproduced"] is None
    assert record["after"] is None


def test_the_default_wait_passes_the_idle_limit_and_one_idle_check() -> None:
    from omrs.integrations.llamacpp_runtime.manager import IDLE_CHECK_SECONDS, IDLE_STOP_SECONDS

    assert idle.IDLE_LIMIT_SECONDS == IDLE_STOP_SECONDS
    assert idle.DEFAULT_IDLE_SECONDS >= IDLE_STOP_SECONDS + IDLE_CHECK_SECONDS


def test_hold_opens_one_session_around_both_embeddings_and_the_wait() -> None:
    events: list[str] = []

    @contextlib.contextmanager
    def session() -> Any:
        events.append("open")
        yield
        events.append("close")

    record, _ = _run([OK, OK], [200, 200], events, session=session)
    assert events == ["open", "embed", "embed", "close"]
    assert record["held_session"] is True


def test_main_writes_idle_json_with_the_record(tmp_path: Path) -> None:
    clock, started = Clock(), []

    @contextlib.contextmanager
    def start(url: str, out: Path, hold: bool) -> Any:
        started.append((url, out, hold))
        yield MODEL, None

    code = idle.main(
        ["--url", URL, "--idle-seconds", "5", "--out", str(tmp_path / "idle")],
        start=start,
        embed=_embed([OK, DOWN], []),
        probe=_probe([200, "URLError"]),
        sleep=clock.sleep,
    )
    assert code == 0
    assert started == [(URL, tmp_path / "idle", False)]
    record = json.loads((tmp_path / "idle" / "idle.json").read_text(encoding="utf-8"))
    assert record["reproduced"] is True and record["waited_seconds"] == 5
    assert not list((tmp_path / "idle").glob("*.tmp"))


def test_main_exits_2_when_the_first_embedding_fails(tmp_path: Path) -> None:
    @contextlib.contextmanager
    def start(url: str, out: Path, hold: bool) -> Any:
        yield MODEL, None

    code = idle.main(
        ["--out", str(tmp_path)], start=start, embed=_embed([DOWN], []), probe=_probe([200])
    )
    assert code == 2
    assert json.loads((tmp_path / "idle.json").read_text())["reproduced"] is None


class _Router(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        body = {"/props": {"build_info": "b11941-abc"}, "/health": {"status": "ok"}}[self.path]
        self._send(body)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        self.rfile.read(int(self.headers["Content-Length"]))
        self._send({"object": "list", "data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    def _send(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


def test_the_http_layer_records_the_openai_connection_error_after_the_server_stops() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        assert idle.embed_once(url, MODEL) == OK
        assert idle.probe(url) == {"build": "b11941-abc", "health": 200}
    finally:
        server.shutdown()
        server.server_close()
    assert idle.embed_once(url, MODEL) == DOWN
    assert idle.probe(url)["health"] == "URLError"


def test_the_router_settings_name_only_the_4b_embedder_on_the_given_url(tmp_path: Path) -> None:
    plan = json.loads((idle.EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    entry = idle.embed_entry(plan)
    (tmp_path / entry["file"]).write_bytes(b"")
    values = idle.router_values(entry, tmp_path, "http://127.0.0.1:18099/v1")
    assert values["llamacpp_router_url"] == "http://127.0.0.1:18099/v1"
    assert values["llamacpp_router_server"] == "managed"
    assert values["llamacpp_embed_model"] == MODEL
    assert [e["model"] for e in values["llamacpp_models"].values()] == [MODEL]
    idle.router_env.write_settings(values, tmp_path / "config")
    idle.router_env.check_settings_file(tmp_path / "config")


def test_the_router_helper_refusal_becomes_the_exit_2_error() -> None:
    # Experiment 48's router_config has its own RouterConfigError (no server binary, ...).
    class HelperError(RuntimeError):
        pass

    def refuse(files: list[str], plan: dict) -> Any:
        raise HelperError("no llama-server binary")

    helper = type("router_config", (), {"RouterConfigError": HelperError, "start_router": refuse})
    with pytest.raises(idle.router_env.RouterConfigError, match="no llama-server binary"):
        idle.managed_router(helper, ["model.gguf"], {})
