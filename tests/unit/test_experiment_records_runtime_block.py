"""The ``runtime`` block of ``plan.json`` (reproducible-experiment-runtime, task 2.1, D4).

One pydantic model validates the block, so the checker and the live-server
check cannot disagree about what a valid block is.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from omrs.core.experiment_records.record import RecordError
from omrs.core.experiment_records.runtime_block import (
    LocalModel,
    ReferenceModel,
    RuntimeBlock,
    Tolerance,
    load_runtime_block,
)

_SHA = "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439"


def _plan(**runtime_overrides: Any) -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "runtime_under_test": False,
        "models": [
            {
                "role": "embedding",
                "repository": "Qwen/Qwen3-Embedding-0.6B-GGUF",
                "file": "Qwen3-Embedding-0.6B-Q8_0.gguf",
                "sha256": _SHA,
                "runtime": "llama.cpp",
                "build": 11671,
                "server_args": {"pooling": "last", "ubatch-size": 8192, "embedding": True},
            }
        ],
        "references": [{"role": "reference", "provider": "cloudflare", "model": "clef-flash"}],
        "tolerance": [
            {"metric": "recall_at_10", "max_abs_change": 0.01},
            {"item_score": "noul", "max_abs_change": 0.10},
        ],
    }
    runtime.update(runtime_overrides)
    return {"hypothesis": "x", "runtime": runtime}


def _model(plan: dict[str, Any]) -> dict[str, Any]:
    model: dict[str, Any] = plan["runtime"]["models"][0]
    return model


def test_valid_llamacpp_entry_loads() -> None:
    block = load_runtime_block(_plan())
    assert isinstance(block, RuntimeBlock)
    assert block.runtime_under_test is False
    (model,) = block.models
    assert isinstance(model, LocalModel)
    assert model.file == "Qwen3-Embedding-0.6B-Q8_0.gguf"
    assert model.build == 11671
    assert model.server_args == {"pooling": "last", "ubatch-size": 8192, "embedding": True}
    assert isinstance(block.references[0], ReferenceModel)
    assert [t.metric for t in block.tolerance] == ["recall_at_10", None]
    assert isinstance(block.tolerance[1], Tolerance)
    assert block.tolerance[1].item_score == "noul"


def test_references_default_to_empty() -> None:
    plan = _plan()
    del plan["runtime"]["references"]
    assert load_runtime_block(plan).references == []


@pytest.mark.parametrize("sha", ["abc", _SHA[:-1], _SHA + "0", _SHA.upper(), "g" * 64])
def test_sha256_must_be_64_lower_hex(sha: str) -> None:
    plan = _plan()
    _model(plan)["sha256"] = sha
    with pytest.raises(RecordError, match="sha256"):
        load_runtime_block(plan)


def test_other_runtime_fails_without_runtime_under_test() -> None:
    plan = _plan()
    _model(plan).update(runtime="mlx", version="0.29.1", build=None)
    with pytest.raises(RecordError, match=r"llama\.cpp") as caught:
        load_runtime_block(plan)
    assert "runtime_under_test" in str(caught.value)


def test_other_runtime_loads_with_runtime_under_test_and_version() -> None:
    plan = _plan(runtime_under_test=True)
    mlx = copy.deepcopy(_model(plan))
    mlx.update(runtime="mlx", version="0.29.1", build=None)
    plan["runtime"]["models"].append(mlx)
    block = load_runtime_block(plan)
    assert block.models[1].runtime == "mlx"
    assert block.models[1].version == "0.29.1"


def test_mlx_entry_without_version_fails_under_test() -> None:
    plan = _plan(runtime_under_test=True)
    _model(plan).update(runtime="mlx", build=None)
    with pytest.raises(RecordError, match="version"):
        load_runtime_block(plan)


def test_llamacpp_entry_needs_a_build() -> None:
    plan = _plan()
    del _model(plan)["build"]
    with pytest.raises(RecordError, match="build"):
        load_runtime_block(plan)


def test_block_without_tolerance_fails() -> None:
    plan = _plan()
    del plan["runtime"]["tolerance"]
    with pytest.raises(RecordError, match="tolerance"):
        load_runtime_block(plan)


def test_empty_tolerance_fails() -> None:
    with pytest.raises(RecordError, match="tolerance"):
        load_runtime_block(_plan(tolerance=[]))


@pytest.mark.parametrize(
    "entry",
    [
        {"max_abs_change": 0.1},
        {"metric": "a", "item_score": "b", "max_abs_change": 0.1},
        {"metric": "a", "max_abs_change": -0.1},
    ],
)
def test_tolerance_needs_one_target_and_a_non_negative_change(entry: dict[str, Any]) -> None:
    with pytest.raises(RecordError, match="tolerance"):
        load_runtime_block(_plan(tolerance=[entry]))


def test_unknown_key_is_rejected() -> None:
    plan = _plan()
    _model(plan)["quant"] = "Q8_0"
    with pytest.raises(RecordError, match="quant"):
        load_runtime_block(plan)


def test_plan_without_runtime_block_names_the_block() -> None:
    with pytest.raises(RecordError, match="runtime"):
        load_runtime_block({"hypothesis": "x"})


def test_runtime_that_is_not_an_object_fails() -> None:
    with pytest.raises(RecordError, match="runtime"):
        load_runtime_block({"runtime": ["llama.cpp"]})


def test_build_zero_is_a_placeholder_and_fails() -> None:
    plan = _plan()
    _model(plan)["build"] = 0
    with pytest.raises(RecordError, match="build"):
        load_runtime_block(plan)


def test_all_zero_sha256_is_a_placeholder_and_fails() -> None:
    plan = _plan()
    _model(plan)["sha256"] = "0" * 64
    with pytest.raises(RecordError, match="sha256"):
        load_runtime_block(plan)


def test_shipped_plan_template_runtime_block_is_refused() -> None:
    # The template holds placeholders, so an unfilled plan must not pass.
    import json

    from omrs.core.experiment_records.templates import read_template

    with pytest.raises(RecordError):
        load_runtime_block(json.loads(read_template("plan.json")))
