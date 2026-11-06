"""Self-tests of the fake router (task 3.1, design D16).

The fake ``llama-server`` gains a router mode with ``--models-preset``. These
tests start it as a real process and check each rule that the spike evidence
(``evidence/spike-1.2.md`` and ``spike-1.3-macos.md``) records for b11941:
the model list, load and unload, the error codes, routing by ``model``, the
reload rule, autoload, and the process behaviour of the children.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.fixtures.llamacpp.harness import pid_alive, wait_until
from tests.fixtures.llamacpp.install import install_fake_server

EMBED = "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
CHAT = "Qwen/Qwen3-4B-GGUF:Q8_0"
EXTRA = "Clef/Flash-GGUF:Q8_0"

PRESET = f"""\
[{EMBED}]
model = /models/embed.gguf
embeddings = true
pooling = last
ctx-size = 8192

[{CHAT}]
model = /models/chat.gguf
ctx-size = 8192
"""

#: Seconds a group stop may take (design D9 allows 10).
STOP_SECONDS = 10.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FakeRouter:
    """A fake router started as its own process group."""

    def __init__(self, folder: Path, **env: str) -> None:
        self.binary = install_fake_server(folder / "bin")
        self.preset = folder / "models.ini"
        self.preset.write_text(PRESET, encoding="utf-8")
        self.requests = folder / "requests.jsonl"
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "FAKE_LLAMA_REQUESTS": str(self.requests),
            **env,
        }
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(  # noqa: S603 - test fixture, fixed argv
            [
                str(self.binary),
                "--models-preset",
                str(self.preset),
                "--models-max",
                "4",
                "--models-memory-margin",
                "8192",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            env=self.env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        assert wait_until(self._healthy, 15), "the router never answered /health"

    def _healthy(self) -> bool:
        try:
            return httpx.get(f"{self.url}/health", timeout=1).status_code == 200
        except httpx.HTTPError:
            return False

    @property
    def pid(self) -> int:
        assert self.proc is not None
        return self.proc.pid

    def get(self, path: str) -> httpx.Response:
        return httpx.get(f"{self.url}{path}", timeout=30)

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        return httpx.post(f"{self.url}{path}", json=body, timeout=30)

    def status(self, name: str | None = None) -> Any:
        """Return ``{name: status value}`` or, with *name*, that model's value."""
        items = self.get("/v1/models").json()["data"]
        values = {item["id"]: item["status"]["value"] for item in items}
        return values if name is None else values.get(name)

    def item(self, name: str) -> dict[str, Any]:
        items = self.get("/v1/models").json()["data"]
        return next(item for item in items if item["id"] == name)

    def load(self, name: str) -> None:
        """Load *name* and wait until it is ``loaded``."""
        assert self.post("/models/load", {"model": name}).status_code == 200
        assert wait_until(lambda: self.status(name) == "loaded", 15), self.status()

    def children(self) -> dict[str, int]:
        """Return ``{model name: pid}`` of the router's direct children."""
        out = subprocess.run(  # noqa: S603 - fixed argv
            ["ps", "-A", "-o", "pid=,ppid=,args="],  # noqa: S607 - ps on PATH
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        found: dict[str, int] = {}
        for line in out.splitlines():
            pid_text, ppid_text, args = line.strip().split(None, 2)
            if int(ppid_text) == self.pid and "--router-child" in args:
                words = shlex.split(args)
                found[words[words.index("--alias") + 1]] = int(pid_text)
        return found

    def rewrite(self, text: str) -> None:
        tmp = self.preset.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.preset)

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):  # group already gone
            pass
        self.proc.wait()


def _group_of(pid: int) -> int:
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["ps", "-o", "pgid=", "-p", str(pid)],  # noqa: S607 - ps on PATH
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return int(out.strip())


@pytest.fixture
def make_router(tmp_path: Path) -> Iterator[Any]:
    """Return a factory for started routers; every one is killed at the end."""
    started: list[FakeRouter] = []

    def factory(**env: str) -> FakeRouter:
        router = FakeRouter(tmp_path, **env)
        started.append(router)
        router.start()
        return router

    yield factory
    for router in started:
        router.stop()


