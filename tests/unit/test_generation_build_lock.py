"""Generation builds each lazy resource once, also under concurrency (2026-11-09 review fix).

Two concurrent first answers used to build the answer LLM twice (and run the
OpenRouter host check twice). The lock keeps one build per generation.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from omrs.engine_providers import Generation


def _race(call: Any) -> list[Any]:
    """Run *call* from two threads that start together; return both results."""
    barrier = threading.Barrier(2)
    results: list[Any] = []

    def worker() -> None:
        barrier.wait()
        results.append(call())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_concurrent_first_answers_build_the_llm_once(effective_settings: Any) -> None:
    generation = Generation(effective=effective_settings())
    calls: list[int] = []

    def factory() -> Any:
        calls.append(1)
        time.sleep(0.05)
        return object()

    generation.answer_llm_factory = factory
    results = _race(generation.get_answer_llm)
    assert calls == [1]
    assert results[0] is results[1]


def test_concurrent_first_use_builds_the_resolver_once(effective_settings: Any) -> None:
    generation = Generation(effective=effective_settings())
    calls: list[int] = []

    def factory() -> Any:
        calls.append(1)
        time.sleep(0.05)
        return object()

    generation.resolver_factory = factory
    results = _race(generation.get_resolver)
    assert calls == [1]
    assert results[0] is results[1]
