"""The conftest guard against unplanned LLM metadata calls (speed-up-fast-test-suite D2).

These tests run under the real autouse guard in ``tests/conftest.py``. The
``llamaindex`` strategy is replaced by a stub in the registry cache, so no
test makes a network call. Without the guard, the unmarked case reaches the
stub and fails because nothing raised.
"""

from __future__ import annotations

import asyncio

import pytest

from omrs.core.metadata import extractor, registry
from omrs.core.settings import EffectiveSettings, MetadataBlock


@pytest.fixture
def stub_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the ``llamaindex`` strategy with a stub; return the calls it records."""
    calls: list[str] = []

    async def _stub(text, file_name, settings, *, store=None):
        calls.append(file_name)
        return {"category": "stub"}

    monkeypatch.setitem(registry._cache, "llamaindex", _stub)
    return calls


def _run(mode: str) -> dict:
    """Dispatch one extraction through the extractor with *mode*."""
    settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode=mode))
    return asyncio.run(extractor.extract_metadata_async("Some text.", "doc.txt", settings))


def test_unmarked_llm_dispatch_fails_with_the_strategy_name(stub_calls: list[str]) -> None:
    """An unmarked ``llamaindex`` dispatch fails, names the strategy and both fixes."""
    with pytest.raises(pytest.fail.Exception) as failure:
        _run("llamaindex")

    message = str(failure.value)
    assert "'llamaindex'" in message
    assert 'extraction_mode="disabled"' in message
    assert "@pytest.mark.metadata_llm" in message
    assert stub_calls == [], "the strategy body ran before the guard failed the test"


@pytest.mark.metadata_llm
def test_marked_llm_dispatch_reaches_the_strategy(stub_calls: list[str]) -> None:
    """The ``metadata_llm`` marker turns the guard off for that test."""
    assert _run("llamaindex") == {"category": "stub"}
    assert stub_calls == ["doc.txt"]


def test_keyword_dispatch_is_not_guarded() -> None:
    """The ``keyword`` strategy makes no LLM call, so the guard lets it pass."""
    assert isinstance(_run("keyword"), dict)


def test_disabled_mode_is_not_guarded() -> None:
    """``disabled`` mode makes no LLM call, so the guard lets it pass."""
    assert _run("disabled") == {}


def test_marker_is_registered(pytestconfig: pytest.Config) -> None:
    """``metadata_llm`` is a registered marker of the repository suite."""
    names = [line.split(":", 1)[0].strip() for line in pytestconfig.getini("markers")]

    assert "metadata_llm" in names
