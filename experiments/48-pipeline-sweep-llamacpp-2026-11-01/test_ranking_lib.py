"""Tests for the ranking keys and the Part C neighbour comparison (review fixes, 2026-11-08).

Run with: uv run --no-sync pytest test_ranking_lib.py -q
"""

from __future__ import annotations

import json

import pytest
from ranking_lib import (
    EmptyResultIdError,
    PopulatedCollectionError,
    answer_fields,
    neighbour_mismatches,
    require_empty_collection,
    result_id,
    write_props_snapshot,
)


def test_result_id_prefers_chunk_id():
    assert result_id({"chunk_id": "c1", "id": "x"}) == "c1"


def test_result_id_falls_back_to_id():
    assert result_id({"id": "x"}) == "x"


@pytest.mark.parametrize("item", [{}, {"chunk_id": ""}, {"id": ""}, {"chunk_id": None}])
def test_result_id_refuses_a_blank_id(item):
    with pytest.raises(EmptyResultIdError, match="chunk_id"):
        result_id(item)


def _unit(*xs: float) -> list[float]:
    norm = sum(x * x for x in xs) ** 0.5
    return [x / norm for x in xs]


VECTORS = {
    "a": _unit(1, 0, 0),
    "b": _unit(0.9, 0.1, 0),
    "c": _unit(0.3, 1, 0),
    "d": _unit(0.2, 0.9, 0.1),
}


def test_identical_vectors_give_no_neighbour_change():
    assert neighbour_mismatches(VECTORS, dict(VECTORS), k=2) == []


def test_a_moved_vector_names_the_query_and_both_lists():
    moved = dict(VECTORS)
    moved["b"] = _unit(0, 0.95, 0.05)  # b now sits next to c and d, not a
    found = neighbour_mismatches(VECTORS, moved, k=1)  # a: b under exact, c under fast
    queries = {m["query"] for m in found}
    assert "a" in queries
    row = next(m for m in found if m["query"] == "a")
    assert row["exact"] != row["fast"]


def test_different_id_sets_are_refused():
    with pytest.raises(ValueError, match="same chunk ids"):
        neighbour_mismatches(VECTORS, {"a": VECTORS["a"]}, k=2)


# --- /props snapshot (spec: pin every server argument; review finding 4) ------

from ranking_lib import server_snapshot  # noqa: E402


def test_snapshot_reads_props_per_model_and_lists_llama_arg_names():
    calls = []

    def fake_get(path):
        calls.append(path)
        return {"build_info": "b11941", "default_generation_settings": {"speculative": False}}

    snap = server_snapshot(["m:Q8_0"], fake_get, environ={"LLAMA_ARG_CTX_SIZE": "9", "PATH": "x"})
    assert calls == ["/props?model=m%3AQ8_0"]
    assert snap["props"]["m:Q8_0"]["build_info"] == "b11941"
    assert snap["llama_arg_env"] == ["LLAMA_ARG_CTX_SIZE"]


def test_snapshot_refuses_an_empty_props_answer():
    with pytest.raises(ValueError, match="/props"):
        server_snapshot(["m"], lambda path: {}, environ={})


# --- gold-source match on the file name only (review fix, 2026-11-08) --------

from ranking_lib import source_matches  # noqa: E402


def test_match_uses_the_file_name():
    assert source_matches("/data/x/Kalai - Why Language Models Hallucinate.pdf", "hallucinate")


def test_a_folder_name_does_not_match():
    assert not source_matches("/runs/coding-test/3M_2023Q2_10Q.pdf", "coding")


# --- answer rows keep the verification fields (gap 3) ---------------------------


def test_answer_fields_keep_what_the_engine_returns():
    answer = {"status": "ok", "verified": True, "answer": "x", "citations": [1]}
    fields = answer_fields(answer, verify=True)
    assert fields["status"] == "ok"
    assert fields["verified"] is True
    assert fields["error"] == ""


def test_answer_fields_keep_failing_claims_and_do_not_call_them_an_error():
    claims = [{"claim": "c", "verdict": "unsupported", "ordinals": [1]}]
    answer = {"status": "unverified_claims", "unverified_claims": claims}
    fields = answer_fields(answer, verify=True)
    assert fields["unverified_claims"] == claims
    assert fields["error"] == ""


def test_a_skipped_verification_on_a_verify_run_is_an_error_row():
    answer = {"status": "ok", "verification_skipped": "verification provider unavailable"}
    fields = answer_fields(answer, verify=True)
    assert fields["verification_skipped"] == "verification provider unavailable"
    assert "verification provider unavailable" in fields["error"]


def test_a_missing_verification_on_a_verify_run_is_an_error_row():
    fields = answer_fields({"status": "ok", "answer": "x"}, verify=True)
    assert fields["verified"] is False
    assert "verification" in fields["error"]


def test_a_plain_run_needs_no_verification():
    assert answer_fields({"status": "ok", "answer": "x"}, verify=False)["error"] == ""


def test_an_engine_error_status_is_an_error_row():
    fields = answer_fields({"status": "error", "error": "model gone"}, verify=False)
    assert "model gone" in fields["error"]


# --- one props snapshot writer for both runners (gap 2) -------------------------


def test_props_snapshot_appends_a_line_with_props_env_names_and_argv(tmp_path, monkeypatch):
    import io
    import urllib.request

    seen = []

    def fake_urlopen(url, timeout):
        seen.append(url)
        return io.BytesIO(b'{"n_ctx": 4096}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    target = tmp_path / "server-props.jsonl"
    for _ in range(2):
        write_props_snapshot(
            "http://127.0.0.1:1", ["m 1"], {"LLAMA_ARG_X": "1", "HOME": "h"}, target, ["run.py"]
        )
    lines = [json.loads(line) for line in target.read_text().splitlines()]
    assert len(lines) == 2
    assert seen[0] == "http://127.0.0.1:1/props?model=m%201"
    assert lines[0]["props"] == {"m 1": {"n_ctx": 4096}}
    assert lines[0]["llama_arg_env"] == ["LLAMA_ARG_X"]
    assert lines[0]["argv"] == ["run.py"]


# --- a resumed slice must not mix old and new files (gap 5) ---------------------


def test_a_populated_collection_is_refused_and_named():
    with pytest.raises(PopulatedCollectionError, match="sweep43_timing_4b_bioasq"):
        require_empty_collection("sweep43_timing_4b_bioasq", 12)


def test_an_empty_collection_passes():
    require_empty_collection("sweep43_timing_4b_bioasq", 0)
