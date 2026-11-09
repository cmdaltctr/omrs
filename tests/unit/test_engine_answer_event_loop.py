"""``Engine.answer`` keeps the event loop free while the host check reads (pre-exp35 D11).

The first use of an OpenRouter role reads the model's endpoint list with a
blocking call. Web routes and the MCP server await ``Engine.answer`` on the
event loop, so the answer model and judge builds must run in a worker thread.
The endpoint read here is a fake that sleeps with ``time.sleep``; no test
reaches the network.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from omrs.compose import settings_to_effective
from omrs.compose_answer import build_answer_llm, build_verify_llm
from omrs.config import Settings
from omrs.core.providers.llm import openrouter_hosts
from omrs.engine import Engine

ANSWER_MODEL = "deepseek/deepseek-v4.1-flash-1017"
JUDGE_MODEL = "openai/gpt-oss-120b"
OR_KEY = "sk-or-v1-0000aaaa1111bbbb2222cccc3333dddd"  # gitleaks:allow
SLEEP_SECONDS = 0.4


def _payload(model: str) -> dict[str, Any]:
    endpoint = {"provider_name": "Fireworks", "tag": "fireworks", "supported_parameters": ["seed"]}
    return {"data": {"id": model, "endpoints": [endpoint]}}


class SlowFetch:
    """An endpoint-list read that blocks its thread, like ``httpx.get`` does."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, url: str, headers: dict[str, str]) -> Any:
        self.calls += 1
        time.sleep(SLEEP_SECONDS)
        return _payload(url.split("/models/")[1].removesuffix("/endpoints"))


@pytest.fixture(autouse=True)
def _fresh_cache() -> Any:
    openrouter_hosts.clear_cache()
    yield
    openrouter_hosts.clear_cache()


def test_the_host_check_does_not_block_the_event_loop(tmp_path: Any) -> None:
    """A concurrent task keeps running while both first-use endpoint reads sleep."""
    settings = Settings(
        _env_file=None,
        openrouter_api_key=OR_KEY,
        lancedb_uri=str(tmp_path / "lancedb"),
        answer={
            "provider": "openrouter",
            "model": ANSWER_MODEL,
            "seed": 1,
            "allowed_hosts": "Fireworks",
            "verify_claims": True,
            "verify_provider": "openrouter",
            "verify_model": JUDGE_MODEL,
            "verify_seed": 1,
            "verify_allowed_hosts": "Fireworks",
        },
    )
    fetch = SlowFetch()
    engine = Engine(
        settings_to_effective(settings),
        store=MagicMock(cache_identity="test-identity"),
        embed_model=MagicMock(model_name="m"),
        answer_llm_factory=lambda: build_answer_llm(settings, fetch_endpoints=fetch),
        verify_llm_factory=lambda block: build_verify_llm(
            settings, answer_block=block, fetch_endpoints=fetch
        ),
    )

    async def fake_answer(_query: str, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "ok"}

    async def scenario() -> int:
        ticks = 0
        stop = asyncio.Event()

        async def ticker() -> None:
            nonlocal ticks
            while not stop.is_set():
                await asyncio.sleep(0.01)
                ticks += 1

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0)  # let the ticker start
        await engine.answer("q")
        stop.set()
        await task
        return ticks

    with patch("omrs.core.answer.pipeline.answer", side_effect=fake_answer):
        ticks = asyncio.run(scenario())

    assert fetch.calls == 2, "the answer model and the judge each read once"
    # Blocked loop: about 0 ticks. Free loop: about 2 * SLEEP_SECONDS / 0.01 = 80.
    assert ticks >= 20, f"the event loop stalled during the endpoint read (ticks={ticks})"
