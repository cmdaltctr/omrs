"""One reader for llama.cpp ``/models`` replies (PR 222)."""

from __future__ import annotations

from typing import Any

import pytest

from omrs.integrations.llamacpp_runtime.model_list import served_model_names


def test_both_layouts_are_read_in_order_without_repeats() -> None:
    body = {
        "data": [{"id": "a"}, {"id": ""}, "junk"],
        "models": [{"model": "b", "name": "b"}, {"name": "a"}, 3],
    }
    assert served_model_names(body) == ["a", "b"]


def test_a_valid_empty_list_is_empty() -> None:
    assert served_model_names({"data": [], "models": None}) == []


@pytest.mark.parametrize("body", [None, [], {"models": 1}, {"data": "x"}])
def test_a_reply_that_is_not_a_model_list_raises(body: Any) -> None:
    with pytest.raises(ValueError):
        served_model_names(body)
