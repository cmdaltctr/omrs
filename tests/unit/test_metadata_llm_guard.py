"""The conftest guard against unplanned LLM metadata calls (design D2).

The guard is an autouse fixture in ``tests/conftest.py``. It replaces
``omrs.core.metadata.extractor._metadata_get`` so that a test which
dispatches an LLM strategy without the ``metadata_llm`` marker fails at once,
before any network call.

These tests run one inner pytest session in a subprocess. The inner
``conftest.py`` loads the real ``tests/conftest.py`` from its file path and
exports only the guard fixture. So the inner tests run against the real
fixture, and none of the other autouse fixtures of the repository apply. A
subprocess keeps the inner ``conftest`` module apart from the outer one, which
an in-process ``pytester`` run would load under the same module name.
"""

from __future__ import annotations

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_REPO_CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
_GUARD_NAME = "_guard_unplanned_metadata_llm"

_INNER_CONFTEST = f"""
import importlib.util

_spec = importlib.util.spec_from_file_location("omrs_repo_conftest", {str(_REPO_CONFTEST)!r})
_repo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_repo)

# Export only the guard. A missing guard leaves the inner tests unguarded,
# so the unmarked case then fails for the reason this file checks.
_guard = getattr(_repo, {_GUARD_NAME!r}, None)
if _guard is not None:
    {_GUARD_NAME} = _guard
"""

_INNER_TESTS = """
import asyncio

import pytest

from omrs.core.metadata import extractor, registry
from omrs.core.settings import EffectiveSettings, MetadataBlock

CALLS = []


async def _stub_llamaindex(text, file_name, settings, *, store=None):
    CALLS.append(file_name)
    return {"category": "stub"}


@pytest.fixture(autouse=True)
def _stub_strategy(monkeypatch):
    # The real llamaindex strategy would make a network call. The stub in
    # the registry cache records that the strategy body ran.
    monkeypatch.setitem(registry._cache, "llamaindex", _stub_llamaindex)
    CALLS.clear()


def _run(mode):
    settings = EffectiveSettings(metadata=MetadataBlock(extraction_mode=mode))
    return asyncio.run(extractor.extract_metadata_async("Some text.", "doc.txt", settings))


def test_unmarked_llamaindex():
    try:
        _run("llamaindex")
    finally:
        assert not CALLS, "the strategy body ran: the guard did not stop the call"


@pytest.mark.metadata_llm
def test_marked_llamaindex():
    assert _run("llamaindex") == {"category": "stub"}
    assert CALLS == ["doc.txt"]


def test_unmarked_keyword():
    assert isinstance(_run("keyword"), dict)


def test_unmarked_disabled():
    assert _run("disabled") == {}
"""


@pytest.fixture(scope="module")
def inner_results(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str | None]:
    """Run the inner session once and map each test name to its failure text.

    Returns:
        Test name to the failure message and text, or ``None`` for a pass.
    """
    root = tmp_path_factory.mktemp("guard_inner")
    (root / "conftest.py").write_text(_INNER_CONFTEST)
    (root / "test_inner.py").write_text(_INNER_TESTS)
    (root / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n    metadata_llm: inner copy of the repository marker\n"
    )
    report = root / "report.xml"
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:xdist",
            "--strict-markers",
            f"--junitxml={report}",
            "test_inner.py",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    results: dict[str, str | None] = {}
    # The report comes from the subprocess above, not from outside input.
    for case in ET.parse(report).getroot().iter("testcase"):  # noqa: S314
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        results[case.get("name", "")] = (
            None if problem is None else f"{problem.get('message', '')}\n{problem.text or ''}"
        )
    return results


def test_unmarked_llm_dispatch_fails_with_the_strategy_name(inner_results) -> None:
    """An unmarked ``llamaindex`` dispatch fails, names the strategy and both fixes."""
    failure = inner_results["test_unmarked_llamaindex"]

    assert failure is not None, "the guard let an unmarked LLM dispatch pass"
    assert "'llamaindex'" in failure
    assert 'extraction_mode="disabled"' in failure
    assert "@pytest.mark.metadata_llm" in failure
    assert "the strategy body ran" not in failure


def test_marked_llm_dispatch_reaches_the_strategy(inner_results) -> None:
    """The ``metadata_llm`` marker turns the guard off for that test."""
    assert inner_results["test_marked_llamaindex"] is None


def test_keyword_dispatch_is_not_guarded(inner_results) -> None:
    """The ``keyword`` strategy makes no LLM call, so the guard lets it pass."""
    assert inner_results["test_unmarked_keyword"] is None


def test_disabled_mode_is_not_guarded(inner_results) -> None:
    """``disabled`` mode makes no LLM call, so the guard lets it pass."""
    assert inner_results["test_unmarked_disabled"] is None


def test_marker_is_registered(pytestconfig: pytest.Config) -> None:
    """``metadata_llm`` is a registered marker of the repository suite."""
    names = [line.split(":", 1)[0].strip() for line in pytestconfig.getini("markers")]

    assert "metadata_llm" in names
