"""``omrs answer`` when the OpenRouter host check refuses (pre-exp35 D11).

The host check raises ``HostRefused``, a ``RuntimeError``. The CLI must treat
it like the other build failures: a refused answer model prints a failure
(JSON with ``--json``) and exits 1 with no traceback, and a refused judge
degrades to ``verification_skipped`` while the answer is still returned.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from omrs.core.providers.llm.sampling import HostRefused
from omrs.transports.cli import app

runner = CliRunner()

_REFUSAL = "No allowed OpenRouter host for m takes seed: Relace. No call was made."


def _refuse(*_args: Any, **_kwargs: Any) -> Any:
    raise HostRefused(_REFUSAL)


def test_a_refused_answer_model_prints_a_json_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--json`` prints the standard failure on stderr and exits 1, no traceback."""
    monkeypatch.setattr("omrs.compose.build_answer_llm", _refuse)

    result = runner.invoke(app, ["answer", "lantern", "--json"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), "the refusal must not escape as a traceback"
    assert result.stdout.strip() == "", "--json failure output must not write to stdout"
    data = json.loads(result.stderr)
    assert data["status"] == "error"
    assert "Relace" in data["error"]


def test_a_refused_judge_degrades_to_verification_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """The answer is returned and the skip reason names the refusal."""
    seen: dict[str, Any] = {}

    async def _fake_answer(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {
            "status": "ok",
            "query": "lantern",
            "answer": "Station one [1].",
            "citations": [],
            "evidence": [],
            "failure_stage": None,
            "error": None,
            "completion_source": "server",
            "verification_skipped": kwargs["verify_unavailable_reason"],
        }

    monkeypatch.setattr("omrs.compose.build_answer_llm", lambda settings=None: None)
    monkeypatch.setattr("omrs.compose.build_verify_llm", _refuse)
    monkeypatch.setattr("omrs.core.answer.answer", _fake_answer)
    monkeypatch.setenv("ANSWER__VERIFY_CLAIMS", "true")

    result = runner.invoke(app, ["answer", "lantern", "--json"])

    assert result.exit_code == 0, result.output
    assert isinstance(result.exception, (type(None), SystemExit))
    assert seen["verify_complete"] is None
    reason = seen["verify_unavailable_reason"]
    assert reason.startswith("verification provider unavailable: ")
    assert "Relace" in reason
    assert json.loads(result.stderr)["answer"] == "Station one [1]."
