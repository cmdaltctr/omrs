"""Experiment 35 search stage (``search35.py``) with a stub engine on a sealed fixture index.

Rules under test: ranked lists only, no text, no gold, no metric (task 15.1a);
depth 100 (task 15.2); the resend rule for a failed search (section 12); an
un-reranked reranker-on query stops the stage (task 13.7); the fingerprint
checks and the rebuild gate (task 5.5).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import lancedb
import pytest
from tests._exp35_fixtures import FakeTokens, load, stage_ctx

datasets35 = load("datasets35")
outputs35 = load("outputs35")
search35 = load("search35")
stagekit35 = load("stagekit35")
stages35 = load("stages35")

SETUP = "e4b-c1024-roff-hoff"
RERANK = "e4b-c1024-r4b-hoff"


def _questions(n: int = 3) -> list[Any]:
    return [datasets35.Question(qid=f"q{i}", text=f"question {i}?", relevant=()) for i in range(n)]


def _row(i: int, *, reranked: bool = True) -> dict[str, Any]:
    return {
        "chunk_id": f"ch{i}",
        "text": " ".join(["word"] * (i + 1)),
        "score": 1.0 - i / 1000,
        "page_label": str(i % 7),
        "metadata": {"file_name": f"doc{i % 3}.md"},
        "source": f"/x/doc{i % 3}.md",
        "reranked": reranked,
        "timings": {"embed_seconds": 0.5},
    }


class Engine:
    """Stub engine: 100 rows per query; can fail or come back un-reranked."""

    def __init__(self, fail: dict[str, int] | None = None, unranked: set[str] = frozenset()):
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = dict(fail or {})
        self.unranked = set(unranked)

    def search(self, text: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append((text, kwargs))
        if self.fail.get(text, 0) > 0:
            self.fail[text] -= 1
            raise RuntimeError("store unavailable")
        reranked = text not in self.unranked
        rows = [_row(i, reranked=reranked) for i in range(100)]
        if not reranked:
            rows[0]["rerank_reason"] = "llama.cpp rerank failed: HTTP 500"
        return rows


def _ctx(tmp_path: Path, engine: Engine, setup: str = SETUP, **kw: Any) -> Any:
    return stage_ctx(
        tmp_path, "search", setup, kind="search", questions=_questions(), engine=engine, **kw
    )


def _run(ctx: Any) -> int:
    return asyncio.run(search35.search_stage(ctx))


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_the_search_stage_saves_100_ranked_stored_chunks_without_text(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine)
    assert _run(ctx) == 0
    rows = _lines(ctx.run_dir / "search.jsonl")
    assert [r["qid"] for r in rows] == ["q0", "q1", "q2"]
    first = rows[0]
    assert set(first) == {"qid", "chunks", "seconds", "timings"}
    assert len(first["chunks"]) == 100
    assert first["chunks"][3] == {
        "chunk_id": "ch3",
        "score": _row(3)["score"],
        "stem": "doc0",
        "page_label": "3",
        "tokens": FakeTokens.count(_row(3)["text"]),
    }
    assert [c["chunk_id"] for c in first["chunks"]] == [f"ch{i}" for i in range(100)]
    assert "word" not in (ctx.run_dir / "search.jsonl").read_text(encoding="utf-8")
    for _, kwargs in engine.calls:
        assert kwargs["top_k"] == 100 and kwargs["fetch_k"] == 100
        assert kwargs["unassembled"] is True and kwargs["rerank"] is False


def test_the_summary_and_marker_hold_counts_and_timings_never_a_metric(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, Engine())
    assert _run(ctx) == 0
    summary = json.loads((ctx.run_dir / "search-summary.json").read_text(encoding="utf-8"))
    assert set(summary) == {
        "questions",
        "rows",
        "chunks",
        "seconds",
        "resent_calls",
        "closed_missing",
    }
    marker = json.loads((ctx.run_dir / ".done-search.json").read_text(encoding="utf-8"))
    assert marker["checks"]["table_version_unchanged"] is True
    text = json.dumps(marker) + json.dumps(summary)
    for metric in ("ndcg", "recall", "mrr", "hit"):
        assert metric not in text


def test_a_failed_search_saves_no_row_and_is_resent_on_resume(tmp_path: Path) -> None:
    engine = Engine(fail={"question 1?": 1})
    with pytest.raises(stages35.StageIncomplete):
        _run(_ctx(tmp_path, engine))
    ctx = _ctx(tmp_path, engine)
    assert [r["qid"] for r in _lines(ctx.run_dir / "search.jsonl")] == ["q0"]
    assert not (ctx.run_dir / ".done-search.json").exists()
    engine.calls.clear()
    assert _run(_ctx(tmp_path, engine, resume=True)) == 0
    assert [t for t, _ in engine.calls] == ["question 1?"]
    assert [r["qid"] for r in _lines(ctx.run_dir / "search.jsonl")] == ["q0", "q1", "q2"]
    marker = json.loads((ctx.run_dir / ".done-search.json").read_text(encoding="utf-8"))
    assert marker["resent_calls"] == 1


def test_a_third_search_error_closes_the_question_as_missing(tmp_path: Path) -> None:
    engine = Engine(fail={"question 1?": 3})
    with pytest.raises(stages35.StageIncomplete):
        _run(_ctx(tmp_path, engine))
    with pytest.raises(stages35.StageIncomplete):
        _run(_ctx(tmp_path, engine, resume=True))
    assert _run(_ctx(tmp_path, engine, resume=True)) == 0
    rows = _lines(_ctx(tmp_path, engine, resume=True).run_dir / "search.jsonl")
    assert rows[1] == {"qid": "q1", "missing": True, "error": "RuntimeError: store unavailable"}


def test_an_unreranked_query_stops_the_stage_and_is_resent(tmp_path: Path) -> None:
    engine = Engine(unranked={"question 1?"})
    with pytest.raises(stagekit35.RerankFailed, match="question 1.*HTTP 500"):
        _run(_ctx(tmp_path, engine, RERANK))
    ctx = _ctx(tmp_path, engine, RERANK, resume=True)
    assert [r["qid"] for r in _lines(ctx.run_dir / "search.jsonl")] == ["q0"]
    assert not (ctx.run_dir / ".done-search.json").exists()
    engine.unranked.clear()
    engine.calls.clear()
    assert _run(ctx) == 0
    assert [t for t, _ in engine.calls] == ["question 1?", "question 2?"]
    assert all(kw["rerank"] is True for _, kw in engine.calls)


# --- fingerprint checks and the rebuild gate (task 5.5) ----------------------------------


def test_a_missing_fingerprint_refuses_before_the_first_query(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine)
    ctx.layout.fingerprint(ctx.dataset, ctx.index).unlink()
    with pytest.raises(stagekit35.FingerprintError, match="index-fingerprint.json is missing"):
        _run(ctx)
    assert engine.calls == []


def test_a_hybrid_setup_with_another_sparse_backend_is_refused_and_names_both(
    tmp_path: Path,
) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine, "e4b-c1024-roff-hon")
    ctx.settings.retrieval.hybrid_sparse_backend = "native"
    with pytest.raises(stagekit35.FingerprintError, match="'native'.*'bm25'"):
        _run(ctx)
    assert engine.calls == []


def test_a_table_version_change_during_the_stage_fails_with_no_marker(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine)
    table = lancedb.connect(str(ctx.layout.store(ctx.index))).open_table(ctx.collection)

    def search(text: str, **kwargs: Any) -> list[dict[str, Any]]:
        table.add([{"id": f"x{len(engine.calls)}", "text": "new", "vector": [0.0, 0.0]}])
        return Engine.search(engine, text, **kwargs)

    engine.search = search  # type: ignore[method-assign]
    with pytest.raises(stagekit35.FingerprintError, match="changed during the stage"):
        _run(ctx)
    assert not (ctx.run_dir / ".done-search.json").exists()


def test_the_shared_output_folder_needs_a_passing_rebuild_check(tmp_path: Path) -> None:
    engine = Engine()
    ctx = _ctx(tmp_path, engine)
    (ctx.layout.root / "bioasq" / "rebuild.json").write_text('{"ok": false}', encoding="utf-8")
    with pytest.raises(stagekit35.FingerprintError, match="bioasq: no passing rebuild check"):
        _run(ctx)
    assert engine.calls == []


def test_index_from_with_another_output_folder_is_not_blocked(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, Engine())
    (ctx.layout.root / "bioasq" / "rebuild.json").unlink()
    ctx.layout = outputs35.Layout(tmp_path / "elsewhere", index_root=ctx.layout.root)
    ctx.trace._path = ctx.run_dir / "traces.jsonl"
    assert _run(ctx) == 0
    assert (tmp_path / "elsewhere" / "bioasq" / "search" / SETUP / "run1" / "search.jsonl").exists()


def test_the_pinned_tokenizer_loads_once_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[tuple[str, str]] = []

    class Encoding:
        def __init__(self, text: str) -> None:
            words = text.split(" ")
            self.ids = list(range(len(words)))
            ends, at = [], 0
            for word in words:
                at += len(word)
                ends.append((at - len(word), at))
                at += 1
            self.offsets = ends

    class Tokenizer:
        def encode(self, text: str, add_special_tokens: bool = True) -> Encoding:
            assert add_special_tokens is False
            return Encoding(text)

    import omrs.integrations.tokenizer as tokenizer_module

    def fake_load(model: str, revision: str) -> Tokenizer:
        loaded.append((model, revision))
        return Tokenizer()

    monkeypatch.setattr(tokenizer_module, "load_tokenizer", fake_load)
    ctx = type("C", (), {"tokens": None})()
    tokens = stagekit35.tokens_of(ctx)
    assert stagekit35.tokens_of(ctx) is tokens
    arms = load("arms")
    assert loaded == [(arms.TOKENIZER_MODEL, arms.TOKENIZER_REVISION)]
    assert tokens.count("a bb ccc") == 3
    assert tokens.truncate("a bb ccc", 2) == "a bb"
