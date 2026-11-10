"""Experiment 35 arm table (design D3) and the scratch settings of one arm.

No router, no model and no network: the settings are built from a fake plan
and empty fake GGUF files in a tmp folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import fake_plan, load, make_gguf

arms = load("arms")


@pytest.fixture
def gguf(tmp_path: Path) -> Path:
    return make_gguf(tmp_path / "gguf")


def _flat(values: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, dict) and key != "llamacpp_models":
            flat.update(_flat(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def _changes(arm: Any, gguf: Path) -> dict[str, Any]:
    """Every settings key and search argument where *arm* differs from the baseline."""
    plan = fake_plan()
    base = arms.ARMS[arms.BASELINE]
    left = _flat(arms.settings_values(base, plan, gguf, answer_host="h", judges=()))
    right = _flat(arms.settings_values(arm, plan, gguf, answer_host="h", judges=()))
    left.update({f"search.{k}": v for k, v in arms.search_kwargs(base).items()})
    right.update({f"search.{k}": v for k, v in arms.search_kwargs(arm).items()})
    return {k: right.get(k) for k in set(left) | set(right) if left.get(k) != right.get(k)}


# --- the table -------------------------------------------------------------------------


def test_the_six_arms_match_the_plan_names() -> None:
    assert list(arms.ARMS) == [
        "documents-profile-4b",
        "embedding-0.6b",
        "embedding-8b",
        "reranker-off",
        "chunking-off",
        "hybrid",
    ]


def test_baseline_is_documents_profile_with_reranker_on_dense_and_token_aware() -> None:
    base = arms.ARMS[arms.BASELINE]
    assert (base.rerank, base.hybrid, base.token_aware) == (True, False, True)
    assert base.embed_role == "embedding-baseline-4b"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("embedding-0.6b", {"llamacpp_embed_model", "llamacpp_models"}),
        ("embedding-8b", {"llamacpp_embed_model", "llamacpp_models"}),
        ("reranker-off", {"search.rerank"}),
        ("chunking-off", {"embedding.tokenizer_model", "embedding.tokenizer_revision"}),
        ("hybrid", {"search.hybrid"}),
    ],
)
def test_each_arm_differs_from_the_baseline_in_its_one_component_only(
    name: str, expected: set[str], gguf: Path
) -> None:
    assert set(_changes(arms.ARMS[name], gguf)) == expected


def test_chunking_off_leaves_the_tokenizer_empty_so_the_legacy_path_runs(gguf: Path) -> None:
    changes = _changes(arms.ARMS["chunking-off"], gguf)
    assert changes == {"embedding.tokenizer_model": "", "embedding.tokenizer_revision": ""}


def test_only_chunking_off_empties_the_tokenizer_through_the_environment() -> None:
    blank = {"EMBEDDING__TOKENIZER_MODEL": "", "EMBEDDING__TOKENIZER_REVISION": ""}
    assert arms.env_overrides(arms.ARMS["chunking-off"]) == blank
    others = [a for n, a in arms.ARMS.items() if n != "chunking-off"]
    assert all(arms.env_overrides(arm) == {} for arm in others)


def test_reranker_and_hybrid_arms_reuse_the_baseline_index() -> None:
    for name in ("reranker-off", "hybrid"):
        assert arms.ARMS[name].index_of == arms.BASELINE
        assert arms.collection("bioasq", arms.ARMS[name]) == arms.collection(
            "bioasq", arms.ARMS[arms.BASELINE]
        )


def test_embedding_and_chunking_arms_build_their_own_index() -> None:
    names = ("embedding-0.6b", "embedding-8b", "chunking-off")
    collections = {arms.collection("freshstack", arms.ARMS[n]) for n in names}
    collections.add(arms.collection("freshstack", arms.ARMS[arms.BASELINE]))
    assert len(collections) == 4
    assert all(arms.ARMS[n].index_of == n for n in names)


def test_hybrid_keeps_the_reranker_on() -> None:
    assert arms.search_kwargs(arms.ARMS["hybrid"]) == {"rerank": True, "hybrid": True}


# --- settings values ---------------------------------------------------------------------


def test_answers_are_hosted_at_temperature_zero_with_the_plan_seed_and_one_host(
    gguf: Path,
) -> None:
    values = arms.settings_values(
        arms.ARMS[arms.BASELINE], fake_plan(), gguf, answer_host="deepinfra/fp8", judges=()
    )
    answer = values["answer"]
    assert answer["provider"] == "openrouter"
    assert answer["model"] == "deepseek/deepseek-v4.1-flash-1017"
    assert (answer["temperature"], answer["seed"]) == (0.0, 20261101)
    assert answer["allowed_hosts"] == "deepinfra/fp8"
    assert answer["verify_claims"] is False
    assert values["metadata"] == {"extraction_mode": "disabled"}
    assert values["rag_profile"] == "documents"


def test_key_fields_hold_references_only(gguf: Path) -> None:
    values = arms.settings_values(
        arms.ARMS[arms.BASELINE], fake_plan(), gguf, answer_host="h", judges=("chat",)
    )
    keys = {k: v for k, v in _flat(values).items() if k.endswith("_api_key")}
    assert keys == {
        "openrouter_api_key": "env://OPENROUTER_API_KEY",
        "openai_compatible_api_key": "env://OMRS_EXP35_ZAI_KEY",
    }


def test_local_judges_add_their_router_entries_and_chat_adds_none(gguf: Path) -> None:
    plan = fake_plan()
    none = arms.settings_values(arms.ARMS[arms.BASELINE], plan, gguf, answer_host="h", judges=())
    both = arms.settings_values(
        arms.ARMS[arms.BASELINE],
        plan,
        gguf,
        answer_host="h",
        judges=("clef_flash", "granite_guardian", "chat"),
    )
    added = set(both["llamacpp_models"]) - set(none["llamacpp_models"])
    assert added == {"judge-clef-flash", "judge-granite-guardian"}


def test_a_plan_without_the_judge_model_stops_with_the_role_named(gguf: Path) -> None:
    plan = fake_plan()
    plan["runtime"]["models"] = [
        m for m in plan["runtime"]["models"] if m["role"] != "judge-clef-flash"
    ]
    with pytest.raises(arms.ArmConfigError, match="judge-clef-flash"):
        arms.settings_values(
            arms.ARMS[arms.BASELINE], plan, gguf, answer_host="h", judges=("clef_flash",)
        )


def test_an_unknown_judge_is_refused() -> None:
    with pytest.raises(arms.ArmConfigError, match="unknown judge"):
        arms.parse_judges("clef_flash,gpt")


def test_judges_parse_in_the_given_order_without_repeats() -> None:
    assert arms.parse_judges("chat, clef_flash,chat") == ("chat", "clef_flash")
    assert arms.parse_judges("") == ()


def test_stage_models_list_only_what_the_stage_loads() -> None:
    hybrid = arms.ARMS["hybrid"]
    assert arms.stage_roles(hybrid, "search", ("clef_flash",)) == ["embedding-baseline-4b"]
    assert arms.stage_roles(arms.ARMS["embedding-8b"], "answer", ("clef_flash", "chat")) == [
        "embedding-8b",
        "judge-clef-flash",
    ]
    assert arms.stage_roles(hybrid, "determinism", ()) == []


def test_key_fields_are_removed_before_the_resolved_check() -> None:
    values = {"openrouter_api_key": "env://X", "answer": {"model": "m"}, "a": 1}
    assert arms.without_keys(values) == {"answer": {"model": "m"}, "a": 1}
