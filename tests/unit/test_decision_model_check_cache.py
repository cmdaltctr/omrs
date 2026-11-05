"""How long a decision model check result is kept, and what it blocks.

Review findings A and B of document-reading-routers (design D6). A passing
check is kept for the process. A failed check is kept for at most
``FAILED_CHECK_SECONDS``, so a local server started after ``omrs web`` is
found. The checks of one entry run under that entry's own lock, so a slow
check (a managed runtime can take minutes to start) does not hold up the
check of another entry. Every request goes to an ``httpx.MockTransport``.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import httpx
import pytest

from omrs import compose_decision


@pytest.fixture(autouse=True)
def _fresh_checks():
    compose_decision.reset_decision_checks()
    yield
    compose_decision.reset_decision_checks()


@pytest.fixture
def clock(monkeypatch) -> list[float]:
    now = [1000.0]
    monkeypatch.setattr(compose_decision, "monotonic", lambda: now[0])
    return now


class _Server:
    """Answers the probe, or refuses the connection while ``up`` is false."""

    def __init__(self, *, up: bool = True, gate: threading.Event | None = None) -> None:
        self.up, self.gate, self.calls = up, gate, 0
        self.entered = threading.Event()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(10)
        if not self.up:
            raise httpx.ConnectError("refused", request=request)
        reply = {"model": "Clef-Flash-Q8_0.gguf", "answers": {"fidelity": {"noul": 0.9}}}
        return httpx.Response(200, json=reply)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _judge(server: _Server, port: int = 18933) -> compose_decision.PageJudge:
    model = {"kind": "llamacpp", "address": f"http://127.0.0.1:{port}", "model": "clef-flash"}
    router = {"model": "m", "question": "Q?", "threshold": 0.172}
    settings = SimpleNamespace(
        document_router="r", decision_models={"m": model}, document_routers={"r": router}
    )
    judge = compose_decision.build_page_judge(settings, transport=server.transport)
    assert judge is not None
    return judge


def test_a_passing_check_is_kept_for_the_process(clock: list[float]) -> None:
    server = _Server()
    judge = _judge(server)

    assert judge.status is None
    clock[0] += 24 * 3600
    assert judge.status is None
    assert server.calls == 1


def test_a_failed_check_runs_again_after_the_time_limit(clock: list[float]) -> None:
    server = _Server(up=False)
    judge = _judge(server)

    assert judge.status == compose_decision.UNREACHABLE
    clock[0] += compose_decision.FAILED_CHECK_SECONDS - 1
    assert judge.status == compose_decision.UNREACHABLE
    assert server.calls == 1

    server.up = True
    clock[0] += 2
    assert judge.status is None
    assert server.calls == 2


def test_the_time_limit_is_sixty_seconds() -> None:
    assert compose_decision.FAILED_CHECK_SECONDS == 60.0


def test_a_slow_check_on_one_entry_does_not_block_another_entry() -> None:
    gate = threading.Event()
    slow = _Server(gate=gate)
    fast = _Server()
    slow_judge, fast_judge = _judge(slow, 18934), _judge(fast, 18935)
    background = threading.Thread(target=lambda: slow_judge.status, daemon=True)
    background.start()
    try:
        assert slow.entered.wait(5)
        result: list[str | None] = []
        other = threading.Thread(target=lambda: result.append(fast_judge.status), daemon=True)
        other.start()
        other.join(2)

        assert not other.is_alive(), "the check of entry B waited for entry A"
        assert result == [None]
    finally:
        gate.set()
        background.join(5)


def test_two_readers_of_one_entry_run_the_check_once() -> None:
    gate = threading.Event()
    server = _Server(gate=gate)
    judge = _judge(server)
    results: list[str | None] = []
    readers = [
        threading.Thread(target=lambda: results.append(judge.status), daemon=True) for _ in range(2)
    ]
    for reader in readers:
        reader.start()
    assert server.entered.wait(5)
    gate.set()
    for reader in readers:
        reader.join(5)

    assert results == [None, None]
    assert server.calls == 1
