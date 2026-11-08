"""Wiring tests for the five harness gaps (Experiment 48 review, 2026-11-08).

Run with: uv run --no-sync pytest test_harness_rows.py -q

Every test uses fakes and tmp folders. No test starts a server, a router or an
ingest, and none writes to ``output/``.
"""

from __future__ import annotations

import io
import json
import sys
import types
import urllib.request
from pathlib import Path

import pytest
import router_config as rc

EXP_DIR = Path(__file__).resolve().parent
PLAN = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
BASELINE = "Qwen3-Embedding-4B-Q8_0.gguf"


class FakeEngine:
    def __init__(self, answers=None):
        self.answers = list(answers or [])

    def search(self, query, **kwargs):
        return [{"chunk_id": "c1", "source": "a.pdf"}]

    async def answer(self, text, **kwargs):
        return self.answers.pop(0)

    def close(self):
        pass


# --- gap 4: a collection name on search, arms and determinism rows ---------------


def test_a_search_row_carries_its_collection(part_a):
    row = part_a._one_search(  # noqa: SLF001
        FakeEngine(), "q", "dense", {}, "sweep43_06b", expected=""
    )
    assert row["collection"] == "sweep43_06b"


def test_a_failed_search_row_still_carries_its_collection(part_a):
    class Broken(FakeEngine):
        def search(self, query, **kwargs):
            raise RuntimeError("boom")

    row = part_a._one_search(Broken(), "q", "dense", {}, "sweep43", expected="")  # noqa: SLF001
    assert row["error"] and row["collection"] == "sweep43"


# --- gap 3: answer rows keep verification fields; G1 cannot pass quietly ---------


def _run_answers(part_a, monkeypatch, answers, verify):
    monkeypatch.setattr(part_a, "engine_factory", lambda *a: lambda: FakeEngine(answers))
    questions = [{"query": f"q{i}"} for i in range(len(answers))]
    return part_a.run_answers(part_a.engine_factory, questions, [], None, verify=verify)


def test_a_verified_answer_row_keeps_status_and_verified(part_a, monkeypatch):
    ok = {"status": "ok", "verified": True, "answer": "a", "citations": [1]}
    row = _run_answers(part_a, monkeypatch, [ok], verify=True)[0]
    assert (row["status"], row["verified"], row["error"]) == ("ok", True, "")


def test_a_skipped_verification_makes_an_error_row(part_a, monkeypatch):
    skipped = {"status": "ok", "verification_skipped": "judge down", "answer": "a"}
    row = _run_answers(part_a, monkeypatch, [skipped], verify=True)[0]
    assert "judge down" in row["error"]
    assert row["verification_skipped"] == "judge down"


def test_a_missing_verification_makes_an_error_row(part_a, monkeypatch):
    row = _run_answers(part_a, monkeypatch, [{"status": "ok", "answer": "a"}], verify=True)[0]
    assert row["error"]


def test_a_plain_run_row_is_not_an_error(part_a, monkeypatch):
    row = _run_answers(part_a, monkeypatch, [{"status": "ok", "answer": "a"}], verify=False)[0]
    assert row["error"] == ""


# --- gap 1: determinism mode runs the same preflight -----------------------------


