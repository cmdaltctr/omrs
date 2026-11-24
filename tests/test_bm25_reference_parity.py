"""BM25 matches the Anserini/Pyserini reference used by BEIR and FreshStack.

The reference uses k1 0.9, b 0.4 and Porter stemming. These tests pin the
tokeniser stems, the parameters of both BM25 paths, and the claim that the
internal fallback scores like ``rank_bm25.BM25Okapi``.
"""

from __future__ import annotations

import builtins
import sys
from importlib.util import find_spec
from typing import Any

import pytest

from omrs.core.retrieval import sparse
from omrs.core.retrieval.sparse import _make_bm25, _SimpleBM25Okapi, tokenize_english

#: Cases that need ``rank_bm25`` (the ``hybrid`` extra). They skip in the clean
#: base install, so the tripwire subtracts them there (``_HYBRID_EXTRA_CASES``).
requires_rank_bm25 = pytest.mark.skipif(
    find_spec("rank_bm25") is None,
    reason="hybrid extra not installed (uv sync --extra hybrid)",
)

#: Corpus with a term in more than half of the documents, so the epsilon
#: clip of negative IDF values is part of the comparison.
CORPUS: list[list[str]] = [
    ["common", "alpha", "alpha", "beta"],
    ["common", "beta", "gamma"],
    ["common", "delta", "delta", "delta", "epsilon", "zeta", "eta"],
    ["theta", "alpha"],
]
QUERIES: list[list[str]] = [["alpha"], ["common", "delta"], ["beta", "gamma", "missing"]]


@pytest.fixture(autouse=True)
def _fresh_stem_caches() -> Any:
    sparse._get_stemmer.cache_clear()
    sparse._stem.cache_clear()
    yield
    sparse._get_stemmer.cache_clear()
    sparse._stem.cache_clear()


def test_tokenize_english_applies_porter_stems() -> None:
    assert tokenize_english("Running runners ran quickly") == ["run", "runner", "ran", "quickli"]


def test_tokenize_english_uses_the_original_porter_algorithm_as_lucene_does() -> None:
    # Lucene's PorterStemFilter (Anserini, Pyserini) runs Porter's original algorithm.
    # NLTK's default mode adds special cases ("skies" -> "sky", "dying" -> "die").
    assert tokenize_english("skies dying") == ["ski", "dy"]


def test_tokenize_english_filters_stop_words_before_stemming() -> None:
    # "this" and "were" are stop words. Their stems ("thi", "were") must not appear.
    assert tokenize_english("This indexes were running") == ["index", "run"]


def test_tokenize_english_stops_with_hybrid_extra_name_when_nltk_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "nltk.stem.porter", None)
    with pytest.raises(RuntimeError, match=r"hybrid"):
        tokenize_english("running")


def test_simple_bm25_fallback_uses_reference_parameters() -> None:
    bm25 = _SimpleBM25Okapi(CORPUS)
    assert (bm25.k1, bm25.b) == (0.9, 0.4)


def test_make_bm25_fallback_path_uses_reference_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def hide_rank_bm25(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "rank_bm25":
            raise ModuleNotFoundError("hidden", name=name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", hide_rank_bm25)
    bm25 = _make_bm25(CORPUS)
    assert isinstance(bm25, _SimpleBM25Okapi)
    assert (bm25.k1, bm25.b) == (0.9, 0.4)


def test_simple_bm25_score_matches_the_formula_at_reference_parameters() -> None:
    """One hand-computed value: tf 2, doc length 4, avgdl 4, k1 0.9, b 0.4."""
    bm25 = _SimpleBM25Okapi(
        [["alpha", "alpha", "x", "y"], ["x", "y", "z", "w"], ["p", "q", "r", "s"]]
    )
    # idf = ln((3 - 1 + 0.5) / (1 + 0.5)); doc length equals avgdl, so length norm is 1.
    expected = 0.5108256237659907 * (2 * 1.9) / (2 + 0.9)
    assert bm25.get_scores(["alpha"])[0] == pytest.approx(expected)


@requires_rank_bm25
def test_make_bm25_builds_rank_bm25_with_reference_parameters() -> None:
    from rank_bm25 import BM25Okapi

    bm25 = _make_bm25(CORPUS)
    assert isinstance(bm25, BM25Okapi)
    assert (bm25.k1, bm25.b) == (0.9, 0.4)
    assert bm25.epsilon == 0.25


@requires_rank_bm25
def test_simple_bm25_scores_match_rank_bm25_at_reference_parameters() -> None:
    from rank_bm25 import BM25Okapi

    reference = BM25Okapi(CORPUS, k1=0.9, b=0.4)
    fallback = _SimpleBM25Okapi(CORPUS)
    for query in QUERIES:
        assert fallback.get_scores(query) == pytest.approx(list(reference.get_scores(query)))


@requires_rank_bm25
def test_simple_bm25_scores_match_rank_bm25_at_other_parameters() -> None:
    from rank_bm25 import BM25Okapi

    reference = BM25Okapi(CORPUS, k1=1.2, b=0.5)
    fallback = _SimpleBM25Okapi(CORPUS, k1=1.2, b=0.5)
    for query in QUERIES:
        assert fallback.get_scores(query) == pytest.approx(list(reference.get_scores(query)))
