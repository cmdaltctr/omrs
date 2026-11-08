"""Timing-runner tests for the PR 195 review fixes (CodeRabbit, 2026-11-08).

Run with: uv run --no-sync pytest test_timing_review.py -q

Fakes and tmp folders only: no server, no router, no write to ``output/``.
"""

from __future__ import annotations

import json
import types

import pytest
from sweep_lib import LimitMismatchError
from test_harness_rows import _stage_model


def _rows(timing):
    return [json.loads(x) for x in (timing.OUTPUT / "timing-4b.jsonl").read_text().splitlines()]


# --- comment 9: a returned ingest failure lands in the row's errors ---------------


def test_a_returned_ingest_error_is_recorded_in_the_row(timing, monkeypatch, tmp_path):
    result = {"status": "error", "message": "All 1 file(s) failed to index."}
    _stage_model(timing, monkeypatch, tmp_path, done=[], counts={}, result=result)
    for row in _rows(timing):
        assert any("All 1 file(s) failed" in e for e in row["errors"])


def test_a_clean_ingest_leaves_the_row_errors_empty(timing, monkeypatch, tmp_path):
    _stage_model(timing, monkeypatch, tmp_path, done=[], counts={}, result={"status": "ok"})
    assert all(row["errors"] == [] for row in _rows(timing))


# --- comment 2: a limited run's rows cannot stand in for a full run ---------------


def test_a_row_records_the_limit_of_its_run(timing, monkeypatch, tmp_path):
    _stage_model(timing, monkeypatch, tmp_path, done=[], counts={}, limit=1)
    assert all(row["limit"] == 1 for row in _rows(timing))


def test_done_rows_from_a_limited_run_are_refused_on_a_full_run(timing, monkeypatch, tmp_path):
    with pytest.raises(LimitMismatchError, match="--limit 1"):
        _stage_model(timing, monkeypatch, tmp_path, done=["freshstack"], counts={}, done_limit=1)


def test_done_rows_from_the_same_limit_are_skipped(timing, monkeypatch, tmp_path):
    ingested = _stage_model(
        timing, monkeypatch, tmp_path, done=["freshstack"], counts={}, limit=1, done_limit=1
    )
    assert "sweep43_timing_4b_freshstack" not in ingested


# --- comments 10 and 11: extrapolation ---------------------------------------------


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