def test_determinism_mode_runs_preflight_with_the_baseline_model_only(
    part_a, monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(part_a, "preflight", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(rc, "configure", lambda *a, **k: Path("unused"))
    monkeypatch.setattr(part_a, "load_questions", lambda: [])
    monkeypatch.setattr(part_a, "load_financebench", lambda: [])
    monkeypatch.setattr(part_a, "read_jsonl", lambda name: [])
    monkeypatch.setattr(part_a, "engine_factory", lambda *a: lambda: FakeEngine())
    monkeypatch.setattr(sys, "argv", ["run_part_a.py", "--mode", "determinism"])
    (tmp_path / "plan.json").write_text((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(part_a, "EXP_DIR", tmp_path)
    part_a.main()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert kwargs.get("load") == [BASELINE]
    assert kwargs.get("models") == [BASELINE]


# --- gap 2: run_timing writes a /props snapshot after its live check -------------


def test_timing_live_check_appends_a_props_snapshot(timing, monkeypatch):
    order = []
    fake_found = types.SimpleNamespace(as_run_record=lambda: {"ok": True})
    monkeypatch.setattr(timing, "verify_llamacpp_runtime", lambda *a, **k: fake_found)
    monkeypatch.setattr(timing, "record_run_start", lambda *a, **k: order.append("record"))
    monkeypatch.setattr(timing, "preset_has_parallel", lambda models: None)
    settings = types.SimpleNamespace(llamacpp_router_url="http://127.0.0.1:18080/v1")
    monkeypatch.setattr("omrs.compose.get_settings", lambda: settings)
    urls = []

    def fake_urlopen(url, timeout):
        urls.append(url)
        order.append("props")
        return io.BytesIO(b'{"n_ctx": 1}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sys, "argv", ["run_timing.py", "--model", "4b"])
    timing.check_runtime(PLAN, [BASELINE])
    lines = (timing.OUTPUT / "server-props.jsonl").read_text().splitlines()
    assert len(lines) == 1
    snap = json.loads(lines[0])
    assert list(snap["props"]) == [rc.model_name(rc.plan_model(PLAN, BASELINE))]
    assert snap["argv"] == ["run_timing.py", "--model", "4b"]
    assert urls[0].startswith("http://127.0.0.1:18080/props?model=")
    assert order == ["record", "props"]


# --- gap 5: a resumed slice with chunks already in its collection is refused -----


def _stage_model(
    timing, monkeypatch, tmp_path, *, done, counts, result=None, limit=None, done_limit=None
):
    """Run ``stage_model`` with fakes; return the collections ingested into.

    *result* is what the fake ``ingest_path_async`` returns. *done_limit*, when
    given, is the ``limit`` stored in each already-done row.
    """
    ingested = []
    slices = {}
    for name in ("freshstack", "bioasq", "financebench"):
        folder = tmp_path / "slices" / name
        folder.mkdir(parents=True)
        (folder / "doc.txt").write_text("x", encoding="utf-8")
        slices[name] = folder
    (timing.OUTPUT / "timing-4b.jsonl").write_text(
        "".join(
            json.dumps({"slice": s, **({} if done_limit is None else {"limit": done_limit})}) + "\n"
            for s in done
        ),
        encoding="utf-8",
    )

    async def fake_ingest(path, collection_name):
        ingested.append(collection_name)
        return {"timings": {}} if result is None else result

    monkeypatch.setattr(timing, "check_runtime", lambda *a: None)
    monkeypatch.setattr(timing, "prepare_slices", lambda: slices)
    monkeypatch.setattr(timing, "store_texts", lambda collection: [{"id": "1", "text": "t"}])
    monkeypatch.setattr(timing, "tokenize_count", lambda texts, name: 1)
    monkeypatch.setattr(
        timing, "collection_chunk_count", lambda collection: counts.get(collection, 0)
    )
    monkeypatch.setattr(
        "omrs.compose.build_engine", lambda: types.SimpleNamespace(_effective_settings=None)
    )
    monkeypatch.setattr("omrs.compose.ensure_runtime_setup", lambda: None)
    monkeypatch.setattr("omrs.core.ingestion.ingest_path_async", fake_ingest)
    monkeypatch.setattr("omrs.core.settings.set_default_effective_settings", lambda s: None)
    monkeypatch.setattr(timing.router_config, "held", _held)
    monkeypatch.setattr(timing.router_config, "router_pids", lambda: set())
    monkeypatch.setattr(timing, "GpuMemorySampler", _FakeGpu)
    monkeypatch.setattr(timing, "RssSampler", _FakeRss)
    timing.stage_model("4b", PLAN, limit, object())
    return ingested


class _FakeRss:
    def __init__(self):
        self.stop_event = types.SimpleNamespace(set=lambda: None)
        self.peak_bytes = 0

    def start(self):
        pass

    def join(self, timeout=None):
        pass


class _FakeGpu:
    def __init__(self, **kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        return None


class _held:  # noqa: N801 - stands in for a context manager function
    def __init__(self, *args):
        pass

    def __enter__(self):
        return "name"

    def __exit__(self, *exc):
        return False


def test_a_slice_whose_collection_holds_chunks_is_refused(timing, monkeypatch, tmp_path):
    counts = {"sweep43_timing_4b_bioasq": 7}
    with pytest.raises(Exception, match="sweep43_timing_4b_bioasq"):
        _stage_model(timing, monkeypatch, tmp_path, done=[], counts=counts)


def test_a_slice_already_done_is_skipped_even_if_its_collection_holds_chunks(
    timing, monkeypatch, tmp_path
):
    counts = {"sweep43_timing_4b_bioasq": 7}
    ingested = _stage_model(
        timing, monkeypatch, tmp_path, done=["freshstack", "bioasq", "financebench"], counts=counts
    )
    assert "sweep43_timing_4b_bioasq" not in ingested


def test_empty_collections_run_every_slice(timing, monkeypatch, tmp_path):
    ingested = _stage_model(timing, monkeypatch, tmp_path, done=[], counts={})
    assert {c for c in ingested if not c.endswith("warmup")} == {
        "sweep43_timing_4b_freshstack",
        "sweep43_timing_4b_bioasq",
        "sweep43_timing_4b_financebench",
    }
