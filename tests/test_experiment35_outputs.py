"""Experiment 35 ``outputs35.py``: the runner lock and the configuration hash (tasks 3.2, 3.4).

The lock tests open real files on one stage folder. The key tests write a
stage key, change one part of the configuration, and resume.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.run_safety import RunStop
from tests._exp35_fixtures import load

outputs35 = load("outputs35")

QIDS = ["q1", "q2"]
SETTINGS = {
    "retrieval": {"top_k": 10, "reranker_enabled": True},
    "llm": {"provider": "openrouter", "openrouter_api_key": "sk-test-one"},
}
RUNTIME = {"models": [{"role": "reranker", "file": "r.gguf", "sha256": "a" * 64}]}
PROMPTS = {"answer": "b" * 64, "judge": "c" * 64}
COMMIT = "d" * 40


def _config(**change: Any) -> dict[str, Any]:
    parts: dict[str, Any] = {
        "settings": SETTINGS,
        "runtime": RUNTIME,
        "prompts": PROMPTS,
        "commit": COMMIT,
    }
    parts.update(change)
    return outputs35.config_fields(**parts)


def _key(**change: Any) -> dict[str, Any]:
    return outputs35.run_key(None, None, 20261101, QIDS, config=_config(**change))


# --- 3.2 runner lock -------------------------------------------------------------------


def test_second_runner_on_a_held_folder_stops_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = outputs35.RowFile(tmp_path, "answer", _key(), resume=False)
    first.append({"qid": "q1"})
    reads: list[Path] = []
    real = Path.read_text

    def spy(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(self)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    with pytest.raises(RunStop, match=r"\.lock"):
        outputs35.RowFile(tmp_path, "answer", _key(), resume=True)
    assert reads == []
    monkeypatch.undo()
    first.close()


def test_resume_opens_the_folder_after_the_first_runner_ends(tmp_path: Path) -> None:
    with outputs35.RowFile(tmp_path, "answer", _key(), resume=False) as first:
        first.append({"qid": "q1"})
    with outputs35.RowFile(tmp_path, "answer", _key(), resume=True) as later:
        assert later.done_ids("qid") == {"q1"}


def test_a_refused_open_releases_the_lock(tmp_path: Path) -> None:
    outputs35.RowFile(tmp_path, "answer", _key(), resume=False).close()
    with pytest.raises(outputs35.StageFileExistsError):
        outputs35.RowFile(tmp_path, "answer", _key(), resume=False)
    outputs35.RowFile(tmp_path, "answer", _key(), resume=True).close()


# --- 3.4 configuration hash in the resume key ------------------------------------------


def test_key_holds_one_hash_per_part_and_the_commit() -> None:
    key = _key()
    assert set(key) == {
        "limit",
        "corpus_sample",
        "seed",
        "qids",
        "settings_sha256",
        "runtime_sha256",
        "prompt_sha256",
        "harness_commit",
    }
    assert len(key["settings_sha256"]) == 64
    assert key["prompt_sha256"] == PROMPTS
    assert key["harness_commit"] == COMMIT


def test_settings_hash_leaves_out_keys() -> None:
    other_key = {**SETTINGS, "llm": {**SETTINGS["llm"], "openrouter_api_key": "sk-test-two"}}
    assert _key(settings=other_key) == _key()
    assert "sk-test" not in json.dumps(_key())


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"settings": {**SETTINGS, "retrieval": {"top_k": 20}}}, "settings_sha256"),
        ({"runtime": {"models": [{"file": "r.gguf", "sha256": "e" * 64}]}}, "runtime_sha256"),
        ({"prompts": {**PROMPTS, "answer": "f" * 64}}, "prompt_sha256"),
        ({"commit": "0" * 40}, "harness_commit"),
    ],
)
def test_resume_with_a_changed_part_refuses_and_names_it(
    tmp_path: Path, change: dict[str, Any], field: str
) -> None:
    outputs35.RowFile(tmp_path, "answer", _key(), resume=False).close()
    with pytest.raises(outputs35.ResumeMismatchError, match=field) as caught:
        outputs35.RowFile(tmp_path, "answer", _key(**change), resume=True)
    others = {"settings_sha256", "runtime_sha256", "prompt_sha256", "harness_commit"} - {field}
    assert not any(name in str(caught.value) for name in others)


def test_finished_stage_with_a_changed_key_refuses_before_the_skip(tmp_path: Path) -> None:
    with outputs35.RowFile(tmp_path, "search", _key(), resume=False) as log:
        log.mark_done({"rows": 0})
    changed = _key(runtime={"models": []})
    with pytest.raises(outputs35.ResumeMismatchError, match="runtime_sha256"):
        outputs35.check_stage_key(tmp_path, "search", changed)
    with pytest.raises(outputs35.ResumeMismatchError, match="runtime_sha256"):
        outputs35.RowFile(tmp_path, "search", changed, resume=True)


def test_ingest_done_marker_holds_the_configuration(tmp_path: Path) -> None:
    with outputs35.RowFile(tmp_path, "ingest", _key(), resume=False) as log:
        log.mark_done({"files": 2})
    marker = json.loads((tmp_path / ".done-ingest.json").read_text(encoding="utf-8"))
    assert marker["files"] == 2
    assert marker["config"] == {k: _key()[k] for k in outputs35.CONFIG_FIELDS}


def test_non_ingest_stage_refuses_an_index_built_with_another_configuration(
    tmp_path: Path,
) -> None:
    with outputs35.RowFile(tmp_path, "ingest", _key(), resume=False) as log:
        log.mark_done({"files": 2})
    outputs35.check_index_config(tmp_path, _config())
    with pytest.raises(outputs35.ResumeMismatchError, match="settings_sha256"):
        outputs35.check_index_config(tmp_path, _config(settings={"chunking": {"size": 512}}))


def test_key_without_configuration_keeps_todays_shape() -> None:
    key = outputs35.run_key(None, None, 1, QIDS)
    assert key == {"limit": None, "corpus_sample": None, "seed": 1, "qids": QIDS}
