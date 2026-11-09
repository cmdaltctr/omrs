"""Tests for ``experiments/_lib/ranking.py`` (change pre-exp35-harness-and-answer-fixes, D4).

The first part copies the Experiment 48 tests of ``ranking_lib.py`` and the
ranking functions of ``sweep_lib.py``. The sections marked "fix" and "lesson"
hold the new behaviour. No server, no router: fakes and tmp folders only.
"""

from __future__ import annotations

import json

import pytest
from experiments._lib.ranking import (
    EmptyResultIdError,
    PopulatedCollectionError,
    answer_fields,
    compare_rankings,
    incomplete_comparisons,
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

from experiments._lib.ranking import server_snapshot  # noqa: E402


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

from experiments._lib.ranking import source_matches  # noqa: E402


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


# --- determinism comparison and incomplete pairs (copied from sweep_lib tests) ----


def test_determinism_reports_question_mode_and_both_rankings():
    left = {"q1": ["c1", "c2", "c3"]}
    right = {"q1": ["c2", "c1", "c3"]}
    mismatches = compare_rankings("dense", left, right)
    assert len(mismatches) == 1
    row = mismatches[0]
    assert row["question"] == "q1"
    assert row["mode"] == "dense"
    assert row["run1"] == ["c1", "c2", "c3"]
    assert row["run2"] == ["c2", "c1", "c3"]


def test_determinism_silent_on_identical_rankings():
    same = {"q1": ["c1", "c2"]}
    assert compare_rankings("hybrid", same, same) == []


def _row(question, mode, ids, error=""):
    return {"question": question, "mode": mode, "error": error, "results": [{"id": i} for i in ids]}


def test_a_failed_repeat_search_is_an_incomplete_comparison():
    baseline = [_row("q1", "dense", ["a"])]
    repeat = [_row("q1", "dense", [], error="boom")]
    found = incomplete_comparisons(baseline, repeat)
    assert [(r["question"], r["mode"]) for r in found] == [("q1", "dense")]
    assert "boom" in found[0]["incomplete"]


def test_a_failed_baseline_search_is_an_incomplete_comparison():
    found = incomplete_comparisons(
        [_row("q1", "dense", [], error="down")], [_row("q1", "dense", [])]
    )
    assert len(found) == 1 and "down" in found[0]["incomplete"]


def test_a_missing_baseline_row_is_an_incomplete_comparison():
    found = incomplete_comparisons([], [_row("q1", "dense", ["a"])])
    assert len(found) == 1 and "baseline" in found[0]["incomplete"]


def test_complete_rows_give_no_incomplete_comparison():
    rows = [_row("q1", "dense", ["a"])]
    assert incomplete_comparisons(rows, rows) == []


# --- fix 3.2: a neighbour list never holds the query chunk ---------------------------


def _vectors(count: int, seed: int) -> dict[str, list[float]]:
    import numpy as np

    rng = np.random.default_rng(seed)
    return {f"c{n:02d}": [float(x) + 0.01 for x in rng.random(6)] for n in range(count)}


def _reference_neighbours(vectors: dict[str, list[float]], query: str, k: int) -> list[str]:
    """Top-k other chunks by cosine, best first; ties by id order (a plain sort)."""

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        return dot / ((sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5))

    others = [c for c in sorted(vectors) if c != query]
    ranked = sorted(others, key=lambda c: -cosine(vectors[query], vectors[c]))
    return ranked[:k]


def test_a_small_slice_lists_every_other_chunk_and_never_the_query():
    exact = _vectors(5, seed=1)
    fast = _vectors(5, seed=101)
    found = neighbour_mismatches(exact, fast, k=10)
    assert found, "the moved vectors must change at least one list"
    for row in found:
        assert len(row["exact"]) == 4 and len(row["fast"]) == 4
        assert row["query"] not in row["exact"]
        assert row["query"] not in row["fast"]
        assert sorted(row["exact"]) == sorted(c for c in exact if c != row["query"])


@pytest.mark.parametrize("count", [5, 6])
def test_a_slice_of_k_or_k_plus_one_chunks_never_lists_the_query(count):
    exact = _vectors(count, seed=2)
    for row in neighbour_mismatches(exact, _vectors(count, seed=102), k=5):
        assert row["query"] not in row["exact"] + row["fast"]
        assert len(row["exact"]) == min(5, count - 1)


def test_a_large_slice_keeps_k_neighbours_in_the_same_order_as_before():
    exact = _vectors(50, seed=3)
    fast = _vectors(50, seed=103)
    found = {row["query"]: row for row in neighbour_mismatches(exact, fast, k=10)}
    assert len(found) > 10
    for query, row in found.items():
        assert len(row["exact"]) == 10
        assert query not in row["exact"] + row["fast"]
        assert row["exact"] == _reference_neighbours(exact, query, 10)
        assert row["fast"] == _reference_neighbours(fast, query, 10)


# --- fix 3.4: the comparison covers the union of both runs' questions ----------------


def test_a_question_only_in_run_2_is_reported():
    found = compare_rankings("dense", {"q1": ["a"]}, {"q1": ["a"], "q9": ["c1"]})
    assert [(row["question"], row["run1"], row["run2"]) for row in found] == [("q9", [], ["c1"])]


def test_a_question_only_in_run_1_is_reported():
    found = compare_rankings("dense", {"q1": ["a"], "q4": ["c1"]}, {"q1": ["a"]})
    assert [(row["question"], row["run1"], row["run2"]) for row in found] == [("q4", ["c1"], [])]


def test_a_question_only_in_run_1_with_an_empty_ranking_is_still_reported():
    """An empty ranking is not the same as no answer: the question is missing from run 2."""
    found = compare_rankings("dense", {"q4": []}, {})
    assert [row["question"] for row in found] == ["q4"]
    assert found[0]["missing_from"] == "run2"


def test_a_missing_question_names_the_run_it_is_missing_from():
    found = compare_rankings("dense", {"q4": ["c1"]}, {"q9": ["c2"]})
    assert {row["question"]: row["missing_from"] for row in found} == {"q4": "run2", "q9": "run1"}


def test_a_question_in_both_runs_with_equal_rankings_is_not_reported():
    assert compare_rankings("dense", {"q1": ["a"], "q2": []}, {"q1": ["a"], "q2": []}) == []


# --- lessons from the PR 195 review (each one has a mutation check) -------------------


def test_lesson_the_result_id_is_the_engines_chunk_id_key():
    """The first run read ``id`` while the engine returns ``chunk_id``: every id was blank."""
    assert result_id({"chunk_id": "c9", "text": "t"}) == "c9"


def test_lesson_a_blank_result_id_is_refused_not_stored():
    with pytest.raises(EmptyResultIdError):
        result_id({"chunk_id": "", "id": "", "text": "t"})


def test_lesson_two_failed_searches_are_an_incomplete_comparison_not_a_match():
    failed = {"question": "q1", "mode": "dense", "error": "boom", "results": []}
    assert compare_rankings("dense", {"q1": []}, {"q1": []}) == []  # why the check is needed
    found = incomplete_comparisons([failed], [failed])
    assert [(row["question"], row["mode"]) for row in found] == [("q1", "dense")]