def test_health_answers_with_no_model_loaded(make_router: Any) -> None:
    router = make_router()
    assert router.get("/health").json() == {"status": "ok"}
    assert router.children() == {}
    assert router.get("/props").json()["role"] == "router"


def test_model_list_before_and_after_load(make_router: Any) -> None:
    router = make_router()
    assert router.status() == {EMBED: "unloaded", CHAT: "unloaded"}
    before = router.item(EMBED)["status"]
    assert before["args"][0] == str(router.binary)
    assert "--embeddings" in before["args"]
    assert before["args"][before["args"].index("--alias") + 1] == EMBED
    assert before["preset"].startswith(f"[{EMBED}]\n")
    assert "ctx-size = 8192\n" in before["preset"]

    router.load(EMBED)

    assert router.status() == {EMBED: "loaded", CHAT: "unloaded"}
    assert set(router.children()) == {EMBED}


def test_load_and_unload_start_and_end_the_child(make_router: Any) -> None:
    router = make_router()
    router.load(CHAT)
    pid = router.children()[CHAT]
    assert pid_alive(pid)
    assert router.post("/models/load", {"model": CHAT}).status_code == 400  # already running

    assert router.post("/models/unload", {"model": CHAT}).status_code == 200

    assert router.status(CHAT) == "unloaded"
    assert wait_until(lambda: not pid_alive(pid), 5)
    assert router.post("/models/unload", {"model": CHAT}).status_code == 400  # not running


def test_unknown_name_status_codes(make_router: Any) -> None:
    router = make_router()
    unknown = {"model": "no-such/model:Q8_0"}
    assert router.post("/models/load", unknown).status_code == 404
    assert router.post("/models/unload", unknown).status_code == 400
    assert router.post("/v1/embeddings", unknown).status_code == 400
    assert router.post("/v1/chat/completions", unknown).status_code == 400
    assert router.post("/v1/chat/completions", {"messages": []}).status_code == 400
    assert router.children() == {}


@pytest.mark.parametrize(
    "path", ["/v1/embeddings", "/v1/chat/completions", "/v1/completions", "/v1/systemone"]
)
def test_post_routes_by_the_model_field(make_router: Any, path: str) -> None:
    router = make_router()
    router.load(EMBED)
    router.load(CHAT)

    first = router.post(path, {"model": EMBED, "input": "a"})
    second = router.post(path, {"model": CHAT, "input": "b"})

    assert first.status_code == second.status_code == 200
    assert first.json()["model"] == EMBED
    assert second.json()["model"] == CHAT
    sent = [json.loads(line) for line in router.requests.read_text().splitlines()]
    assert [body["input"] for body in sent] == ["a", "b"]
    if path == "/v1/embeddings":
        assert first.json()["data"][0]["embedding"] == [0.1, 0.2, 0.3]
    else:
        assert first.json()["choices"][0]["message"]["content"] == "[]"


def test_post_to_an_unloaded_model_loads_it(make_router: Any) -> None:
    router = make_router()
    assert router.status(CHAT) == "unloaded"

    reply = router.post("/v1/chat/completions", {"model": CHAT})

    assert reply.status_code == 200
    assert reply.json()["model"] == CHAT
    assert router.status() == {EMBED: "unloaded", CHAT: "loaded"}


def test_reload_unloads_only_the_edited_model(make_router: Any) -> None:
    router = make_router()
    router.load(EMBED)
    router.load(CHAT)
    pids = router.children()

    router.rewrite(
        PRESET.replace(
            "[" + CHAT + "]\nmodel = /models/chat.gguf\nctx-size = 8192",
            "[" + CHAT + "]\nmodel = /models/chat.gguf\nctx-size = 4096",
        )
    )
    assert router.get("/models?reload=1").status_code == 200

    assert router.status() == {EMBED: "loaded", CHAT: "unloaded"}
    assert wait_until(lambda: not pid_alive(pids[CHAT]), 5)
    assert router.children() == {EMBED: pids[EMBED]}
    router.load(CHAT)
    args = router.item(CHAT)["status"]["args"]
    assert args[args.index("--ctx-size") + 1] == "4096"
    embed_args = router.item(EMBED)["status"]["args"]
    assert embed_args[embed_args.index("--ctx-size") + 1] == "8192"
    assert router.children()[CHAT] != pids[CHAT]


