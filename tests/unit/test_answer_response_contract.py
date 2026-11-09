"""``AnswerResponse`` declares every key an answer result holds, and nothing else (task 1.5).

Spec ``answer-sampling``: the schema declares ``sampling``, ``judge_calls``,
``usage`` and ``reasoning`` and sets ``additionalProperties: false``. Each
result below comes from the real builders (``core/answer/results.py``), the
Engine's completion ledger (``engine_answer.py``: ``usage``, ``reasoning``,
``sampling``) and the user-profile path (``unused_request_values``), and is
validated against the contract.
"""

from __future__ import annotations

import asyncio
import types
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from tests.unit.test_llm_reasoning_providers import OPENROUTER_REPLY

from omrs.core.answer import results
from omrs.core.answer.verify import VerificationFields
from omrs.core.settings import AnswerBlock
from omrs.engine_answer import CompletionLedger, build_verifier, select_completion

_CONTRACT = Path(__file__).resolve().parents[2] / "src/omrs/transports/api/openapi.yaml"
_EVIDENCE = {
    "ordinal": 1,
    "chunk_id": "c1",
    "chunk_ids": ["c1"],
    "source_id": "s1",
    "source_version": "v1",
    "source": "doc.md",
    "source_chunk_index": 0,
    "score": 0.5,
    "score_kind": "similarity",
    "text": "The sky is blue.",
}
_CITATION = {k: v for k, v in _EVIDENCE.items() if k != "text"}
_DIAGNOSTICS = results.generation_diagnostics(1.0, 2.0, 1)


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))


def _validate(contract: dict[str, Any], body: dict[str, Any]) -> None:
    schema = {"$ref": "#/components/schemas/AnswerResponse", "components": contract["components"]}
    jsonschema.Draft202012Validator(schema).validate(body)


class _FakeLLM:
    """An LLM that answers with the recorded OpenRouter reply."""

    model = "z-ai/glm-5.3-flash"
    temperature = 0.1

    def __init__(self, seed: int | None = None) -> None:
        self.additional_kwargs = {} if seed is None else {"seed": seed}

    async def acomplete(self, prompt: str) -> Any:
        return types.SimpleNamespace(text="The sky is blue [1].", raw=OPENROUTER_REPLY)


def _ledger_result(effective_settings: Any) -> dict[str, Any]:
    block = AnswerBlock(
        provider="openrouter", model="m", verify_claims=True, verify_provider="openrouter"
    )
    effective = effective_settings(answer=block)
    ledger = CompletionLedger()
    complete, effective, _ = select_completion(effective, None, lambda: _FakeLLM(seed=1), ledger)
    verify, _ = build_verifier(effective, lambda b: _FakeLLM(seed=2), str, ledger)

    async def run() -> None:
        await complete("q")
        await verify("claim")

    asyncio.run(run())
    result = results.answered_result(
        "q",
        "server",
        text="The sky is blue [1].",
        citations=[_CITATION],
        grounded=True,
        evidence=[_EVIDENCE],
        verification=VerificationFields(verified=True, ran=True, ms=3.0, calls=1),
        diagnostics=_DIAGNOSTICS,
    )
    return ledger.attach(result)


def test_the_schema_is_closed_and_declares_the_new_fields(contract: dict[str, Any]) -> None:
    schema = contract["components"]["schemas"]["AnswerResponse"]
    assert schema.get("additionalProperties") is False
    for name in ("sampling", "judge_calls", "usage", "reasoning", "unused_request_values"):
        assert name in schema["properties"], name


def test_a_server_answer_with_ledger_fields_conforms(
    contract: dict[str, Any], effective_settings: Any
) -> None:
    result = _ledger_result(effective_settings)
    assert {"usage", "reasoning", "sampling"} <= set(result)
    assert set(result["sampling"]) == {"chat", "judge"}
    _validate(contract, result)


def test_the_profile_path_extra_key_conforms(
    contract: dict[str, Any], effective_settings: Any
) -> None:
    result = _ledger_result(effective_settings)
    result["unused_request_values"] = ["rerank"]
    _validate(contract, result)


_CALL = {
    "strategy": "clef_flash",
    "model": "clef-flash",
    "host": None,
    "sha256": "ab" * 32,
    "version": "clef-flash-claim/1",
    "settings": {
        "temperature": None,
        "seed": None,
        "reasoning": None,
        "threshold": 0.5,
        "think": None,
    },
    "p_yes": 0.92,
    "error": None,
}


def test_a_judge_calls_list_conforms(contract: dict[str, Any], effective_settings: Any) -> None:
    result = _ledger_result(effective_settings)
    result["judge_calls"] = [_CALL]
    _validate(contract, result)


@pytest.mark.parametrize(
    "entry",
    [
        {"strategy": "chat", "verdict": "supported"},
        {**_CALL, "claim": "The sky is blue."},
        {**_CALL, "settings": {**_CALL["settings"], "evidence": "x"}},
    ],
)
def test_a_loose_judge_call_is_refused(contract: dict[str, Any], entry: dict[str, Any]) -> None:
    """The entry is closed: claim or evidence text cannot ride along (design D10)."""
    result = results.no_evidence_result("q", "server")
    result["judge_calls"] = [entry]
    with pytest.raises(jsonschema.ValidationError):
        _validate(contract, result)


@pytest.mark.parametrize(
    "result",
    [
        results.no_evidence_result(
            "q", "server", diagnostics=results.zero_generation_diagnostics(1.0)
        ),
        results.no_provider_result("q", "server", [_EVIDENCE]),
        results.disabled_result("q", "none"),
        results.stage_failure_result(
            "q",
            "server",
            failure_stage="generation",
            error="Generation failed",
            evidence=[_EVIDENCE],
        ),
        results.answered_result(
            "q",
            "client_mrtr",
            text="Blue [1].",
            citations=[_CITATION],
            grounded=True,
            evidence=[_EVIDENCE],
            verification=VerificationFields(
                failing=({"claim": "Blue.", "verdict": "unsupported", "ordinals": [1]},),
                ran=True,
                calls=1,
            ),
            diagnostics=_DIAGNOSTICS,
        ),
        results.answered_result(
            "q",
            "server",
            text="Blue.",
            citations=[],
            grounded=False,
            evidence=[_EVIDENCE],
            verification=VerificationFields(skipped_reason="verification provider unavailable"),
        ),
    ],
)
def test_every_builder_result_conforms(contract: dict[str, Any], result: dict[str, Any]) -> None:
    _validate(contract, result)


def test_an_undeclared_key_is_refused(contract: dict[str, Any]) -> None:
    result = results.no_evidence_result("q", "server")
    result["surprise"] = 1
    with pytest.raises(jsonschema.ValidationError):
        _validate(contract, result)


def test_a_real_claim_check_record_conforms(contract: dict[str, Any]) -> None:
    from omrs.core.answer.verify import run_verification_stage

    async def judge(prompt: str) -> str:
        return "supported"

    fields = asyncio.run(
        run_verification_stage(
            "The sky is blue [1].",
            [_EVIDENCE],
            verify_complete=judge,
            unavailable_reason=None,
            error_detail=str,
        )
    )
    result = results.answered_result(
        "q", "server", text="The sky is blue [1].", citations=[_CITATION], grounded=True,
        evidence=[_EVIDENCE], verification=fields, diagnostics=_DIAGNOSTICS,
    )  # fmt: skip
    assert result["judge_calls"][0]["version"] == "chat-oneword/1"
    _validate(contract, result)
