"""Experiment 35 setup table (design D28) and the settings each setup writes.

Rules under test: 72 search setups over 9 indexes, named by their four
factors; each setup writes its chunk size, overlap, tokenizer, reranker and
hybrid backend; seeds and pins come from ``plan.json``; the answer setups
hold one round of 131,072 characters (tasks 13.1, 13.1a, 4.1, 4.6, 14.1).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import FOLDER, fake_plan, load, make_gguf, unpin

from omrs.core.answer.settings import AnswerSettings

arms = load("arms")

OLD_ARMS = (
    "documents-profile-4b",
    "embedding-0.6b",
    "embedding-8b",
    "reranker-off",
    "chunking-off",
    "hybrid",
)


@pytest.fixture
def gguf(tmp_path: Path) -> Path:
    return make_gguf(tmp_path / "gguf")


def _values(name: str, gguf: Path, plan: Any = None, judges: tuple[str, ...] = ()) -> Any:
    return arms.settings_values(
        arms.parse_setup(name), plan or fake_plan(), gguf, answer_host="h", judges=judges
    )


# --- the table ----------------------------------------------------------------------------


def test_the_table_has_72_search_setups_over_9_indexes() -> None:
    names = list(arms.SEARCH_SETUPS)
    assert len(names) == 72
    assert len(set(names)) == 72
    pattern = re.compile(r"^e(0\.6b|4b|8b)-c(512|1024|2048)-r(off|0\.6b|4b|8b)-h(off|on)$")
    assert all(pattern.match(name) for name in names)
    assert arms.INDEXES == tuple(
        f"e{e}-c{c}" for e in ("0.6b", "4b", "8b") for c in (512, 1024, 2048)
    )
    assert {arms.SEARCH_SETUPS[n].index for n in names} == set(arms.INDEXES)
    assert not any(old in names or "documents" in name for old in OLD_ARMS for name in names)
    assert not hasattr(arms, "ARMS")
    assert not hasattr(arms, "env_overrides")


def test_index_and_collection_names_follow_the_factors() -> None:
    setup = arms.parse_setup("e0.6b-c512-r8b-hon")
    assert setup.index == "e0.6b-c512"
    assert setup.collection("bioasq") == "exp35_bioasq_e06b_c512"
    assert arms.parse_setup("e8b-c2048-roff-hoff").collection("legal") == "exp35_legal_e8b_c2048"


def test_each_index_has_eight_search_setups() -> None:
    found = arms.index_setups("e4b-c1024")
    assert len(found) == 8
    assert {s.index for s in found} == {"e4b-c1024"}


def test_an_unknown_setup_name_is_refused() -> None:
    with pytest.raises(arms.ArmConfigError, match="e5b-c1024-roff-hoff"):
        arms.parse_setup("e5b-c1024-roff-hoff")


def test_there_are_15_answer_setups_with_the_chosen_sizes() -> None:
    names = [s.name for s in arms.answer_setups("4b", "4b")]
    assert len(names) == 15
    assert "e4b-c512-r4b-hon-t20k" in names
    assert "e4b-c2048-roff-hoff" in names
    assert sum(name.endswith("-t20k") for name in names) == 3
    assert not any("-r0.6b-" in n or "-r8b-" in n for n in names)


def test_judge_names_are_clef_flash_and_chat() -> None:
    assert arms.JUDGE_NAMES == ("clef_flash", "chat")


def test_concurrency_defaults_come_from_one_block() -> None:
    assert arms.CONCURRENCY_DEFAULTS == {
        "answer_concurrency": 16,
        "chat_concurrency": 4,
        "ragas_concurrency": 16,
        "classify_concurrency": 16,
        "rate_limit_attempts": 6,
    }


# --- settings each setup writes -----------------------------------------------------------


def test_reranker_and_hybrid_setup_writes_every_factor(gguf: Path) -> None:
    values = _values("e8b-c2048-r4b-hon", gguf)
    assert values["chunking"] == {
        "chunk_size": 2048,
        "markdown_chunk_size": 2048,
        "chunk_overlap": 307,
    }
    assert values["embedding"]["tokenizer_model"] == "Qwen/Qwen3-Embedding-4B"
    assert values["embedding"]["tokenizer_revision"].startswith("5cf2132a")
    assert values["retrieval"]["rerank_backend"] == "llamacpp"
    assert values["retrieval"]["rerank_model"] == "Qwen/Qwen3-Reranker-4B-GGUF:Q8_0"
    assert values["retrieval"]["hybrid_sparse_backend"] == "bm25"
    assert values["llamacpp_embed_model"] == "Qwen/Qwen3-Embedding-8B-GGUF:Q8_0"
    assert set(values["llamacpp_models"]) == {"embedding-8b", "reranker-4b"}
    assert values["llamacpp_router_models_max"] == 2


@pytest.mark.parametrize(("chunk", "overlap"), [(512, 77), (1024, 154), (2048, 307)])
def test_overlap_is_fifteen_percent_of_the_chunk_size(gguf: Path, chunk: int, overlap: int) -> None:
    assert _values(f"e4b-c{chunk}-roff-hoff", gguf)["chunking"]["chunk_overlap"] == overlap


def test_a_reranker_off_setup_sets_no_reranker_and_loads_one_model(gguf: Path) -> None:
    values = _values("e4b-c1024-roff-hoff", gguf)
    assert "rerank_model" not in values.get("retrieval", {})
    assert "rerank_backend" not in values.get("retrieval", {})
    assert set(values["llamacpp_models"]) == {"embedding-baseline-4b"}
    assert values["llamacpp_router_models_max"] == 1


def test_every_hybrid_on_setup_pins_bm25_and_hybrid_off_sets_nothing(gguf: Path) -> None:
    for name in arms.SEARCH_SETUPS:
        retrieval = _values(name, gguf).get("retrieval", {})
        if name.endswith("-hon"):
            assert retrieval["hybrid_sparse_backend"] == "bm25", name
        else:
            assert "hybrid_sparse_backend" not in retrieval, name


def test_every_answer_setup_holds_one_round_of_131072_characters(gguf: Path) -> None:
    for setup in arms.answer_setups("0.6b", "8b"):
        answer = arms.settings_values(setup, fake_plan(), gguf, answer_host="h", judges=())[
            "answer"
        ]
        assert answer["context_window"] == 131072, setup.name
        assert answer["max_rounds"] == 1, setup.name
        AnswerSettings.model_validate(answer)


def test_local_judges_join_the_router_models(gguf: Path) -> None:
    values = _values("e4b-c512-roff-hoff", gguf, judges=("clef_flash", "chat"))
    assert set(values["llamacpp_models"]) == {"embedding-baseline-4b", "judge-clef-flash"}
    assert values["openai_compatible_api_key"] == f"env://{arms.GLM_KEY_ENV}"


# --- seeds and pins from plan.json (task 13.1a) --------------------------------------------


def test_every_p10_and_p11_settings_pin_is_written_from_the_plan(gguf: Path) -> None:
    values = _values("e4b-c512-r4b-hon", gguf)
    assert values["pdf_reader"] == "pdf_inspector"
    assert values["embedding"]["query_instruction"] == ""
    assert values["answer"]["reasoning"] == "low"
    assert values["answer"]["max_output_tokens"] == 2048
    assert values["retrieval"]["hybrid_rrf_k"] == 60


def test_a_changed_plan_pin_changes_the_written_value(gguf: Path) -> None:
    plan = fake_plan()
    plan["pins"]["settings"]["retrieval"]["hybrid_rrf_k"] = 30
    assert _values("e4b-c512-roff-hon", gguf, plan)["retrieval"]["hybrid_rrf_k"] == 30


def test_the_answer_seed_is_read_from_the_plan(gguf: Path) -> None:
    plan = fake_plan()
    plan["seeds"]["answer"] = 7
    assert _values("e4b-c512-roff-hoff", gguf, plan)["answer"]["seed"] == 7


def test_the_glm_judge_records_the_plan_seed() -> None:
    plan = fake_plan()
    block = arms.judge_block(AnswerSettings(), "chat", plan)
    assert block.verify_seed == 20261109
    plan["seeds"]["glm"] = 42
    assert arms.judge_block(AnswerSettings(), "chat", plan).verify_seed == 42


def test_a_missing_seed_or_pin_block_names_the_plan_key(gguf: Path) -> None:
    plan = fake_plan()
    del plan["seeds"]["glm"]
    with pytest.raises(arms.ArmConfigError, match="seeds.glm"):
        arms.plan_seed(plan, "glm")
    del plan["pins"]
    with pytest.raises(arms.ArmConfigError, match="pins"):
        _values("e4b-c512-roff-hoff", gguf, plan)


# A value a pre-freeze task has not recorded is ``null`` in plan.json and listed in
# ``pins.pending``. Each reader refuses it by name; a ``null`` is never passed on.


def test_a_null_seed_is_refused_and_names_its_key_and_task() -> None:
    plan = unpin(fake_plan(), "seeds.ragas_judge", "P10")
    with pytest.raises(arms.ArmConfigError, match=r"seeds\.ragas_judge.*P10"):
        arms.plan_seed(plan, "ragas_judge")


def test_a_null_recorded_pin_is_refused_and_never_reaches_the_trace() -> None:
    plan = unpin(fake_plan(), "pins.recorded.reranker_instruction", "P11")
    with pytest.raises(arms.ArmConfigError, match=r"pins\.recorded\.reranker_instruction.*P11"):
        arms.recorded_pins(plan)


def test_a_null_settings_pin_is_never_written_to_the_scratch_settings(gguf: Path) -> None:
    plan = unpin(fake_plan(), "pins.settings.retrieval.hybrid_rrf_k", "P11")
    with pytest.raises(arms.ArmConfigError, match=r"pins\.settings\.retrieval\.hybrid_rrf_k.*P11"):
        _values("e4b-c512-roff-hon", gguf, plan)


def test_a_null_pin_without_a_pending_entry_is_still_refused_by_key() -> None:
    plan = fake_plan()
    plan["pins"]["recorded"]["hybrid"] = None
    with pytest.raises(arms.ArmConfigError, match=r"pins\.recorded\.hybrid"):
        arms.recorded_pins(plan)


def test_recorded_pins_hold_the_values_omrs_has_no_setting_for() -> None:
    recorded = arms.recorded_pins(fake_plan())
    assert recorded["reranker_instruction"].startswith("Given a web search query")
    assert recorded["hybrid"]["fusion_depth"] == 100


def test_no_harness_module_imports_from_the_prefreeze_measure_lib() -> None:
    importing = re.compile(r"^\s*(from|import)\s+\S*measure_lib", re.MULTILINE)
    found = [p.name for p in FOLDER.glob("*.py") if importing.search(p.read_text("utf-8"))]
    assert found == []


# --- plan roles and judges ----------------------------------------------------------------


def test_stage_roles_load_the_embedder_and_the_reranker_only_after_the_index() -> None:
    setup = arms.parse_setup("e8b-c512-r0.6b-hoff")
    assert arms.stage_roles(setup, "ingest", ()) == ["embedding-8b"]
    assert arms.stage_roles(setup, "seal", ()) == ["embedding-8b"]
    assert arms.stage_roles(setup, "search", ()) == ["embedding-8b", "reranker-0.6b"]
    assert arms.stage_roles(setup, "judge", ("clef_flash", "chat"))[-1] == "judge-clef-flash"


def test_a_plan_without_the_role_names_it(gguf: Path) -> None:
    plan = fake_plan()
    plan["runtime"]["models"] = [m for m in plan["runtime"]["models"] if m["role"] != "reranker-4b"]
    with pytest.raises(arms.ArmConfigError, match="reranker-4b"):
        _values("e4b-c512-r4b-hoff", gguf, plan)


def test_parse_judges_keeps_order_and_refuses_unknown_names() -> None:
    assert arms.parse_judges("chat, clef_flash,chat") == ("chat", "clef_flash")
    with pytest.raises(arms.ArmConfigError, match="granite_guardian"):
        arms.parse_judges("granite_guardian")


def test_without_keys_drops_every_key_field() -> None:
    assert arms.without_keys({"openrouter_api_key": "env://X", "a": 1}) == {"a": 1}


# --- the answer host and the P10 values in plan.json (2026-11-23 owner decisions) -------------


def _pin_host(plan: Any, host: str = "deepinfra/fp8") -> Any:
    plan["pins"]["settings"]["answer"]["allowed_hosts"] = host
    return plan


def test_the_scratch_settings_take_the_answer_host_from_the_plan_pin(gguf: Path) -> None:
    values = arms.settings_values(
        arms.parse_setup("e4b-c512-roff-hoff"),
        _pin_host(fake_plan()),
        gguf,
        answer_host="",
        judges=(),
    )
    assert values["answer"]["allowed_hosts"] == "deepinfra/fp8"
    AnswerSettings.model_validate(values["answer"])


def test_an_answer_host_that_differs_from_the_plan_pin_is_refused(gguf: Path) -> None:
    with pytest.raises(arms.ArmConfigError, match=r"Other.*deepinfra/fp8"):
        arms.settings_values(
            arms.parse_setup("e4b-c512-roff-hoff"),
            _pin_host(fake_plan()),
            gguf,
            answer_host="Other",
            judges=(),
        )


def test_an_answer_host_equal_to_the_plan_pin_is_accepted(gguf: Path) -> None:
    values = arms.settings_values(
        arms.parse_setup("e4b-c512-roff-hoff"),
        _pin_host(fake_plan()),
        gguf,
        answer_host="deepinfra/fp8",
        judges=(),
    )
    assert values["answer"]["allowed_hosts"] == "deepinfra/fp8"


def test_plan_json_holds_the_p10_values_and_lists_no_p10_key_as_pending() -> None:
    import json

    from omrs.core.answer.settings import normalise_hosts

    plan = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
    pins = plan["pins"]
    assert plan["seeds"]["ragas_judge"] == 20261137
    assert plan["seeds"]["classifier"] == 20261138
    assert pins["settings"]["answer"]["reasoning"] == "none"
    assert pins["settings"]["answer"]["max_output_tokens"] == 2048
    assert pins["settings"]["answer"]["allowed_hosts"] == normalise_hosts("deepinfra/fp8")
    assert pins["ragas_judge"]["host"] == normalise_hosts("deepinfra/bf16")
    assert [p for p in pins["pending"] if p["task"] == "P10"] == []
    answer = AnswerSettings.model_validate(pins["settings"]["answer"])
    assert answer.reasoning == "none"
