"""Tests for the BM25 calibration scorer (bm25_calibration35.py).

Run with: uv run --no-sync pytest test_bm25_calibration35.py -q
"""

from __future__ import annotations

import json
import math
from importlib.util import find_spec

import bm25_calibration35 as cal
import pytest

from omrs.core.retrieval import sparse


def test_ndcg_at_10_matches_a_hand_computed_value_with_linear_gain():
    rels = {"a": 2, "b": 1, "c": 1}
    ranked = ["x", "a", "c"]
    dcg = 2 / math.log2(3) + 1 / math.log2(4)
    idcg = 2 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4)
    assert cal.ndcg_at(ranked, rels) == pytest.approx(dcg / idcg)


def test_ndcg_counts_only_the_top_k():
    assert cal.ndcg_at(["x"] * 10 + ["a"], {"a": 1}) == 0.0


def test_recall_at_100_is_the_share_of_relevant_documents_found():
    ranked = ["a"] + [f"x{i}" for i in range(99)] + ["b"]
    assert cal.recall_at(ranked, {"a": 1, "b": 1}) == pytest.approx(0.5)


def test_paired_stats_reports_the_mean_difference_and_a_tiny_p_for_a_clear_gain():
    a = [0.1] * 40
    b = [0.3] * 40
    out = cal.paired_stats(a, b)
    assert out["mean_diff"] == pytest.approx(0.2)
    assert out["wins"] == 40 and out["losses"] == 0
    assert out["p"] < 0.001
    assert out["ci_low"] == pytest.approx(0.2) and out["ci_high"] == pytest.approx(0.2)


def test_paired_stats_gives_a_large_p_when_nothing_changes():
    a = [0.1, 0.2, 0.3, 0.4] * 10
    assert cal.paired_stats(a, list(a))["p"] == pytest.approx(1.0)


def test_holm_multiplies_the_smallest_p_by_the_family_size_and_stays_monotone():
    out = cal.holm({"x": 0.01, "y": 0.04, "z": 0.03})
    assert out["x"] == pytest.approx(0.03)
    assert out["z"] == pytest.approx(0.06)
    assert out["y"] == pytest.approx(0.06)


def test_stem_config_is_the_shipped_omrs_bm25_and_reference_is_pyserini():
    by_name = {c.name: c for c in cal.CONFIGS}
    stem, ref, old = by_name["stem"], by_name["reference"], by_name["old"]
    assert (stem.k1, stem.b) == (sparse.BM25_K1, sparse.BM25_B) == (1.5, 0.75)
    assert stem.tokens is sparse.tokenize_english is ref.tokens
    assert (ref.k1, ref.b) == (0.9, 0.4)
    assert (old.k1, old.b) == (1.5, 0.75)
    assert old.tokens("The Running indexes") == ["running", "indexes"]


@pytest.mark.skipif(
    find_spec("rank_bm25") is None,
    reason="hybrid extra not installed (uv sync --extra hybrid)",
)
def test_a_small_beir_folder_runs_end_to_end(tmp_path):
    beir = tmp_path / "beir"
    (beir / "scifact").mkdir(parents=True)
    (beir / "scifact-qrels").mkdir()
    docs = [
        {"_id": "d2", "title": "Running shoes", "text": "shoes for runners"},
        {"_id": "d1", "title": "Cooking", "text": "pasta and sauce"},
        {"_id": "d3", "title": "Gardens", "text": "roses and tulips"},
        {"_id": "d4", "title": "Boats", "text": "sails and oars"},
    ]  # four documents: with two, rank_bm25 gives a one-document word an IDF of 0
    (beir / "scifact" / "corpus.jsonl").write_text("\n".join(json.dumps(d) for d in docs))
    (beir / "scifact" / "queries.jsonl").write_text(json.dumps({"_id": "q1", "text": "run"}))
    (beir / "scifact-qrels" / "test.tsv").write_text("query-id\tcorpus-id\tscore\nq1\td2\t1\n")
    out = tmp_path / "out"
    assert cal.main(["--beir-dir", str(beir), "--out", str(out), "--datasets", "scifact"]) == 0
    summary = json.loads((out / "bm25-calibration.json").read_text())
    means = summary["means"]["scifact"]
    # Only stemming lets "run" match "Running" and "runners". Without it every score is 0,
    # and OMRS returns no document with a score of 0 (sparse.py keeps score > 0 only).
    assert means["old"] == {"ndcg10": 0.0, "recall100": 0.0}
    assert means["reference"]["ndcg10"] == pytest.approx(1.0)


def test_every_parquet_shard_of_a_part_is_read(tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    import pyarrow as pa

    folder = tmp_path / "corpus"
    folder.mkdir()
    pq.write_table(pa.Table.from_pylist([{"_id": "d1"}]), folder / "corpus-00000-of-00002.parquet")
    pq.write_table(pa.Table.from_pylist([{"_id": "d2"}]), folder / "corpus-00001-of-00002.parquet")
    assert [r["_id"] for r in cal._rows(tmp_path, "corpus")] == ["d1", "d2"]
