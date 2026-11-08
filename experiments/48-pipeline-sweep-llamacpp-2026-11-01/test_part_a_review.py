"""Part A tests for the PR 195 review fixes (CodeRabbit, 2026-11-08).

Run with: uv run --no-sync pytest test_part_a_review.py -q

Fakes and tmp folders only: no server, no router, no write to ``output/``.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
import router_config as rc
from sweep_lib import LimitMismatchError
from test_harness_rows import FakeEngine

EXP_DIR = Path(__file__).resolve().parent
BASELINE = "Qwen3-Embedding-4B-Q8_0.gguf"


def _tree(tmp_path):
    """A tmp experiment folder: two frozen files, two frozen PDFs, and strays."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("a", encoding="utf-8")
    (corpus / ".DS_Store").write_text("junk", encoding="utf-8")
    pdfs = tmp_path / "output" / "financebench" / "pdfs"
    pdfs.mkdir(parents=True)
    (pdfs / "B.pdf").write_text("b", encoding="utf-8")
    (pdfs / "STALE.pdf").write_text("old", encoding="utf-8")
    plan = {
        "frozen": [
            {"name": "corpus/a.md", "sha256": "x"},
            {"name": "financebench/B.pdf", "sha256": "y"},
            {"name": "ground-truth.json", "sha256": "z"},
        ]
    }
    return plan


# --- comments 3 and 0: ingest only the frozen documents ---------------------------


def test_the_ingest_list_holds_only_frozen_documents(part_a, monkeypatch, tmp_path):
    plan = _tree(tmp_path)
    monkeypatch.setattr(part_a, "EXP_DIR", tmp_path)
    found = part_a.fixed_set_documents(plan)
    assert [p.name for p in found] == ["a.md", "B.pdf"]


def _ingest_with_fakes(part_a, monkeypatch, tmp_path, result, limit=None):
    plan = _tree(tmp_path)
    monkeypatch.setattr(part_a, "EXP_DIR", tmp_path)
    seen = []

    async def fake_ingest(path, collection_name):
        seen.append(Path(path).name)
        return result

    engine = types.SimpleNamespace(_effective_settings=None, close=lambda: None)
    monkeypatch.setattr("omrs.compose.ensure_runtime_setup", lambda: None)
    monkeypatch.setattr("omrs.core.ingestion.ingest_path_async", fake_ingest)
    monkeypatch.setattr("omrs.core.settings.set_default_effective_settings", lambda s: None)
    rows = part_a.ingest_documents(lambda: engine, limit, plan=plan)
    return seen, rows


def test_ingest_documents_sends_only_frozen_documents(part_a, monkeypatch, tmp_path):
    seen, _ = _ingest_with_fakes(part_a, monkeypatch, tmp_path, {"status": "ok"})
    assert seen == ["a.md", "B.pdf"]


# --- comment 9 (Part A side): a returned ingest error is an error row -------------


def test_a_returned_ingest_error_is_recorded_as_a_row_error(part_a, monkeypatch, tmp_path):
    result = {"status": "error", "message": "All 1 file(s) failed to index."}
    _, rows = _ingest_with_fakes(part_a, monkeypatch, tmp_path, result)
    assert all("All 1 file(s) failed" in row["error"] for row in rows)


def test_a_clean_ingest_row_has_no_error(part_a, monkeypatch, tmp_path):
    _, rows = _ingest_with_fakes(part_a, monkeypatch, tmp_path, {"status": "ok"})
    assert [row["error"] for row in rows] == ["", ""]


# --- comment 2: a smoke run's markers cannot complete a full run ------------------


def test_a_marker_from_a_limited_run_is_refused_on_a_full_resume(part_a):
    part_a.OUTPUT.mkdir()
    part_a.mark_done("ingest", {"files": 1}, limit=1)
    with pytest.raises(LimitMismatchError, match="--limit 1"):
        part_a.stage_done("ingest", None)


def test_a_marker_from_the_same_limit_counts_as_done(part_a):
    part_a.OUTPUT.mkdir()
    part_a.mark_done("ingest", {"files": 1}, limit=1)
    assert part_a.stage_done("ingest", 1) is True


def test_a_marker_from_a_full_run_counts_as_done_for_a_full_run(part_a):
    part_a.OUTPUT.mkdir()
    part_a.mark_done("ingest", {"files": 11}, limit=None)
    assert part_a.stage_done("ingest", None) is True


def test_a_marker_written_before_the_limit_field_counts_as_a_full_run(part_a):
    part_a.OUTPUT.mkdir()
    (part_a.OUTPUT / ".done-ingest.json").write_text('{"files": 11}', encoding="utf-8")
    assert part_a.stage_done("ingest", None) is True


def test_no_marker_means_not_done(part_a):
    part_a.OUTPUT.mkdir()
    assert part_a.stage_done("ingest", 1) is False


# --- comment 6: a determinism pass needs two good searches ------------------------


def _determinism(part_a, monkeypatch, tmp_path, baseline_rows, search):
    class Engine(FakeEngine):
        def search(self, query, **kwargs):
            return search(query)

    monkeypatch.setattr(part_a, "preflight", lambda *a, **k: None)
    monkeypatch.setattr(rc, "configure", lambda *a, **k: Path("unused"))
    monkeypatch.setattr(part_a, "load_questions", lambda: [{"query": "q1"}])
    monkeypatch.setattr(part_a, "load_financebench", lambda: [])
    monkeypatch.setattr(part_a, "read_jsonl", lambda name: baseline_rows)
    monkeypatch.setattr(part_a, "engine_factory", lambda *a: lambda: Engine())
    monkeypatch.setattr(sys, "argv", ["run_part_a.py", "--mode", "determinism"])
    (tmp_path / "plan.json").write_text((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(part_a, "EXP_DIR", tmp_path)
    part_a.OUTPUT.mkdir()
    part_a.main()
    return [json.loads(x) for x in (part_a.OUTPUT / "determinism.jsonl").read_text().splitlines()]


def _baseline(error=""):
    return [
        {"question": "q1", "mode": mode, "error": error, "results": [] if error else [{"id": "c1"}]}
        for mode in part_a_modes()
    ]


def part_a_modes():
    return ["dense", "dense_rerank", "hybrid", "hybrid_rerank"]


def test_two_failed_searches_do_not_pass_as_a_match(part_a, monkeypatch, tmp_path):
    def boom(query):
        raise RuntimeError("down")

    rows = _determinism(part_a, monkeypatch, tmp_path, _baseline(error="down"), boom)
    assert len(rows) == 4 and all("incomplete" in row for row in rows)


def test_matching_good_searches_give_no_mismatch_rows(part_a, monkeypatch, tmp_path):
    rows = _determinism(
        part_a,
        monkeypatch,
        tmp_path,
        _baseline(),
        lambda q: [{"chunk_id": "c1", "source": "a.pdf"}],
    )
    assert rows == []
