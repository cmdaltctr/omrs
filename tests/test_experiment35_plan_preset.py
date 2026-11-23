"""Experiment 35 ``plan.json`` Clef-Flash server arguments (task 16.34, protocol 4.4).

The main-run preset must equal the preset of the LLM-AggreFact checker runs
(``prefreeze/run_aggrefact.py``), key by key, and the G3 server-argument check (task 5.8)
must read every key.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from types import SimpleNamespace

import pytest
from experiments._lib import llamacpp_runtime
from tests._exp35_fixtures import FOLDER, load

arms = load("arms")

JUDGE_ROLE = "judge-clef-flash"


def _aggrefact_preset() -> dict:
    prefreeze = str(FOLDER / "prefreeze")
    sys.path.insert(0, prefreeze)
    try:
        path = FOLDER / "prefreeze" / "run_aggrefact.py"
        spec = importlib.util.spec_from_file_location("run_aggrefact_under_test", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return dict(module.SERVER_ARGS)
    finally:
        sys.path.remove(prefreeze)


def _plan_preset() -> dict:
    plan = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
    return dict(arms.plan_role(plan, JUDGE_ROLE)["server_args"])


def test_the_main_run_preset_equals_the_aggrefact_preset_key_by_key() -> None:
    expected, found = _aggrefact_preset(), _plan_preset()
    assert sorted(found) == sorted(expected)
    assert {k: found[k] for k in expected} == expected


@pytest.mark.parametrize("key", sorted(_aggrefact_preset()))
def test_the_server_argument_check_reads_every_preset_key(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    preset = _plan_preset()
    model = SimpleNamespace(file="Clef-Flash-Q8_0.gguf", server_args=preset)
    monkeypatch.setattr(
        llamacpp_runtime, "_args_by_file", lambda base_url: {model.file: dict(preset)}
    )
    llamacpp_runtime._check_server_args("http://127.0.0.1:1", [model])
    value = preset[key]
    drifted = {**preset, key: (not value) if isinstance(value, bool) else "drifted"}
    monkeypatch.setattr(llamacpp_runtime, "_args_by_file", lambda base_url: {model.file: drifted})
    with pytest.raises(llamacpp_runtime.PreflightError, match=key):
        llamacpp_runtime._check_server_args("http://127.0.0.1:1", [model])
