"""Tests of the LLM-AggreFact runner with stub judges: no router, no network."""

from __future__ import annotations

import json
import signal

import aggrefact_lib as lib
import pytest
import run_aggrefact as run
from aggrefact_testkit import DATASETS, ROW_MARK, StubJudge, isolate_env, make_split, truthful


@pytest.fixture
def split(tmp_path, monkeypatch):
    return make_split(tmp_path, monkeypatch)


@pytest.fixture
def isolated_env(monkeypatch):
    isolate_env(monkeypatch)


def _maker(decide=truthful, built=None):
    def make(strategy, out_dir, gguf_file):
        judge = StubJudge(strategy, decide)
        if built is not None:
            built.append(judge)
        return judge

    return make


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _go(split, out, *extra, make=None):
    argv = ["--strategy", "clef_flash", "--parquet", str(split), "--out-dir", str(out), *extra]
    return run.main(argv, make_judge=make or _maker())


def test_model_ids_match_the_brief():
    assert run.model_id("clef_flash") == "ggml-org/Clef-Flash-GGUF:Q8_0"
    assert run.model_id("granite_guardian") == "ibm-granite/granite-guardian-3.3-8b-GGUF:Q8_0"


def test_scratch_settings_reach_the_production_judge_config(tmp_path, isolated_env):
    import os

    gguf = tmp_path / "gguf"
    gguf.mkdir()
    (gguf / "Clef-Flash-Q8_0.gguf").write_bytes(b"not a model")
    os.environ["SWEEP_GGUF_DIR"] = str(gguf)
    model, settings, path = run.configure("clef_flash", tmp_path / "out", None, hash_missing=True)
    assert path == tmp_path / "out" / "config" / "omrs.jsonc"
    assert settings.answer.verify_claims is True
    assert settings.answer.verify_judge == "clef_flash"
    assert settings.answer.verify_model == "ggml-org/Clef-Flash-GGUF:Q8_0"
    assert model["sha256"] == run.JUDGES["clef_flash"]["sha256"]  # pinned: not re-hashed
    summary = run.settings_summary("clef_flash", settings, path)
    assert summary["strategy_ready"] == "ready"
    assert summary["judge_role_problems"] == []
    assert summary["entries"]["ggml-org/Clef-Flash-GGUF:Q8_0"]["preset"]["parallel"] == 1


def test_unpinned_model_is_hashed_before_the_router(tmp_path, isolated_env):
    import os

    gguf = tmp_path / "gguf"
    gguf.mkdir()
    (gguf / "granite-guardian-3.3-8b-Q8_0.gguf").write_bytes(b"granite")
    os.environ["SWEEP_GGUF_DIR"] = str(gguf)
    model, settings, _ = run.configure("granite_guardian", tmp_path / "out", None,
                                       hash_missing=True)  # fmt: skip
    expected = lib.file_sha256(gguf / "granite-guardian-3.3-8b-Q8_0.gguf")
    assert model["sha256"] == expected
    assert settings.llamacpp_models["judge-granite-guardian"].sha256 == expected


def test_dry_run_starts_nothing(split, tmp_path, isolated_env, capsys):
    import os

    gguf = tmp_path / "gguf"
    gguf.mkdir()
    (gguf / "Clef-Flash-Q8_0.gguf").write_bytes(b"x")
    os.environ["SWEEP_GGUF_DIR"] = str(gguf)

    def refuse(*_args):
        raise AssertionError("the dry run built a judge")

    assert _go(split, tmp_path / "out", "--dry-run", make=refuse) == 0
    out = capsys.readouterr().out
    assert "no router started" in out and '"verify_judge": "clef_flash"' in out
    assert not (tmp_path / "out" / "aggrefact-clef_flash.jsonl").exists()
    assert ROW_MARK not in out


