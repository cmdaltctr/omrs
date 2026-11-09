"""Building the claim judges in the composition root (tasks 8.4, 8.6, 8.7).

``compose_judges`` gives each strategy its transport: the typed judges ask the
llama.cpp router through its lease (a fake here, with an ``httpx``
``MockTransport``), read the model file's SHA-256 from the router's
``hashes.json`` and refuse a 4-bit build before any request. The ``chat``
judge records the host its reply names. No network, no router, no model file
beyond a few header bytes.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from tests.fixtures.decision.gguf import header_with_type

from omrs import compose_judges
from omrs.core.answer.verify import run_verification_stage
from omrs.core.settings import EffectiveSettings

_ANSWER = "The sky is blue [1]. Grass is green [2]."
_EVIDENCE = [
    {"ordinal": 1, "text": "Evidence about the sky being blue."},
    {"ordinal": 2, "text": "Evidence about green grass."},
]
_SHA = "c0ffee" * 10 + "abcd"


class FakeLease:
    """A router lease that sends to one fake address; records each model asked."""

    def __init__(self) -> None:
        self.models: list[str] = []

    def request_model(self, model: str, send: Callable[[str], Any]) -> Any:
        self.models.append(model)
        return send("http://127.0.0.1:9/v1")


def _router_reply(handler: Callable[[dict[str, Any], str], Any]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=handler(json.loads(request.content), request.url.path))

    return httpx.MockTransport(respond)


def _model_file(tmp_path: Path, quant: str) -> Path:
    path = tmp_path / f"judge-{quant}.gguf"
    path.write_bytes(header_with_type(quant))
    return path


def _settings(tmp_path: Path, *, judge: str, quant: str = "Q8_0", model: str = "judge") -> Any:
    file = _model_file(tmp_path, quant)
    base = EffectiveSettings()
    answer = base.answer.model_copy(
        update={"verify_claims": True, "verify_judge": judge, "verify_model": model}
    )
    listed = {"judge": {"model": "judge", "file": str(file), "sha256": None}}
    return base.model_copy(update={"answer": answer, "llamacpp_models": listed})


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OMRS_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _write_hashes(state: Path, file: str) -> None:
    from omrs.compose_runtime_manager import runtime_manager
    from omrs.integrations.llamacpp_runtime.router_spec import HASHES_FILE, router_dir

    folder = router_dir(runtime_manager().root)
    folder.mkdir(parents=True, exist_ok=True)
    info = os.stat(file)
    item = {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": _SHA}
    (folder / HASHES_FILE).write_text(json.dumps({file: item}), encoding="utf-8")


def _judge(settings: Any, lease: Any, transport: httpx.MockTransport, monkeypatch: Any) -> Any:
    monkeypatch.setattr("omrs.compose_runtimes.router_lease_for", lambda _settings: lease)
    return compose_judges.build_judge_target(settings, settings.answer, transport=transport)


def _verify(judge: Any) -> Any:
    return asyncio.run(
        run_verification_stage(
            _ANSWER, _EVIDENCE, verify_complete=judge, unavailable_reason=None, error_detail=str
        )
    )


# ── 8.4 / 8.6 clef_flash through the decision adapter and the lease ─────


def test_clef_flash_asks_systemone_through_the_lease(
    tmp_path: Path, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, judge="clef_flash")
    _write_hashes(state, settings.llamacpp_models["judge"]["file"])
    seen: list[tuple[str, dict[str, Any]]] = []

    def reply(body: dict[str, Any], path: str) -> Any:
        seen.append((path, body))
        return {
            "model": "judge",
            "answers": {"fidelity": {"noul": 0.92 if len(seen) == 1 else 0.12}},
        }

    lease = FakeLease()
    fields = _verify(_judge(settings, lease, _router_reply(reply), monkeypatch))

    assert [path for path, _ in seen] == ["/v1/systemone", "/v1/systemone"]
    assert seen[0][1]["model"] == "judge" and seen[0][1]["questions"]["fidelity"]["type"] == "noul"
    assert "The sky is blue." in seen[0][1]["state"]["text"]
    assert lease.models == ["judge", "judge"]
    assert [c["p_yes"] for c in fields.judge_calls] == [0.92, 0.12]
    assert fields.failing[0]["verdict"] == "unsupported"
    first = fields.judge_calls[0]
    assert (first["strategy"], first["model"], first["sha256"]) == ("clef_flash", "judge", _SHA)
    assert first["version"] == "clef-flash-claim/1" and first["host"] is None


def test_a_four_bit_build_sends_no_claim_request(
    tmp_path: Path, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario "Model below 8-bit"."""
    settings = _settings(tmp_path, judge="clef_flash", quant="Q4_K_M")
    lease = FakeLease()
    fields = _verify(
        _judge(settings, lease, _router_reply(lambda b, p: pytest.fail("sent")), monkeypatch)
    )
    assert lease.models == []
    assert fields.skipped_reason == "claim judge clef_flash cannot run: quantisation-refused"
    assert fields.judge_calls == ()


