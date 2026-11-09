"""The ``answer.verify_judge`` lever in Studio (task 8.3a; spec ``claim-judge-strategies``).

The Verify claims step takes ``verify_judge`` beside ``verify_claims``. Its
options come from the judge registry through the operation catalogue (no
list in web code and no ``Literal``). A name the registry does not hold is
refused; a strategy whose model is not set up on this host is reported not
ready and refused before a save, with a message that names the missing setting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.test_engine_pipelines_support import build_engine

from omrs.compose_judges import judge_option_set, judge_save_problem
from omrs.core.answer.graph_adapters import VERIFY_CLAIMS, VerifyClaimsParams
from omrs.core.answer.judges import registry
from omrs.core.pipelines import ALLOWED_LEVERS, IssueCode, PipelineValidationError
from omrs.core.pipelines.levers import apply_levers
from omrs.core.settings import EffectiveSettings
from omrs.pipeline_templates import answer_template

_LISTED = {"clef": {"model": "clef-flash", "file": "/models/clef-q8.gguf"}}


def _settings(**answer: Any) -> EffectiveSettings:
    base = EffectiveSettings()
    return base.model_copy(
        update={"answer": base.answer.model_copy(update=answer), "llamacpp_models": _LISTED}
    )


def _graph(**verify: Any) -> dict[str, Any]:
    data = answer_template().model_dump(mode="json")
    for node in data["graph"]["nodes"]:
        if node["id"] == "verify":
            node["params"] = {**(node.get("params") or {}), **verify}
    return data


# ── The lever and the step parameter ─────────────────────────────────────


def test_the_lever_is_a_plain_string_beside_check_claims() -> None:
    spec = ALLOWED_LEVERS["answer.verify_judge"]
    assert spec.validate("clef_flash") == "clef_flash"
    with pytest.raises(ValidationError):
        spec.validate(3)
    assert VERIFY_CLAIMS.lever_params == {
        "verify_claims": "answer.verify_claims",
        "verify_judge": "answer.verify_judge",
    }
    assert VERIFY_CLAIMS.option_params == {"verify_judge": "verify_judge"}


def test_the_lever_round_trips_through_the_settings() -> None:
    applied = apply_levers(_settings(), {"answer.verify_judge": "clef_flash"})
    assert applied.answer.verify_judge == "clef_flash"


def test_the_step_options_come_from_the_registry() -> None:
    schema = VerifyClaimsParams.model_json_schema()["properties"]["verify_judge"]
    variants = schema.get("anyOf", [schema])
    names = next(v["enum"] for v in variants if "enum" in v)
    assert names == registry.names()


@pytest.mark.parametrize("value", [None, "chat", "clef_flash", "granite_guardian"])
def test_the_step_takes_a_registered_name_or_inherit(value: str | None) -> None:
    assert VerifyClaimsParams(verify_judge=value).verify_judge == value


def test_the_step_refuses_an_unknown_name_naming_the_registered_ones() -> None:
    with pytest.raises(ValidationError) as caught:
        VerifyClaimsParams(verify_judge="foo")
    assert all(name in str(caught.value) for name in registry.names())


# ── Not ready on this host ───────────────────────────────────────────────


def test_a_typed_strategy_without_a_judge_model_is_not_ready() -> None:
    reasons = judge_option_set(_settings(verify_model="")).unavailable
    assert "answer.verify_model" in reasons["granite_guardian"]
    assert "answer.verify_model" in reasons["clef_flash"]
    assert "chat" not in reasons


def test_a_typed_strategy_whose_model_the_router_lacks_is_not_ready() -> None:
    reasons = judge_option_set(_settings(verify_model="granite-guardian")).unavailable
    assert "granite-guardian" in reasons["granite_guardian"]
    assert "answer.verify_model" in reasons["granite_guardian"]


def test_a_listed_model_makes_the_typed_strategies_ready() -> None:
    option_set = judge_option_set(_settings(verify_model="clef-flash", verify_judge="clef_flash"))
    assert "clef_flash" not in option_set.unavailable
    assert option_set.inherited == "clef_flash"


def test_an_unknown_name_is_unavailable() -> None:
    assert "foo" in judge_option_set(_settings()).unavailable


def test_the_draft_check_reports_a_not_ready_strategy(tmp_path: Path) -> None:
    engine = build_engine(_settings(verify_model=""))
    with pytest.raises(PipelineValidationError) as caught:
        engine.validate_pipeline(_graph(verify_judge="granite_guardian"))
    issues = [i for i in caught.value.issues if i.code == IssueCode.OPTION_UNAVAILABLE]
    assert issues and issues[0].node_id == "verify"
    assert "answer.verify_model" in issues[0].message


def test_the_catalogue_lists_the_not_ready_options() -> None:
    engine = build_engine(_settings(verify_model=""))
    verify = next(
        op for op in engine.describe_operations() if op["operation_id"] == "verify.claims"
    )
    assert set(verify["unavailable_options"]["verify_judge"]) == {"clef_flash", "granite_guardian"}
    assert verify["inherited_values"]["verify_judge"] == "chat"


# ── Save ─────────────────────────────────────────────────────────────────


def test_a_save_refuses_a_not_ready_strategy_naming_the_setting() -> None:
    problem = judge_save_problem(
        _settings(verify_model=""), _graph(verify_judge="clef_flash")["graph"]
    )
    assert problem is not None and "answer.verify_model" in problem and "clef_flash" in problem


def test_a_save_refuses_an_unknown_override() -> None:
    document = {**_graph()["graph"], "overrides": {"answer.verify_judge": "foo"}}
    problem = judge_save_problem(_settings(), document)
    assert problem is not None and "chat" in problem and "granite_guardian" in problem


def test_a_save_takes_a_ready_strategy_and_a_removed_override() -> None:
    settings = _settings(verify_model="clef-flash")
    assert judge_save_problem(settings, _graph(verify_judge="clef_flash")["graph"]) is None
    assert judge_save_problem(settings, _graph(verify_judge=None)["graph"]) is None