def test_full_run_writes_header_facts_and_rows(split, tmp_path, capsys):
    out = tmp_path / "out"
    assert _go(split, out) == 0
    lines = _lines(out / "aggrefact-clef_flash.jsonl")
    header, facts, rows = lines[0], lines[2], [x for x in lines if x["kind"] == "row"]
    assert header["kind"] == "header" and header["strategy"] == "clef_flash"
    assert header["judge_version"] == "clef-flash-claim/1"
    assert header["model"] == "ggml-org/Clef-Flash-GGUF:Q8_0"
    assert header["parquet_sha256"] == lib.file_sha256(split)
    assert header["seed"] == 20261109 and header["limit"] is None
    assert facts["kind"] == "facts" and facts["sha256"] == "ab" * 32
    assert len(rows) == 30 and {r["idx"] for r in rows} == set(range(30))
    assert set(rows[0]) == {"kind", "idx", "dataset", "label", "verdict", "p_yes", "seconds",
                            "error"}  # fmt: skip
    assert [r["idx"] for r in rows] == lib.row_order(30)  # the fixed order


def test_never_prints_or_stores_row_text(split, tmp_path, capsys):
    out = tmp_path / "out"
    assert _go(split, out) == 0
    captured = capsys.readouterr()
    assert ROW_MARK not in captured.out + captured.err
    assert ROW_MARK not in (out / "aggrefact-clef_flash.jsonl").read_text(encoding="utf-8")