def test_a_router_that_cannot_start_skips_with_a_fixed_reason(
    tmp_path: Path, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario "Router not reachable": the lease cannot be built."""
    settings = _settings(tmp_path, judge="clef_flash")
    fields = _verify(
        _judge(settings, "not-provisioned", _router_reply(lambda b, p: {}), monkeypatch)
    )
    assert fields.skipped_reason == "claim judge clef_flash cannot run: not-provisioned"
    assert "sky" not in fields.skipped_reason


def test_an_unlisted_model_skips_before_any_request(
    tmp_path: Path, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, judge="granite_guardian", model="missing")
    lease = FakeLease()
    fields = _verify(_judge(settings, lease, _router_reply(lambda b, p: {}), monkeypatch))
    assert lease.models == []
    assert fields.skipped_reason == "claim judge granite_guardian cannot run: model-not-listed"


def test_granite_guardian_asks_the_completions_route(
    tmp_path: Path, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, judge="granite_guardian")
    seen: list[tuple[str, dict[str, Any]]] = []

    def reply(body: dict[str, Any], path: str) -> Any:
        seen.append((path, body))
        return {"choices": [{"text": "<score> no </score>"}]}

    fields = _verify(_judge(settings, FakeLease(), _router_reply(reply), monkeypatch))
    assert {path for path, _ in seen} == {"/v1/completions"}
    assert seen[0][1]["prompt"].endswith("<|start_of_role|>judge{no_think}<|end_of_role|>")
    assert seen[0][1]["temperature"] == 0.0
    assert fields.verified is True
    assert fields.judge_calls[0]["settings"]["think"] is False


def test_the_sha256_comes_from_hashes_json_only_while_the_file_matches(
    tmp_path: Path, state: Path
) -> None:
    file = str(_model_file(tmp_path, "Q8_0"))
    _write_hashes(state, file)
    assert compose_judges.cached_sha256(file) == _SHA
    Path(file).write_bytes(header_with_type("Q8_0") + b"changed")
    assert compose_judges.cached_sha256(file) is None


# ── 8.7 the chat strategy's hosted record ───────────────────────────────


class _HostedLLM:
    """An OpenRouter-like judge LLM whose reply names the host that served it."""

    model = "z-ai/glm-5.3"
    temperature = 0.0
    additional_kwargs = {"seed": 20261101}

    async def acomplete(self, prompt: str, **kwargs: Any) -> Any:
        return SimpleNamespace(text="supported", raw={"provider": "Z.AI"})


def test_the_chat_record_names_the_host_and_the_sent_values() -> None:
    """Scenario "Hosted call"."""
    from omrs.engine_answer import build_verifier

    base = EffectiveSettings()
    answer = base.answer.model_copy(
        update={
            "verify_claims": True,
            "verify_provider": "openrouter",
            "verify_model": "z-ai/glm-5.3",
            "verify_reasoning": "low",
        }
    )
    effective = base.model_copy(update={"answer": answer})
    judge, reason = build_verifier(effective, lambda _block: _HostedLLM(), str)
    assert reason is None
    fields = _verify(judge)
    call = fields.judge_calls[0]
    assert (call["strategy"], call["model"], call["host"]) == ("chat", "z-ai/glm-5.3", "Z.AI")
    assert call["version"] == "chat-oneword/1"
    assert call["settings"]["temperature"] == 0.0 and call["settings"]["seed"] == 20261101
    assert call["settings"]["reasoning"] == "low"


def test_no_claim_or_evidence_text_in_the_serialised_result() -> None:
    from omrs.core.answer.results import answered_result
    from omrs.engine_answer import build_verifier

    base = EffectiveSettings()
    answer = base.answer.model_copy(update={"verify_claims": True, "verify_provider": "openrouter"})
    effective = base.model_copy(update={"answer": answer})
    judge, _ = build_verifier(effective, lambda _block: _HostedLLM(), str)
    fields = _verify(judge)
    result = answered_result(
        "q", "server", text=_ANSWER, citations=[], grounded=True, evidence=[],
        verification=fields, diagnostics=None,
    )  # fmt: skip
    text = json.dumps(result["judge_calls"])
    assert len(result["judge_calls"]) == 2
    for fragment in ("The sky is blue", "Grass is green", "Evidence about"):
        assert fragment not in text


def test_the_graph_judge_resource_records_the_host_too() -> None:
    """The user-profile graph path keeps the chat record's host (same as the Engine path)."""
    from omrs.core.answer.graph_adapters import _judge_seam
    from omrs.engine_answer import recording_judge

    base = EffectiveSettings()
    answer = base.answer.model_copy(update={"verify_claims": True, "verify_model": "z-ai/glm-5.3"})
    settings = base.model_copy(update={"answer": answer})
    resource = recording_judge(lambda _block: _HostedLLM(), lambda _block: "openrouter")
    context = SimpleNamespace(settings=settings, resource=lambda _name: resource)
    judge, reason = _judge_seam(context)  # type: ignore[arg-type]
    assert reason is None
    call = _verify(judge).judge_calls[0]
    assert (call["host"], call["model"], call["settings"]["seed"]) == (
        "Z.AI",
        "z-ai/glm-5.3",
        20261101,
    )
