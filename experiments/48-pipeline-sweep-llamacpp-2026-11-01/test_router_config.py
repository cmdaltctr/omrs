"""Tests for the scratch router settings of the sweep (change task 3.5, design D2, D6, D6a).

Run with: uv run --no-sync pytest test_router_config.py -q

No test starts a server or reads a real model file: ``SWEEP_GGUF_DIR`` points
at a tmp folder of empty ``.gguf`` files.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest
import router_config as rc

EXP_DIR = Path(__file__).resolve().parent
PLAN = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
MODELS = PLAN["runtime"]["models"]
BASELINE_FILE = "Qwen3-Embedding-4B-Q8_0.gguf"


@pytest.fixture
def gguf_dir(tmp_path, monkeypatch):
    """A tmp ``SWEEP_GGUF_DIR`` with one empty file per plan model."""
    folder = tmp_path / "gguf"
    folder.mkdir()
    for model in MODELS:
        (folder / model["file"]).write_bytes(b"")
    monkeypatch.setenv(rc.GGUF_DIR_ENV, str(folder))
    return folder


def _entries_by_file(values: dict) -> dict[str, dict]:
    return {Path(e["file"]).name: e for e in values["llamacpp_models"].values()}


def _expected_preset(server_args: dict) -> dict:
    """The plan values in the router's spelling: on/off words for flash-attn and fit."""
    expected = {}
    for key, value in server_args.items():
        if key == "spec-type":
            continue  # D6a: not a preset key; the b11941 default is none
        if key in ("flash-attn", "fit") and isinstance(value, bool):
            value = "on" if value else "off"
        expected[key] = value
    return expected


# --- entries come from plan.json ---------------------------------------------


