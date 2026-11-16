"""Experiment 35 unit scorer, token cut and FinanceBench number match.

Tasks 15.1, 15.14 and 13.6 (pre-registration sections 3 and 6). The scorer
reads saved ranked lists of stored chunks only. All data is synthetic.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests._exp35_fixtures import load

scoring35 = load("scoring35")

LOG2 = math.log2


def _c(cid: str, stem: str = "", page: str | None = None, score: float = 0.0) -> dict:
    """One saved stored chunk of a ranked list."""
    return {"chunk_id": cid, "stem": stem, "page_label": page, "score": score}


def _gold(qid: str, units: list[str], doc_id: str | None = None):
    return scoring35.Gold(qid=qid, units=frozenset(units), doc_id=doc_id)


def _score(dataset, chunks, gold, *, unit_map=None, evidence_k=None):
    return scoring35.score_question(
        dataset,
        "e4b-c1024-roff-hoff",
        gold,
        chunks,
        evidence_k=len(chunks) if evidence_k is None else evidence_k,
        unit_map=unit_map,
    )


def _words(text: str) -> int:
    return len(text.split())


def _cut_words(text: str, n: int) -> str:
    return " ".join(text.split()[:n])


def _text(n: int) -> str:
    return " ".join(["w"] * n)


# --- 15.1: collapse to units, then cut at 10 -------------------------------------------


def test_three_chunks_of_one_document_give_one_unit_and_the_list_reaches_past_chunk_ten() -> None:
    unit_map = {f"s{i}": f"P{i}" for i in range(20)}
    unit_map |= {"a0": "PA", "a1": "PA", "a2": "PA"}
    chunks = [_c(f"c{i}", f"a{i}") for i in range(3)]
    chunks += [_c(f"d{i}", f"s{i}") for i in range(9)]  # chunks 4 to 12
    record = _score("freshstack", chunks, _gold("q", ["P8"]), unit_map=unit_map)
    assert record["units"][0] == "PA"
    assert record["units"].count("PA") == 1
    assert len(record["units"]) == 10
    assert record["units"][9] == "P8"  # chunk 12, past chunk 10
    assert record["ndcg_at_10"] == pytest.approx(1 / LOG2(11))
    assert record["mrr_at_10"] == pytest.approx(0.1)


def test_the_same_unit_order_scores_the_same_at_512_and_2048_tokens() -> None:
    small = [_c(f"{p}-{k}", str(p)) for p in range(1, 9) for k in range(4)]  # 4 chunks each
    large = [_c(f"{p}", str(p)) for p in range(1, 9)]
    gold = _gold("q", ["4", "7"])
    a = _score("bioasq", small, gold)
    b = _score("bioasq", large, gold)
    assert a["units"] == b["units"]
    for name in ("ndcg_at_10", "recall_at_10", "mrr_at_10"):
        assert a[name] == b[name]
    assert a["ndcg_at_10"] == pytest.approx(
        (1 / LOG2(5) + 1 / LOG2(8)) / (1 / LOG2(2) + 1 / LOG2(3))
    )


# --- 15.1: FinanceBench, a chunk covers its one page ------------------------------------


@pytest.mark.parametrize(("page", "hit"), [("42", True), ("41", False)])
def test_a_financebench_chunk_covers_its_one_page(page: str, hit: bool) -> None:
    gold = _gold("fb1", ["ACME_2020_10K#p42"], doc_id="ACME_2020_10K")
    record = _score("financebench", [_c("x", "ACME_2020_10K", page)], gold)
    assert record["hit_at_page"] is hit
    assert record["ndcg_at_10"] == (1.0 if hit else 0.0)
    assert record["recall_at_10"] == (1.0 if hit else 0.0)
    assert record["mrr_at_10"] == (1.0 if hit else 0.0)
    assert not [key for key in record if "any_page" in key or "first_page" in key]


@pytest.mark.parametrize(
    "row",
    [
        {"chunk_id": "m", "stem": "ACME_2020_10K", "page_labels": ["41", "42"]},
        {"chunk_id": "m", "stem": "ACME_2020_10K", "page_label": "42", "chunk_ids": ["a", "b"]},
    ],
)
def test_a_merged_row_is_refused(row: dict) -> None:
    gold = _gold("fb1", ["ACME_2020_10K#p42"])
    with pytest.raises(ValueError, match="merged"):
        _score("financebench", [row], gold)


# --- 15.1: placeholder units -------------------------------------------------------------


def test_an_unmapped_freshstack_chunk_keeps_its_rank_and_is_counted() -> None:
    chunks = [_c("c1", "orphan"), _c("c2", "s1")]
    record = _score("freshstack", chunks, _gold("q", ["P1"]), unit_map={"s1": "P1"})
    assert record["mrr_at_10"] == 0.5
    assert record["units"][0].startswith(scoring35.PLACEHOLDER)
    assert record["unmapped_chunks"] == 1


def test_a_financebench_chunk_with_no_page_label_keeps_its_rank_and_is_counted() -> None:
    chunks = [_c("c1", "ACME_2020_10K", None), _c("c2", "ACME_2020_10K", "42")]
    record = _score("financebench", chunks, _gold("fb", ["ACME_2020_10K#p42"]))
    assert record["mrr_at_10"] == 0.5
    assert record["unmapped_chunks"] == 1


def test_two_unmapped_chunks_are_two_placeholders_and_the_summary_sums_them() -> None:
    chunks = [_c("c1", "x"), _c("c2", "y"), _c("c3", "s1")]
    gold = _gold("q", ["P1"])
    record = _score("freshstack", chunks, gold, unit_map={"s1": "P1"})
    assert record["mrr_at_10"] == pytest.approx(1 / 3)
    other = _score("freshstack", [_c("c9", "z")], _gold("r", ["P1"]), unit_map={"s1": "P1"})
    summary = scoring35.summarise([record, other], expected_n=2)
    assert summary["unmapped_chunks"] == 3


# --- 15.1: fixed rules for ties and repeats ----------------------------------------------


def test_the_saved_order_is_the_rank_and_scores_are_never_used() -> None:
    chunks = [_c("b", "2", score=0.5), _c("a", "1", score=0.5), _c("z", "3", score=0.9)]
    record = _score("bioasq", chunks, _gold("q", ["1"]))
    assert record["units"] == ["2", "1", "3"]
    assert record["mrr_at_10"] == 0.5


def test_the_same_chunk_twice_keeps_its_first_rank() -> None:
    chunks = [_c("x", "orphan"), _c("x", "orphan"), _c("g", "s1")]
    record = _score("freshstack", chunks, _gold("q", ["P1"]), unit_map={"s1": "P1"})
    assert record["mrr_at_10"] == 0.5
    assert len(record["units"]) == 2


def test_a_gold_unit_listed_twice_counts_once() -> None:
    gold = scoring35.gold_table(
        "bioasq", [SimpleNamespace(qid="q", relevant=("5", "5", "6"), gold_pages={})]
    )["q"]
    record = _score("bioasq", [_c("a", "5")], gold)
    assert record["recall_at_10"] == 0.5


# --- 15.1: counts and gold refusal --------------------------------------------------------


def test_a_summary_refuses_a_question_count_that_differs_from_the_frozen_count() -> None:
    records = [_score("bioasq", [_c("a", "1")], _gold(q, ["1"])) for q in ("q1", "q2")]
    with pytest.raises(ValueError, match=r"2 .*3|3 .*2"):
        scoring35.summarise(records, expected_n=3)


def test_a_summary_refuses_a_question_scored_twice() -> None:
    records = [_score("bioasq", [_c("a", "1")], _gold("q1", ["1"])) for _ in range(2)]
    with pytest.raises(ValueError, match="q1"):
        scoring35.summarise(records, expected_n=2)


def test_the_gold_loader_refuses_a_question_with_no_gold_unit() -> None:
    questions = [
        SimpleNamespace(qid="ok", relevant=("1",), gold_pages={}),
        SimpleNamespace(qid="empty-7", relevant=(), gold_pages={}),
    ]
    with pytest.raises(ValueError, match="empty-7"):
        scoring35.gold_table("bioasq", questions)


def test_the_financebench_gold_records_the_question_document() -> None:
    question = SimpleNamespace(
        qid="fb1", relevant=("ACME_2020_10K#p3",), gold_pages={"ACME_2020_10K": ("3",)}
    )
    gold = scoring35.gold_table("financebench", [question])["fb1"]
    assert gold.doc_id == "ACME_2020_10K"
    assert gold.units == frozenset({"ACME_2020_10K#p3"})


# --- 15.1: formulas -----------------------------------------------------------------------


def test_ndcg_recall_and_mrr_follow_the_registered_formulas_with_twelve_gold_units() -> None:
    gold = _gold("q", [f"g{i}" for i in range(12)])
    order = ["g0", "n1", "g1"] + [f"n{i}" for i in range(2, 9)]
    record = _score("bioasq", [_c(u, u) for u in order], gold)
    ideal = sum(1 / LOG2(i + 1) for i in range(1, 11))  # min(12, 10) gold units
    assert record["ndcg_at_10"] == pytest.approx((1 + 1 / LOG2(4)) / ideal)
    assert record["recall_at_10"] == pytest.approx(2 / 12)
    assert record["mrr_at_10"] == 1.0


def test_a_short_unit_list_scores_missing_ranks_as_misses() -> None:
    chunks = [_c(f"c{i}", str(i % 3)) for i in range(100)]  # 3 distinct units
    record = _score("bioasq", chunks, _gold("q", ["2", "77"]))
    assert record["units"] == ["0", "1", "2"]
    assert record["ndcg_at_10"] == pytest.approx((1 / LOG2(4)) / (1 + 1 / LOG2(3)))
    assert record["recall_at_10"] == 0.5
    empty = _score("bioasq", [], _gold("q", ["2"]))
    assert (empty["ndcg_at_10"], empty["recall_at_10"], empty["mrr_at_10"]) == (0.0, 0.0, 0.0)


def test_the_summary_is_a_plain_mean_over_questions() -> None:
    records = [
        _score("financebench", [_c("x", "D1", "1")], _gold("a", ["D1#p1"], "D1")),
        _score("financebench", [_c("y", "D1", "2")], _gold("b", ["D1#p9"], "D1")),
    ]
    summary = scoring35.summarise(records, expected_n=2)
    assert summary["n"] == 2
    assert summary["ndcg_at_10"] == 0.5
    assert summary["hit_at_page"] == 0.5
    assert summary["evidence_recall_20k"] == 0.5


def test_the_record_holds_the_fields_the_statistics_read() -> None:
    record = _score("financebench", [_c("x", "D1", "1")], _gold("a", ["D1#p1"], "D1"))
    assert set(record) == {
        "dataset", "setup", "qid", "doc_id", "units", "unmapped_chunks", "evidence_chunks",
        "ndcg_at_10", "recall_at_10", "mrr_at_10", "evidence_recall_20k", "hit_at_page",
    }  # fmt: skip
    other = _score("bioasq", [_c("x", "1")], _gold("a", ["1"]))
    assert "hit_at_page" not in other
    assert other["doc_id"] is None


def test_an_unknown_dataset_is_refused() -> None:
    with pytest.raises(ValueError, match="nope"):
        _score("nope", [_c("x", "1")], _gold("a", ["1"]))


# --- 15.1 and 15.14: evidence_recall_20k on the token cut -----------------------------------


def test_evidence_recall_20k_counts_by_tokens_not_by_chunk_number() -> None:
    chunks = [dict(_c(f"c{i}", str(i)), text=_text(100)) for i in range(30)]
    cut = scoring35.evidence_by_tokens(chunks, _words, _cut_words)
    record = _score("bioasq", chunks, _gold("q", ["24"]), evidence_k=len(cut.items))
    assert len(cut.items) == 30
    assert record["evidence_recall_20k"] == 1.0
    assert record["recall_at_10"] == 0.0


def test_evidence_recall_20k_stops_after_the_crossing_chunk() -> None:
    chunks = [dict(_c(f"c{i}", str(i)), text=_text(10_000)) for i in range(5)]
    cut = scoring35.evidence_by_tokens(chunks, _words, _cut_words)
    assert len(cut.items) == 3
    gold = _gold("q", ["2", "3"])
    record = _score("bioasq", chunks, gold, evidence_k=len(cut.items))
    assert record["evidence_recall_20k"] == 0.5  # unit 2 (truncated) yes, unit 3 no
    assert record["evidence_chunks"] == 3


@pytest.mark.parametrize(("page", "covered"), [("42", 1.0), ("41", 0.0)])
def test_a_truncated_financebench_chunk_covers_its_one_page(page: str, covered: float) -> None:
    chunks = [
        dict(_c("c0", "ACME", "7"), text=_text(20_000)),
        dict(_c("c1", "ACME", page), text=_text(5_000)),
    ]
    cut = scoring35.evidence_by_tokens(chunks, _words, _cut_words)
    assert cut.items[-1].truncated
    gold = _gold("fb", ["ACME#p42"], "ACME")
    record = _score("financebench", chunks, gold, evidence_k=len(cut.items))
    assert record["evidence_recall_20k"] == covered


# --- 15.14: evidence_by_tokens ---------------------------------------------------------------


def test_the_crossing_chunk_is_truncated_at_the_limit_and_nothing_after_it_is_taken() -> None:
    chunks = [{"chunk_id": f"c{i}", "text": _text(8_000)} for i in range(4)]
    cut = scoring35.evidence_by_tokens(chunks, _words, _cut_words)
    assert [item.chunk_id for item in cut.items] == ["c0", "c1", "c2"]
    assert [item.tokens for item in cut.items] == [8_000, 8_000, 4_480]
    assert [item.truncated for item in cut.items] == [False, False, True]
    assert _words(cut.items[-1].text) == 4_480
    assert cut.cut_total == 20_480
    assert cut.truncated_chunk_id == "c2"


def test_a_list_under_the_budget_keeps_every_chunk_and_records_the_total() -> None:
    chunks = [{"chunk_id": f"c{i}", "text": _text(150)} for i in range(100)]
    cut = scoring35.evidence_by_tokens(chunks, _words, _cut_words)
    assert len(cut.items) == 100
    assert cut.cut_total == 15_000
    assert cut.truncated_chunk_id is None


def test_short_chunks_fill_the_budget_instead_of_a_fixed_count() -> None:
    chunks = [{"chunk_id": f"c{i}", "text": _text(300)} for i in range(100)]
    cut = scoring35.evidence_by_tokens(chunks, _words, _cut_words)
    assert len(cut.items) == 69  # 68 whole chunks hold 20,400; chunk 69 gives 80
    assert cut.items[-1].tokens == 80
    assert cut.cut_total == 20_480


def test_a_chunk_that_ends_on_the_limit_stops_the_cut_without_truncation() -> None:
    chunks = [{"chunk_id": f"c{i}", "text": _text(10_240)} for i in range(3)]
    cut = scoring35.evidence_by_tokens(chunks, _words, _cut_words)
    assert len(cut.items) == 2
    assert cut.truncated_chunk_id is None
    assert cut.cut_total == 20_480


def test_the_cut_counts_with_the_counter_it_is_given() -> None:
    seen: list[str] = []

    def counter(text: str) -> int:
        seen.append(text)
        return 1_000  # every chunk is 1,000 tokens whatever its words

    chunks = [{"chunk_id": f"c{i}", "text": f"t{i}"} for i in range(30)]
    cut = scoring35.evidence_by_tokens(chunks, counter, lambda text, n: text)
    assert len(cut.items) == 21
    assert seen[:3] == ["t0", "t1", "t2"]


def test_the_cut_refuses_merged_rows() -> None:
    rows = [{"chunk_id": "m", "chunk_ids": ["a", "b"], "text": "x"}]
    with pytest.raises(ValueError, match="merged"):
        scoring35.evidence_by_tokens(rows, _words, _cut_words)


# --- the one write path for scores -------------------------------------------------------------


def test_write_scores_writes_jsonl_and_json_atomically(tmp_path: Path) -> None:
    record = _score("bioasq", [_c("a", "1")], _gold("q", ["1"]))
    scoring35.write_scores(tmp_path / "s" / "scores.jsonl", [record], half="A")
    lines = (tmp_path / "s" / "scores.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [record]
    summary = scoring35.summarise([record], expected_n=1)
    scoring35.write_scores(tmp_path / "s" / "summary.json", summary, half="A")
    assert json.loads((tmp_path / "s" / "summary.json").read_text(encoding="utf-8")) == summary
    assert not list((tmp_path / "s").glob("*.tmp"))


def test_write_scores_refuses_an_unknown_half(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="C"):
        scoring35.write_scores(tmp_path / "x.json", {}, half="C")


# --- 13.6: FinanceBench number match --------------------------------------------------------


@pytest.mark.parametrize(
    ("reference", "answer", "expected"),
    [
        ("$1,577 million", "Revenue was $1.58 billion.", True),
        ("$1.58 billion", "Revenue was $1,577 million.", True),
        ("12.5%", "The margin was 12.5 percent.", True),
        ("(3.2)", "The change was -3.2.", True),
        ("-3.2", "The change was (3.2).", True),
        ("$5 million", "The answer is not in the filing.", False),
        ("Revenue 10 and cost 20.", "Revenue was 10.", False),
        ("Revenue 10 and cost 20.", "Cost 20, revenue 10.", True),
        ("$100 million", "$102 million", False),  # 2% difference
        ("$100 million", "$100.5 million", True),  # within 1%
        ("0.1", "0.14", True),  # equal after rounding to the reference's one decimal place
        ("(3.2)", "3.2", False),  # the sign counts
        ("4.2%", "4.2", True),
        ("2019-2020 change was 5", "5", False),  # 2019 and 2020 are reference numbers too
    ],
)
def test_number_match_known_pairs(reference: str, answer: str, expected: bool) -> None:
    assert scoring35.number_match(reference, answer) is expected


def test_a_reference_with_no_number_is_not_scored() -> None:
    assert scoring35.number_match("Data Center", "Data Center, 5 units") is None


def test_numbers_read_scale_sign_and_separators() -> None:
    values = [n.value for n in scoring35.extract_numbers("$1,577 million, (3.2), -4, 7bn, 12.5%")]
    expected = ["1577000000", "-3.2", "-4", "7000000000", "12.5"]
    assert values == [Decimal(v) for v in expected]