def test_reload_of_an_unchanged_file_unloads_nothing(make_router: Any) -> None:
    router = make_router()
    router.load(EMBED)
    router.load(CHAT)
    pids = router.children()
    sections = PRESET.split("\n\n")

    router.rewrite("# reordered\n" + sections[1].rstrip() + "\n\n" + sections[0])
    assert router.get("/models?reload=1").status_code == 200

    assert router.status() == {EMBED: "loaded", CHAT: "loaded"}
    assert router.children() == pids


def test_reload_drops_removed_and_lists_added_sections(make_router: Any) -> None:
    router = make_router()
    router.load(EMBED)
    router.load(CHAT)
    pids = router.children()

    router.rewrite(
        f"[{EMBED}]\nmodel = /models/embed.gguf\nembeddings = true\npooling = last\n"
        f"ctx-size = 8192\n\n[{EXTRA}]\nmodel = /models/extra.gguf\n"
    )
    router.get("/models?reload=1")

    assert router.status() == {EMBED: "loaded", EXTRA: "unloaded"}
    assert wait_until(lambda: not pid_alive(pids[CHAT]), 5)
    assert router.children() == {EMBED: pids[EMBED]}
    assert router.post("/v1/chat/completions", {"model": CHAT}).status_code == 400


def test_a_slow_load_shows_loading_first(make_router: Any) -> None:
    router = make_router(FAKE_LLAMA_LOAD_DELAY="1")
    started = time.monotonic()
    assert router.post("/models/load", {"model": CHAT}).status_code == 200

    assert router.status(CHAT) == "loading"
    assert wait_until(lambda: router.status(CHAT) == "loaded", 15)
    assert time.monotonic() - started >= 1.0


def test_a_failing_load_shows_failed_for_that_model_only(make_router: Any) -> None:
    router = make_router(FAKE_LLAMA_LOAD_FAIL=CHAT)
    assert router.post("/models/load", {"model": CHAT}).status_code == 200
    assert wait_until(lambda: router.status(CHAT) == "failed", 15)

    assert router.item(CHAT)["status"]["exit_code"] == 1
    assert router.post("/v1/chat/completions", {"model": CHAT}).status_code == 500
    router.load(EMBED)
    assert router.children() == {EMBED: router.children()[EMBED]}


def test_group_sigterm_ends_the_router_and_every_child(make_router: Any) -> None:
    router = make_router()
    router.load(EMBED)
    router.load(CHAT)
    pids = [router.pid, *router.children().values()]
    assert len(pids) == 3
    assert {_group_of(p) for p in pids} == {router.pid}  # children share the group

    os.killpg(router.pid, signal.SIGTERM)

    assert wait_until(lambda: not any(pid_alive(p) for p in pids), STOP_SECONDS)


def test_sigkill_of_the_router_alone_ends_every_child(make_router: Any) -> None:
    router = make_router()
    router.load(EMBED)
    router.load(CHAT)
    children = list(router.children().values())
    assert len(children) == 2

    os.kill(router.pid, signal.SIGKILL)

    assert wait_until(lambda: not any(pid_alive(p) for p in children), STOP_SECONDS)


def test_a_child_ends_on_its_own_sigterm(make_router: Any) -> None:
    router = make_router()
    router.load(EMBED)
    router.load(CHAT)
    pids = router.children()

    os.kill(pids[CHAT], signal.SIGTERM)

    assert wait_until(lambda: not pid_alive(pids[CHAT]), STOP_SECONDS)
    assert pid_alive(pids[EMBED])
    assert pid_alive(router.pid)
