"""Tests for ``experiments/_lib/timing.py`` (change pre-exp35-harness-and-answer-fixes, D4).

The first part copies the Experiment 48 tests of ``timing_lib.py`` and the
timing functions of ``sweep_lib.py``. The sections marked "fix" and "lesson"
hold the new behaviour. Fakes and tmp folders only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from experiments._lib.timing import (
    LimitMismatchError,
    estimates,
    extrapolate,
    read_speed,
    require_same_limit,
    speed_summary,
    write_json,
    write_jsonl,
)


def test_extrapolation_divides_tokens_by_rate():
    hours = extrapolate(corpus_tokens=36_000_000, tokens_per_second=10_000.0)
    assert hours == pytest.approx(1.0)


def test_extrapolation_financebench_uses_tokens_per_page():
    hours = extrapolate(
        corpus_tokens=None,
        tokens_per_second=2.0,
        tokens_per_page=100.0,
        total_pages=72,
    )
    assert hours == pytest.approx(1.0)


def test_extrapolation_missing_count_names_the_corpus():
    with pytest.raises(ValueError) as exc:
        extrapolate(corpus_tokens=None, tokens_per_second=2.0, corpus="BioASQ")
    assert "BioASQ" in str(exc.value)


def test_same_limit_passes_when_both_are_none_or_equal():
    require_same_limit(None, None, "stage ingest")
    require_same_limit(3, 3, "stage ingest")


@pytest.mark.parametrize(("recorded", "current"), [(1, None), (None, 1), (1, 2)])
def test_a_different_limit_is_refused_and_names_both(recorded, current):
    with pytest.raises(LimitMismatchError) as exc:
        require_same_limit(recorded, current, "stage ingest")
    text = str(exc.value)
    assert "stage ingest" in text and str(recorded) in text and str(current) in text


def test_speed_summary_gives_vectors_per_second_and_the_gain():
    exact = {"freshstack": {"seconds": 10.0, "vectors": 100}}
    fast = {"freshstack": {"seconds": 2.0, "vectors": 100}}
    summary = speed_summary(exact, fast)["freshstack"]
    assert summary["exact_vectors_per_second"] == pytest.approx(10.0)
    assert summary["fast_vectors_per_second"] == pytest.approx(50.0)
    assert summary["speed_gain"] == pytest.approx(5.0)


def test_speed_summary_refuses_slices_that_differ():
    with pytest.raises(ValueError, match="bioasq"):
        speed_summary(
            {"freshstack": {"seconds": 1.0, "vectors": 1}},
            {"bioasq": {"seconds": 1.0, "vectors": 1}},
        )


def test_financebench_tokens_per_page_divides_by_the_slice_pages():
    """Review fix: tokens per page is slice tokens / slice pages, not / chunks."""
    counts = {
        "freshstack": {"tokens": 1000},
        "bioasq": {"tokens": 1000},
        "financebench": {"total_pages": 1000},
    }
    rows = [
        {
            "model": "4b",
            "slice": s,
            "tokens": 10_000,
            "chunks": 50,
            "tokens_per_second": 100.0,
            "peak_rss_mb": 1.0,
            "errors": [],
        }
        for s in ("freshstack", "bioasq", "financebench")
    ]
    out = estimates(counts, rows, financebench_slice_pages=100)
    # 10,000 tokens over 100 pages = 100 tokens per page; 1,000 pages -> 100,000 tokens
    # at 100 tokens/s = 1,000 s = 0.2778 h. Dividing by chunks (50) would give 0.5556 h.
    assert abs(out["4b"]["financebench_hours"] - 1000 / 3600) < 1e-6


def test_financebench_estimate_refuses_without_slice_pages():
    counts = {
        "freshstack": {"tokens": 1},
        "bioasq": {"tokens": 1},
        "financebench": {"total_pages": 10},
    }
    rows = [
        {
            "model": "4b",
            "slice": s,
            "tokens": 1,
            "chunks": 1,
            "tokens_per_second": 1.0,
            "peak_rss_mb": 1.0,
            "errors": [],
        }
        for s in ("freshstack", "bioasq", "financebench")
    ]
    with pytest.raises(ValueError, match="slice pages"):
        estimates(counts, rows, financebench_slice_pages=0)


# --- estimates and read_speed (adapted from the Experiment 48 runner tests) --------


def _timing_row(model, slice_name, **extra):
    row = {
        "model": model,
        "slice": slice_name,
        "files": 1,
        "chunks": 10,
        "tokens": 1000,
        "tokens_per_second": 500.0,
        "peak_rss_mb": 1500.0,
        "errors": [],
    }
    return {**row, **extra}


def _inputs(counts_extra=None, **row_extra):
    counts = {
        "freshstack": {"tokens": 1_000_000},
        "bioasq": {"tokens": 500_000},
        "financebench": {"total_pages": 100},
        **(counts_extra or {}),
    }
    rows = [_timing_row("4b", s, **row_extra) for s in ("freshstack", "bioasq", "financebench")]
    return counts, rows


def test_estimates_key_peak_rss_by_slice_and_divide_tokens_by_rate():
    counts, rows = _inputs()
    out = estimates(counts, rows, financebench_slice_pages=100)
    assert out["4b"]["peak_rss_mb"] == {
        "freshstack": 1500.0,
        "bioasq": 1500.0,
        "financebench": 1500.0,
    }
    assert out["4b"]["freshstack_hours"] == pytest.approx(1_000_000 / 500 / 3600)


def test_read_speed_refuses_a_missing_file_and_names_it_and_the_stage(tmp_path):
    with pytest.raises(SystemExit, match=r"part-c-fast-speed\.json.*--stage fast"):
        read_speed(tmp_path, "fast")


def test_read_speed_reads_the_file_of_the_mode(tmp_path):
    speed = {"freshstack": {"seconds": 8, "vectors": 4}}
    (tmp_path / "part-c-exact-speed.json").write_text(json.dumps(speed), encoding="utf-8")
    assert read_speed(tmp_path, "exact") == speed


# --- fix 3.3: output files are written atomically -------------------------------------


def _rows_then_fail():
    yield {"id": "a", "vector": [1.0]}
    raise RuntimeError("fast-mode step stopped while it wrote the vector file")


@pytest.mark.parametrize("had_old_file", [True, False])
def test_a_jsonl_write_that_fails_part_way_leaves_the_old_file_or_none(tmp_path, had_old_file):
    target = tmp_path / "part-c-fast-freshstack.jsonl"
    if had_old_file:
        target.write_text('{"id": "old"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="stopped while it wrote"):
        write_jsonl(target, _rows_then_fail())
    if had_old_file:
        assert target.read_text(encoding="utf-8") == '{"id": "old"}\n'
    else:
        assert not target.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ([target.name] if had_old_file else [])


@pytest.mark.parametrize("had_old_file", [True, False])
def test_a_json_write_that_fails_part_way_leaves_the_old_file_or_none(
    tmp_path, monkeypatch, had_old_file
):
    target = tmp_path / "part-c-fast-speed.json"
    if had_old_file:
        target.write_text('{"old": true}\n', encoding="utf-8")

    def half_write(self, text, encoding=None, **_):
        with self.open("w", encoding=encoding) as handle:
            handle.write(text[:4])
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", half_write)
    with pytest.raises(OSError, match="disk full"):
        write_json(target, {"new": True})
    monkeypatch.undo()
    if had_old_file:
        assert target.read_text(encoding="utf-8") == '{"old": true}\n'
    else:
        assert not target.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ([target.name] if had_old_file else [])


def test_a_finished_write_replaces_the_old_file_and_leaves_no_temporary_file(tmp_path):
    target = tmp_path / "out.jsonl"
    target.write_text("old\n", encoding="utf-8")
    write_jsonl(target, [{"n": 1}, {"n": 2}])
    assert target.read_text(encoding="utf-8") == '{"n": 1}\n{"n": 2}\n'
    write_json(tmp_path / "out.json", {"a": 1})
    assert json.loads((tmp_path / "out.json").read_text(encoding="utf-8")) == {"a": 1}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.json", "out.jsonl"]


# --- lessons from the PR 195 review (each one has a mutation check) --------------------


def test_lesson_timing_rows_from_a_limit_run_are_refused():
    counts, rows = _inputs(limit=2)
    with pytest.raises(LimitMismatchError, match="timing row"):
        estimates(counts, rows, financebench_slice_pages=100)


def test_lesson_token_counts_from_a_limit_run_are_refused():
    counts, rows = _inputs(counts_extra={"limit": 10})
    with pytest.raises(LimitMismatchError, match="token-counts.json"):
        estimates(counts, rows, financebench_slice_pages=100)


def test_lesson_a_timing_row_that_recorded_an_error_is_refused():
    counts, rows = _inputs(errors=["a.md: ingest status error: boom"])
    with pytest.raises(ValueError, match="boom"):
        estimates(counts, rows, financebench_slice_pages=100)


def test_lesson_estimates_never_use_a_tuple_as_a_json_key():
    """Part B rows are keyed by (model, slice) inside; the written result must still dump."""
    counts, rows = _inputs()
    text = json.dumps(estimates(counts, rows, financebench_slice_pages=100))
    assert '"peak_rss_mb": {"freshstack"' in text