def test_one_entry_per_plan_model_with_its_server_args(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    entries = _entries_by_file(values)
    assert sorted(entries) == sorted(m["file"] for m in MODELS)
    for model in MODELS:
        entry = entries[model["file"]]
        assert entry["preset"] == _expected_preset(model["server_args"])
        assert entry["file"] == str(gguf_dir / model["file"])
        assert entry["sha256"] == model["sha256"]
        assert entry["model"] == f"{model['repository']}:Q8_0"


def test_omrs_refuses_the_raw_plan_spelling_at_three_keys():
    """Documents the refusal the report names: OMRS cannot take plan.json as written."""
    from omrs.config.llamacpp_preset import preset_problems

    refused = {p.key for m in MODELS for p in preset_problems(m["server_args"])}
    assert refused == {"flash-attn", "fit", "spec-type"}


def test_every_entry_passes_the_omrs_entry_checks(gguf_dir):
    from omrs.config.llamacpp_models import (
        LlamaCppModelEntry,
        check_model_entry,
        embedding_preset_problem,
    )

    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    for data in values["llamacpp_models"].values():
        entry, problems = check_model_entry(data)
        assert problems == []
        assert isinstance(entry, LlamaCppModelEntry)
        if data["preset"].get("embeddings"):
            assert embedding_preset_problem(entry) is None


def test_a_spec_type_other_than_none_stops_the_run():
    args = {"ctx-size": 16384, "spec-type": "draft"}
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.preset_from_server_args(args, file="x.gguf")
    assert "spec-type" in str(exc.value)
    assert "x.gguf" in str(exc.value)


# --- SWEEP_GGUF_DIR ------------------------------------------------------------


def test_unset_gguf_dir_stops_and_names_the_variable(monkeypatch):
    monkeypatch.delenv(rc.GGUF_DIR_ENV, raising=False)
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.gguf_dir()
    assert "SWEEP_GGUF_DIR" in str(exc.value)


def test_blank_gguf_dir_stops_and_names_the_variable(monkeypatch):
    monkeypatch.setenv(rc.GGUF_DIR_ENV, "  ")
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.gguf_dir()
    assert "SWEEP_GGUF_DIR" in str(exc.value)


def test_missing_model_file_stops_and_names_the_file(gguf_dir):
    missing = gguf_dir / "Qwen3-Embedding-8B-Q8_0.gguf"
    missing.unlink()
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    assert str(missing) in str(exc.value)
    assert "SWEEP_GGUF_DIR" in str(exc.value)


# --- router settings (D2) ------------------------------------------------------


def test_router_is_managed_on_loopback_scratch_port(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    assert values["llamacpp_router_server"] == "managed"
    assert values["llamacpp_router_url"] == f"http://127.0.0.1:{rc.ROUTER_PORT}/v1"
    assert rc.ROUTER_PORT == 18080
    assert values["embed_provider"] == "llamacpp"
    assert values["local_backend"] == "llamacpp"
    assert values["metadata_llm_provider"] == "local"
    assert values["answer"]["verify_provider"] == "local"


def test_roles_name_the_listed_models(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file="Qwen3-Embedding-8B-Q8_0.gguf")
    names = {Path(e["file"]).name: e["model"] for e in values["llamacpp_models"].values()}
    assert values["llamacpp_embed_model"] == names["Qwen3-Embedding-8B-Q8_0.gguf"]
    assert values["llamacpp_chat_model"] == names["Qwen3-4B-Q8_0.gguf"]
    assert values["answer"]["model"] == names["Qwen3-4B-Q8_0.gguf"]
    assert values["answer"]["verify_model"] == names["Qwen3-4B-Q8_0.gguf"]


def test_part_b_loads_one_model_at_a_time(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE, part_b=True)
    assert values["llamacpp_router_models_max"] == 1


def test_part_a_leaves_the_model_limit_at_its_default(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    assert "llamacpp_router_models_max" not in values


# --- Part C fast mode (D6a) ----------------------------------------------------


def test_fast_mode_differs_from_exact_by_the_two_keys_only(gguf_dir):
    exact = _entries_by_file(rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE))
    fast = _entries_by_file(rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE, fast=True))
    for name in exact:
        if name != BASELINE_FILE:
            assert fast[name] == exact[name]
    left, right = exact[BASELINE_FILE]["preset"], fast[BASELINE_FILE]["preset"]
    changed = {k: right[k] for k in right if left.get(k) != right[k]}
    assert changed == {"parallel": 8, "kv-unified": True}
    assert set(left) == set(right)


# --- the written file and the OMRS settings code -------------------------------


def test_written_file_has_no_omrs_problems_and_settings_load(gguf_dir, tmp_path, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OMRS_STATE_DIR", str(tmp_path / "state"))
    for name in [k for k in os.environ if k.startswith("LLAMACPP_")]:
        monkeypatch.delenv(name)
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE, part_b=True)
    rc.write_settings(values, config)
    rc.check_settings_file(config)  # raises on any problem
    summary = rc.dry_run_summary(rc.load_settings())
    assert summary["llamacpp_router_url"] == values["llamacpp_router_url"]
    assert summary["llamacpp_router_server"] == "managed"
    assert summary["llamacpp_router_models_max"] == 1
    assert summary["role_problems"] == []
    assert sorted(summary["models"]) == sorted(
        e["model"] for e in values["llamacpp_models"].values()
    )


def test_a_problem_in_the_file_stops_and_names_the_key(tmp_path):
    config = tmp_path / "config"
    rc.write_settings({"llamacpp_router_models_max": 99}, config)
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.check_settings_file(config)
    assert "llamacpp_router_models_max" in str(exc.value)


def test_verify_url_is_the_router_url_without_v1():
    class _Settings:
        llamacpp_router_url = "http://127.0.0.1:18080/v1"

    assert rc.verify_url(_Settings()) == "http://127.0.0.1:18080"


def test_held_keeps_a_lease_session_open_for_the_router_name():
    """Direct requests bypass the lease, so the idle stop must see a session open."""
    import contextlib

    seen = []

    class _Router:
        @contextlib.contextmanager
        def model_session(self, name):
            seen.append(("open", name))
            yield "http://127.0.0.1:18080"
            seen.append(("close", name))

    with rc.held(_Router(), PLAN, BASELINE_FILE) as name:
        assert seen == [("open", "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0")]
        assert name == "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
    assert seen[-1] == ("close", name)


# --- environment set-up --------------------------------------------------------


def test_prepare_environment_removes_every_llamacpp_key(monkeypatch):
    environ = {"LLAMACPP_EMBED_URL": "x", "LLAMACPP_CHAT_MODEL": "y", "HOME": "/h"}
    removed = rc.prepare_environment({"VECTOR_STORE": "lancedb"}, environ)
    assert sorted(removed) == ["LLAMACPP_CHAT_MODEL", "LLAMACPP_EMBED_URL"]
    assert not [k for k in environ if k.startswith("LLAMACPP_")]
    assert environ["OMRS_CONFIG_DIR"] == str(rc.CONFIG_DIR)
    assert environ["OMRS_STATE_DIR"] == str(rc.STATE_DIR)
    assert environ["VECTOR_STORE"] == "lancedb"


@pytest.mark.parametrize("runner", ["run_part_a", "run_timing"])
def test_runner_set_up_leaves_no_llamacpp_key(runner, monkeypatch):
    monkeypatch.setattr(os, "environ", dict(os.environ))
    os.environ["LLAMACPP_EMBED_URL"] = "http://127.0.0.1:9931/v1"
    monkeypatch.setattr(sys, "path", list(sys.path))
    sys.modules.pop(runner, None)
    importlib.import_module(runner)
    sys.modules.pop(runner, None)
    assert [k for k in os.environ if k.startswith("LLAMACPP_")] == []
    assert os.environ["OMRS_STATE_DIR"] == str(rc.STATE_DIR)


# --- memory sampling (portable) -----------------------------------------------


def test_router_memory_is_none_without_a_server_record(tmp_path):
    assert rc.router_memory_bytes(tmp_path / "state") is None


def test_router_memory_reads_the_recorded_pid(tmp_path):
    from omrs.integrations.llamacpp_runtime.router_spec import router_dir
    from omrs.integrations.llamacpp_runtime.state import ServerRecord, write_server_record

    folder = router_dir(tmp_path)
    folder.mkdir(parents=True)
    record = ServerRecord(
        pid=os.getpid(),
        port=18080,
        binary=sys.executable,
        digest="d",
        build=None,
        state="running",
        generation=1,
    )
    write_server_record(folder, record)
    found = rc.router_memory_bytes(tmp_path)
    assert found is not None and found > 0


def test_router_pids_is_empty_without_a_server_record(tmp_path):
    assert rc.router_pids(tmp_path / "state") == set()


def test_router_pids_holds_the_router_and_its_children(tmp_path, monkeypatch):
    from omrs.integrations.llamacpp_runtime import children
    from omrs.integrations.llamacpp_runtime.router_spec import router_dir
    from omrs.integrations.llamacpp_runtime.state import ServerRecord, write_server_record

    folder = router_dir(tmp_path)
    folder.mkdir(parents=True)
    record = ServerRecord(
        pid=os.getpid(),
        port=18080,
        binary=sys.executable,
        digest="d",
        build=None,
        state="running",
        generation=1,
    )
    write_server_record(folder, record)
    monkeypatch.setattr(children, "direct_children", lambda pid: [901, 902])
    assert rc.router_pids(tmp_path) == {os.getpid(), 901, 902}
