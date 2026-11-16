"""Halves A and B of Experiment 35 (readiness task 15.5, pre-registration section 4)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests._exp35_fixtures import load

split35 = load("split35")


def _questions() -> dict[str, dict[str, str | None]]:
    fb = {f"fb{i:03d}": f"doc{i % 7}" for i in range(30)}  # 7 documents of 4 or 5 questions
    return {
        "financebench": fb,
        "freshstack": {f"fs{i}": None for i in range(11)},
        "bioasq": {str(i): None for i in range(20)},
        "legal": {f"lg{i}": None for i in range(5)},
    }


def test_same_seed_same_halves() -> None:
    assert split35.make_halves(_questions()) == split35.make_halves(_questions())
    other = split35.make_halves(_questions(), seed=1)
    assert other != split35.make_halves(_questions())


def test_seed_is_registered_value() -> None:
    assert split35.SEED == 20261115


def test_financebench_split_by_document() -> None:
    questions = _questions()
    halves = split35.make_halves(questions)["financebench"]
    by_document: dict[str, set[str]] = {}
    for qid, document in questions["financebench"].items():
        by_document.setdefault(str(document), set()).add(halves[qid])
    assert all(len(sides) == 1 for sides in by_document.values())
    assert set(halves) == set(questions["financebench"])


def test_greedy_rule_fewer_questions_so_far_ties_to_a() -> None:
    # Order and sizes given: d1 (3) to A (tie 0-0), d2 (1) to B (1 < 3),
    # d3 (1) to B (1 < 3), d4 (2) to B (2 < 3), d5 (1) to A (3 < 4).
    ordered = [
        ("d1", ["a", "b", "c"]),
        ("d2", ["d"]),
        ("d3", ["e"]),
        ("d4", ["f", "g"]),
        ("d5", ["h"]),
    ]
    halves = split35.assign_documents(ordered)
    assert halves == {
        "a": "A",
        "b": "A",
        "c": "A",
        "d": "B",
        "e": "B",
        "f": "B",
        "g": "B",
        "h": "A",
    }


def test_other_datasets_split_by_question_first_half_rounded_up_is_a() -> None:
    halves = split35.make_halves(_questions())
    assert sorted(halves["freshstack"].values()).count("A") == 6  # 11 questions: 6 and 5
    assert sorted(halves["legal"].values()).count("A") == 3  # 5 questions: 3 and 2
    assert sorted(halves["bioasq"].values()).count("A") == 10


def test_shuffle_is_python_random_on_sorted_ids_per_dataset() -> None:
    import random

    halves = split35.make_halves(_questions())
    ids = sorted(_questions()["freshstack"])
    random.Random(20261115).shuffle(ids)  # noqa: S311
    assert {q for q, h in halves["freshstack"].items() if h == "A"} == set(ids[:6])
    fb = _questions()["financebench"]
    names = sorted(set(fb.values()))
    random.Random(20261115).shuffle(names)  # noqa: S311
    ordered = [(name, sorted(q for q, d in fb.items() if d == name)) for name in names]
    assert halves["financebench"] == split35.assign_documents(ordered)


def test_halves_json_lists_every_question_and_reads_back(tmp_path: Path) -> None:
    halves = split35.make_halves(_questions())
    path = tmp_path / "halves.json"
    digest = split35.write_halves(halves, path)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["seed"] == 20261115
    for dataset, questions in _questions().items():
        assert set(saved["halves"][dataset]) == set(questions)
    assert split35.read_halves(path) == halves
    assert split35.write_halves(halves, tmp_path / "again.json") == digest
    a_ids = split35.ids_in_half(halves, "freshstack", "A")
    assert a_ids == {q for q, h in halves["freshstack"].items() if h == "A"}
