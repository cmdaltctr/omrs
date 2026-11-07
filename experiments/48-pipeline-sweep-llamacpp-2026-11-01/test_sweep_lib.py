"""Tests for the pure parts of the pipeline-sweep runner (change tasks 3.1, 4.0, 4.1).

Run with: uv run --no-sync pytest test_sweep_lib.py -q
"""

from __future__ import annotations

import pytest
from sweep_lib import (
    ChangedInputError,
    ChunkingGuardError,
    chunking_guard,
    compare_rankings,
    compare_vectors,
    convert_evidence_page,
    extrapolate,
    preset_has_parallel,
    select_financebench,
    verify_input_hashes,
)

# --- input-hash check (task 3.1) -------------------------------------------


def test_hash_check_stops_on_changed_file_and_names_both_hashes(tmp_path):
    target = tmp_path / "doc.pdf"
    target.write_bytes(b"new bytes")
    recorded = {"doc.pdf": "a" * 64}
    with pytest.raises(ChangedInputError) as exc:
        verify_input_hashes(tmp_path, recorded)
    message = str(exc.value)
    assert "doc.pdf" in message
    assert "a" * 64 in message  # recorded hash named
    import hashlib

    assert hashlib.sha256(b"new bytes").hexdigest() in message  # found hash named


def test_hash_check_passes_on_unchanged_file(tmp_path):
    import hashlib

    (tmp_path / "doc.pdf").write_bytes(b"same")
    digest = hashlib.sha256(b"same").hexdigest()
    verify_input_hashes(tmp_path, {"doc.pdf": digest})


# --- FinanceBench page conversion (tasks 2.3/3.1) --------------------------


def test_page_conversion_maps_zero_to_page_one():
    assert convert_evidence_page(0) == 1


def test_page_conversion_maps_twenty_nine_to_thirty():
    assert convert_evidence_page(29) == 30


def test_page_conversion_rejects_negative():
    with pytest.raises(ValueError):
        convert_evidence_page(-1)


# --- determinism comparison (task 3.1) -------------------------------------


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


# --- FinanceBench selection rule (D1, task 2.3) -----------------------------


def _doc(name: str, pages: int, count: int) -> dict:
    return {"doc_name": name, "pages": pages, "question_count": count}


def test_selection_ranks_by_count_then_name_and_caps_pages():
    docs = [
        _doc("BOEING_2022_10K", 120, 7),
        _doc("AMD_2022_10K", 95, 7),
        _doc("AMERICANEXPRESS_2022_10K", 100, 7),
        _doc("PEPSICO_2022_10K", 80, 5),
        _doc("HUGE_2022_10K", 400, 9),  # over the 200-page cap: skipped
        _doc("AMCOR_2023_10K", 60, 4),
        _doc("ULTABEAUTY_2023Q4_EARNINGS", 40, 4),
    ]
    chosen = select_financebench(docs, limit=5)
    assert [d["doc_name"] for d in chosen] == [
        "AMD_2022_10K",
        "AMERICANEXPRESS_2022_10K",
        "BOEING_2022_10K",
        "PEPSICO_2022_10K",
        "AMCOR_2023_10K",
    ]


# --- extrapolation (task 4.1) ----------------------------------------------


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


# --- chunking guard (task 3.1) ---------------------------------------------


class _Resolution:
    def __init__(self, tokenizer, identity, path):
        self.tokenizer = tokenizer
        self.tokenizer_identity = identity
        self.resolved_splitter = path

    @property
    def model_token_aware(self) -> bool:
        return self.tokenizer is not None and self.resolved_splitter == "model_token_aware"


def test_chunking_guard_stops_on_legacy_fallback_and_names_tokenizer():
    identity = {"model": "Qwen/Qwen3-Embedding-4B", "revision": "5cf2132a"}
    legacy = _Resolution(None, identity, "legacy_fallback")
    with pytest.raises(ChunkingGuardError) as exc:
        chunking_guard(settings=object(), resolver=lambda _settings: legacy)
    message = str(exc.value)
    assert "legacy_fallback" in message
    assert "Qwen/Qwen3-Embedding-4B" in message
    assert "5cf2132a" in message


def test_chunking_guard_passes_on_model_token_aware():
    identity = {"model": "Qwen/Qwen3-Embedding-4B", "revision": "5cf2132a"}
    aware = _Resolution(object(), identity, "model_token_aware")
    chunking_guard(settings=object(), resolver=lambda _settings: aware)


# --- Part C comparison (task 4.0) ------------------------------------------


def test_identical_vectors_pass_with_cosine_one():
    vectors = {"c1": [1.0, 0.0], "c2": [0.0, 1.0]}
    report = compare_vectors(vectors, vectors)
    assert report["lowest_cosine"] == pytest.approx(1.0)
    assert report["median_cosine"] == pytest.approx(1.0)
    assert report["failed_chunks"] == []


def test_drifted_vector_fails_rule_and_names_chunk():
    exact = {"c1": [1.0, 0.0], "c2": [0.0, 1.0]}
    fast = {"c1": [0.99, 0.1411], "c2": [0.0, 1.0]}  # cosine just below 0.9999
    report = compare_vectors(exact, fast, threshold=0.9999)
    assert report["failed_chunks"] == ["c1"]
    assert report["lowest_cosine"] < 0.9999


def test_swapped_top10_pair_fails_and_names_question():
    left = {"q1": ["c1", "c2", "c3"], "q2": ["c4", "c5"]}
    right = {"q1": ["c2", "c1", "c3"], "q2": ["c4", "c5"]}
    changed = compare_rankings("exact-vs-fast", left, right)
    assert [row["question"] for row in changed] == ["q1"]


def test_preset_check_fails_without_parallel():
    import pytest as _pytest

    model = {"role": "embedding", "file": "x.gguf", "server_args": {"embeddings": True}}
    with _pytest.raises(ValueError) as exc:
        preset_has_parallel([model])
    assert "x.gguf" in str(exc.value)


def test_preset_check_passes_with_parallel():
    model = {"role": "embedding", "file": "x.gguf", "server_args": {"parallel": 1}}
    preset_has_parallel([model])
