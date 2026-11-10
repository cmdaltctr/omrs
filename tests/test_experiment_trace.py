"""``experiments/_lib/trace.py`` (experiment-35 task 2.6, design D8).

The trace writer appends one secret-free JSON line per query and major stage.
It never writes to stdout, because stdout is the MCP protocol channel.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from experiments._lib.trace import D8_FIELDS, TraceWriter

_SETTINGS = {"retrieval": {"top_k": 10}, "chunking": {"chunk_overlap": 100}}
_MODELS = {"embedding": {"file": "Qwen3-Embedding-4B-Q8_0.gguf", "sha256": "ab" * 32}}


def _writer(path: Path) -> TraceWriter:
    return TraceWriter(
        path,
        benchmark_revision="exp35-r1",
        run_id="run-001",
        arm="dense-rerank",
        repetition=2,
        effective_settings=_SETTINGS,
        model_identities=_MODELS,
    )


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _full_row(writer: TraceWriter) -> None:
    writer.write(
        stage="retrieve",
        dataset="financebench",
        question_id="q-17",
        reader_route="pdf:liteparse",
        chunk_counts={"indexed": 412, "retrieved": 10},
        retrieved={
            "chunk_ids": ["c1", "c2"],
            "parent_ids": ["p1", "p1"],
            "page_ids": ["5", "6"],
            "scores": [0.91, 0.83],
        },
        rerank_input=["c2", "c1"],
        rerank_output=["c1", "c2"],
        durations_s={"retrieve": 0.12, "rerank": 0.4},
        token_counts={"prompt_tokens": 800, "completion_tokens": 90},
        answer_model="glm-5.3",
        judge_model="granite-judge",
    )


def test_writer_never_writes_to_stdout(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    writer = _writer(tmp_path / "trace.jsonl")
    _full_row(writer)
    writer.write(
        stage="answer", dataset="financebench", question_id="q-18", status="error", error="boom"
    )
    assert capfd.readouterr().out == ""


def test_failed_query_keeps_its_row_with_error_status(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    writer = _writer(path)
    writer.write(
        stage="retrieve",
        dataset="freshstack",
        question_id="q-9",
        status="error",
        error="TimeoutError: store did not answer",
    )
    (row,) = _rows(path)
    assert row["status"] == "error"
    assert row["error"] == "TimeoutError: store did not answer"
    assert row["question_id"] == "q-9"
    assert row["retrieved"] is None


def test_degraded_status_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    _writer(path).write(
        stage="retrieve",
        dataset="d",
        question_id="q",
        status="degraded",
        error="reranker fell back to dense order",
    )
    (row,) = _rows(path)
    assert row["status"] == "degraded"


def test_unknown_status_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with pytest.raises(ValueError, match="status"):
        _writer(path).write(stage="retrieve", dataset="d", question_id="q", status="fine")
    assert not path.exists()


def test_sample_trace_holds_every_d8_field(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    writer = _writer(path)
    _full_row(writer)
    (row,) = _rows(path)
    assert set(D8_FIELDS) <= set(row)
    assert row["benchmark_revision"] == "exp35-r1"
    assert row["run_id"] == "run-001"
    assert row["arm"] == "dense-rerank"
    assert row["repetition"] == 2
    assert row["dataset"] == "financebench"
    assert row["question_id"] == "q-17"
    assert row["effective_settings"] == _SETTINGS
    assert row["model_identities"] == _MODELS
    assert row["reader_route"] == "pdf:liteparse"
    assert row["chunk_counts"] == {"indexed": 412, "retrieved": 10}
    assert row["retrieved"]["chunk_ids"] == ["c1", "c2"]
    assert row["rerank_input"] == ["c2", "c1"]
    assert row["rerank_output"] == ["c1", "c2"]
    assert row["durations_s"] == {"retrieve": 0.12, "rerank": 0.4}
    assert row["token_counts"] == {"prompt_tokens": 800, "completion_tokens": 90}
    assert row["answer_model"] == "glm-5.3"
    assert row["judge_model"] == "granite-judge"
    assert row["status"] == "ok"
    assert row["error"] is None


def test_each_write_is_one_line(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    writer = _writer(path)
    for n in range(3):
        writer.write(stage="retrieve", dataset="d", question_id=f"q{n}")
    assert [r["question_id"] for r in _rows(path)] == ["q0", "q1", "q2"]


@pytest.mark.parametrize(
    "key", ["api_key", "OPENROUTER_API_KEY", "access_token", "Authorization", "client_secret"]
)
def test_secret_looking_key_in_a_row_is_refused(tmp_path: Path, key: str) -> None:
    path = tmp_path / "trace.jsonl"
    with pytest.raises(ValueError, match="secret"):
        _writer(path).write(
            stage="answer",
            dataset="d",
            question_id="q",
            token_counts={key: "x", "prompt_tokens": 1},
        )
    assert not path.exists()


def test_nested_secret_key_in_settings_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="secret"):
        TraceWriter(
            tmp_path / "trace.jsonl",
            benchmark_revision="r",
            run_id="x",
            arm="a",
            repetition=1,
            effective_settings={"llm": {"providers": [{"api_key": "sk-123"}]}},
            model_identities={},
        )


def test_token_count_keys_are_not_mistaken_for_secrets(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    _writer(path).write(
        stage="answer",
        dataset="d",
        question_id="q",
        token_counts={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    )
    assert len(_rows(path)) == 1


def test_parent_folder_is_created(tmp_path: Path) -> None:
    path = tmp_path / "output" / "traces" / "trace.jsonl"
    _writer(path).write(stage="retrieve", dataset="d", question_id="q")
    assert path.is_file()