def test_limit_order_is_stable_across_runs_and_spans_datasets(split, tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    assert _go(split, first, "--limit", "9") == 0
    assert _go(split, second, "--limit", "9") == 0
    rows_a = [x for x in _lines(first / "aggrefact-clef_flash.jsonl") if x["kind"] == "row"]
    rows_b = [x for x in _lines(second / "aggrefact-clef_flash.jsonl") if x["kind"] == "row"]
    assert [r["idx"] for r in rows_a] == [r["idx"] for r in rows_b] == lib.row_order(30, limit=9)
    assert {r["dataset"] for r in rows_a} == set(DATASETS)


def test_existing_file_needs_resume(split, tmp_path, capsys):
    out = tmp_path / "out"
    assert _go(split, out, "--limit", "4") == 0
    assert _go(split, out, "--limit", "4") == 2
    assert "pass --resume" in capsys.readouterr().out


def test_resume_with_matching_header_skips_done_rows(split, tmp_path):
    out = tmp_path / "out"
    (out).mkdir()
    (out / "RUNSTOP").write_text("", encoding="utf-8")
    first = []
    assert _go(split, out, make=_maker(built=first)) == 0  # stops before any row
    (out / "RUNSTOP").unlink()

    def stop_after_five(idx):
        if len(first[-1].calls) == 5:
            (out / "RUNSTOP").write_text("", encoding="utf-8")
        return truthful(idx)

    assert _go(split, out, "--resume", make=_maker(stop_after_five, first)) == 0
    (out / "RUNSTOP").unlink()
    assert _go(split, out, "--resume", make=_maker(built=first)) == 0
    lines = _lines(out / "aggrefact-clef_flash.jsonl")
    rows = [x for x in lines if x["kind"] == "row"]
    assert [x["kind"] for x in lines].count("header") == 1
    assert [x["kind"] for x in lines].count("facts") == 1
    assert sorted(r["idx"] for r in rows) == list(range(30))  # no repeat, none missing
    assert len(first[1].calls) == 5 and len(first[2].calls) == 25


@pytest.mark.parametrize(
    ("key", "value"), [("limit", 7), ("parquet_sha256", "0" * 64), ("judge_version", "old/0")]
)
def test_resume_refuses_a_different_header(split, tmp_path, capsys, key, value):
    out = tmp_path / "out"
    assert _go(split, out) == 0
    path = out / "aggrefact-clef_flash.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header[key] = value
    path.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n", encoding="utf-8")
    called = []
    assert _go(split, out, "--resume", make=_maker(built=called)) == 2
    assert f"header of {path.name} differs ({key}:" in capsys.readouterr().out
    assert called == []  # refused before any judge or router


def test_resume_drops_a_half_written_last_line(split, tmp_path):
    out = tmp_path / "out"
    assert _go(split, out, "--limit", "3") == 0
    path = out / "aggrefact-clef_flash.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"kind": "row", "idx', encoding="utf-8")
    assert _go(split, out, "--limit", "3", "--resume") == 0
    assert len([x for x in _lines(path) if x["kind"] == "row"]) == 3


def test_runstop_stops_between_rows(split, tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()

    def stop_after_three(idx):
        if len(built[0].calls) == 3:
            (out / "RUNSTOP").write_text("", encoding="utf-8")
        return truthful(idx)

    built = []
    assert _go(split, out, make=_maker(stop_after_three, built)) == 0
    rows = [x for x in _lines(out / "aggrefact-clef_flash.jsonl") if x["kind"] == "row"]
    assert len(rows) == 3
    assert "RUNSTOP found; stopped after 3 rows" in capsys.readouterr().out


def test_sigterm_finishes_the_current_row(split, tmp_path, capsys):
    out = tmp_path / "out"
    built = []

    def term_on_second(idx):
        if len(built[0].calls) == 2:
            signal.raise_signal(signal.SIGTERM)
        return truthful(idx)

    before = signal.getsignal(signal.SIGTERM)
    assert _go(split, out, make=_maker(term_on_second, built)) == 0
    rows = [x for x in _lines(out / "aggrefact-clef_flash.jsonl") if x["kind"] == "row"]
    assert len(rows) == 2 and rows[1]["verdict"] is not None  # the second row was written
    assert "signal received; stopped after 2 rows" in capsys.readouterr().out
    assert signal.getsignal(signal.SIGTERM) == before  # the old handler is back


def test_failed_rows_are_recorded_and_the_run_goes_on(split, tmp_path):
    out = tmp_path / "out"

    def flaky(idx):
        if idx % 3 == 0:
            return "unparseable", "unreachable"
        if idx % 3 == 1:
            raise RuntimeError(f"{ROW_MARK} reply text")
        return truthful(idx)

    assert _go(split, out, make=_maker(flaky)) == 0
    path = out / "aggrefact-clef_flash.jsonl"
    rows = {x["idx"]: x for x in _lines(path) if x["kind"] == "row"}
    assert len(rows) == 30
    assert rows[0]["error"] == "unreachable"
    assert rows[1]["error"] == "exception-RuntimeError" and rows[1]["verdict"] is None
    assert rows[2]["error"] is None
    assert ROW_MARK not in path.read_text(encoding="utf-8")


def test_more_than_twenty_consecutive_failures_stop_the_run(split, tmp_path, capsys):
    out = tmp_path / "out"
    assert _go(split, out, make=_maker(lambda idx: ("unparseable", "unreachable"))) == 3
    rows = [x for x in _lines(out / "aggrefact-clef_flash.jsonl") if x["kind"] == "row"]
    assert len(rows) == 21
    assert "21 rows in a row failed (last reason: unreachable)" in capsys.readouterr().out


def test_twenty_consecutive_failures_do_not_stop_the_run(split, tmp_path):
    out = tmp_path / "out"
    order = lib.row_order(30)

    def twenty_then_ok(idx):
        return ("unparseable", "unreachable") if order.index(idx) < 20 else truthful(idx)

    assert _go(split, out, make=_maker(twenty_then_ok)) == 0


def test_unavailable_judge_stops_with_its_reason(split, tmp_path, capsys):
    from omrs.core.answer.judges.base import JudgeUnavailable

    def unavailable(idx):
        raise JudgeUnavailable("claim judge clef_flash cannot run: model-not-listed")

    assert _go(split, tmp_path / "out", make=_maker(unavailable)) == run.EXIT_UNAVAILABLE
    assert "model-not-listed" in capsys.readouterr().out


def test_timing_line_printed_once(split, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(run, "TIMING_ROWS", 5)
    assert _go(split, tmp_path / "out") == 0
    out = capsys.readouterr().out
    assert out.count("[timing] first 5 rows:") == 1
    assert "full set of 30 rows" in out and "remaining 25 rows" in out


def test_refuses_an_unpinned_parquet(split, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lib, "PARQUET_SHA256", "f" * 64)
    assert _go(split, tmp_path / "out") == 2
    assert "not the pinned TEST split" in capsys.readouterr().out