def _extrapolate_inputs(timing, *, counts_extra=None, **row_extra):
    counts = {
        "freshstack": {"tokens": 1_000_000},
        "bioasq": {"tokens": 500_000},
        "financebench": {"total_pages": 100},
        **(counts_extra or {}),
    }
    (timing.OUTPUT / "token-counts.json").write_text(json.dumps(counts), encoding="utf-8")
    rows = [_timing_row("4b", s, **row_extra) for s in ("freshstack", "bioasq", "financebench")]
    (timing.OUTPUT / "timing-4b.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )


def test_extrapolation_writes_estimates_with_peak_rss_keyed_by_slice(timing):
    _extrapolate_inputs(timing)
    timing.stage_extrapolate()
    estimates = json.loads((timing.OUTPUT / "estimates.json").read_text())
    assert estimates["4b"]["peak_rss_mb"] == {
        "freshstack": 1500.0,
        "bioasq": 1500.0,
        "financebench": 1500.0,
    }
    assert estimates["4b"]["freshstack_hours"] == pytest.approx(1_000_000 / 500 / 3600)


def test_extrapolation_refuses_a_row_that_recorded_an_error(timing):
    _extrapolate_inputs(timing, errors=["a.md: ingest status error: boom"])
    with pytest.raises(ValueError, match="boom"):
        timing.stage_extrapolate()
    assert not (timing.OUTPUT / "estimates.json").exists()


def test_extrapolation_refuses_token_counts_from_a_limited_run(timing):
    _extrapolate_inputs(timing, counts_extra={"limit": 10})
    with pytest.raises(LimitMismatchError, match="token-counts.json"):
        timing.stage_extrapolate()


def test_extrapolation_refuses_timing_rows_from_a_limited_run(timing):
    _extrapolate_inputs(timing, limit=2)
    with pytest.raises(LimitMismatchError, match="timing row"):
        timing.stage_extrapolate()


def test_tokenize_refuses_existing_counts_from_another_limit(timing):
    (timing.OUTPUT / "token-counts.json").write_text('{"limit": 10}', encoding="utf-8")
    with pytest.raises(LimitMismatchError, match="--limit 10"):
        timing.stage_tokenize({}, None, object())


def test_tokenize_skips_existing_counts_of_the_same_limit(timing, capsys):
    (timing.OUTPUT / "token-counts.json").write_text('{"limit": 10}', encoding="utf-8")
    timing.stage_tokenize({}, 10, object())
    assert "already done" in capsys.readouterr().out


def test_tokenize_writes_the_limit_with_the_counts(timing, monkeypatch, tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pypdf import PdfWriter

    data = tmp_path / "data"
    manifest = data / "experiments/freshstack-corpus/langchain_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"freshstack_id": "f1", "text": "t"}) + "\n", encoding="utf-8")
    corpus = data / "benchmarks/bioasq/text-corpus/test-00000-of-00001.parquet"
    corpus.parent.mkdir(parents=True)
    pq.write_table(pa.table({"id": ["b1"], "passage": ["p"]}), corpus)
    pdfs = data / "benchmarks/financebench/pdfs"
    pdfs.mkdir(parents=True)
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    with (pdfs / "x.pdf").open("wb") as handle:
        writer.write(handle)
    monkeypatch.setattr(timing, "DATA", data)
    monkeypatch.setattr(timing, "chunk_texts_markdown", lambda paths: ["chunk"] * len(paths))
    monkeypatch.setattr(timing, "tokenize_count", lambda texts, model: len(texts))
    monkeypatch.setattr(timing.router_config, "held", lambda *a: _Held())
    timing.stage_tokenize({}, 1, object())
    assert json.loads((timing.OUTPUT / "token-counts.json").read_text())["limit"] == 1


class _Held:
    def __enter__(self):
        return "name"

    def __exit__(self, *exc):
        return False


# --- comment 12: Part C records the speed of each mode -----------------------------


def _part_c_inputs(timing, monkeypatch, seconds):
    slices = timing.OUTPUT / "slices"
    slices.mkdir()
    for name in ("freshstack", "bioasq", "financebench"):
        (slices / f"{name}-chunks.jsonl").write_text(
            "".join(json.dumps({"id": f"{name}{i}", "text": "t"}) + "\n" for i in range(4)),
            encoding="utf-8",
        )
    clock = iter(seconds)
    monkeypatch.setattr(timing, "time", types.SimpleNamespace(perf_counter=lambda: next(clock)))
    monkeypatch.setattr(timing, "check_runtime", lambda *a: None)
    monkeypatch.setattr(timing.router_config, "held", lambda *a: _Held())
    monkeypatch.setattr(
        timing,
        "embed_direct",
        lambda texts, name, concurrency: [[1.0, float(i)] for i, _ in enumerate(texts)],
    )


def test_each_mode_writes_seconds_and_vectors_per_slice(timing, monkeypatch):
    # perf_counter is read twice per slice: start, end.
    _part_c_inputs(timing, monkeypatch, [0, 8, 10, 18, 20, 28])
    timing.stage_part_c("exact", {}, object())
    speed = json.loads((timing.OUTPUT / "part-c-exact-speed.json").read_text())
    assert speed["freshstack"] == {"seconds": 8, "vectors": 4}
    assert set(speed) == {"freshstack", "bioasq", "financebench"}


def _write_vectors(timing, mode):
    for name in ("freshstack", "bioasq", "financebench"):
        (timing.OUTPUT / f"part-c-{mode}-{name}.jsonl").write_text(
            "".join(
                json.dumps({"id": f"{name}{i}", "vector": [1.0, float(i)]}) + "\n" for i in range(4)
            ),
            encoding="utf-8",
        )


def _write_speed(timing, mode, seconds):
    (timing.OUTPUT / f"part-c-{mode}-speed.json").write_text(
        json.dumps(
            {
                n: {"seconds": seconds, "vectors": 4}
                for n in ("freshstack", "bioasq", "financebench")
            }
        ),
        encoding="utf-8",
    )


def test_compare_reports_both_speeds_and_the_gain(timing):
    _write_vectors(timing, "exact")
    _write_vectors(timing, "fast")
    _write_speed(timing, "exact", 8.0)
    _write_speed(timing, "fast", 2.0)
    timing.stage_part_c("compare", {})
    speed = json.loads((timing.OUTPUT / "part-c.json").read_text())["speed"]["bioasq"]
    assert speed["exact_vectors_per_second"] == pytest.approx(0.5)
    assert speed["fast_vectors_per_second"] == pytest.approx(2.0)
    assert speed["speed_gain"] == pytest.approx(4.0)


def test_compare_refuses_when_a_speed_file_is_missing(timing):
    _write_vectors(timing, "exact")
    _write_vectors(timing, "fast")
    _write_speed(timing, "exact", 8.0)
    with pytest.raises(SystemExit, match="part-c-fast-speed.json"):
        timing.stage_part_c("compare", {})
    assert not (timing.OUTPUT / "part-c.json").exists()


def test_financebench_tokens_per_page_divides_by_the_slice_pages():
    """Review fix: tokens per page is slice tokens / slice pages, not / chunks."""
    from timing_lib import estimates

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
    from timing_lib import estimates

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
