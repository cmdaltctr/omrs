"""Blind relevance audit of Experiment 35 (A18; pre-registration section 11.3 and 21)."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load

audit35 = load("audit35")
select35 = load("select35")
bootstrap35 = load("bootstrap35")
scoring35 = load("scoring35")

ON = select35.Setup("4b", 512, "off", "on").name
ON2 = select35.Setup("8b", 1024, "4b", "on").name
OFF = select35.Setup("4b", 512, "off", "off").name
OFF2 = select35.Setup("8b", 1024, "4b", "off").name
T20K = select35.Setup("4b", 512, "off", "on", True).name


def _rec(setup: str, qid: str, ranked: list[str], dataset: str = "bioasq") -> dict[str, Any]:
    return {"dataset": dataset, "setup": setup, "qid": qid, "ranked_units": ranked}


QRELS = {"q1": {"g1": 1, "j1": 0}, "q2": {"g2": 1}}


def test_frame_keeps_top3_pairs_of_one_arm_only_unjudged_and_once() -> None:
    records = [
        _rec(ON, "q1", ["g1", "a", "shared", "late", "x"]),
        _rec(ON2, "q1", ["a", "g1", "shared", "j1", "y"]),  # a again: kept once; j1 judged
        _rec(OFF, "q1", ["g1", "b", "shared", "a2", "late"]),  # late at rank 5 in off? rank4+
        _rec(OFF2, "q1", ["shared", "b", "j1"]),
        _rec(T20K, "q1", ["t20k_only"]),  # a -t20k setup is not one of the 72
        _rec(ON, "q2", ["unmapped:c1", "g2"]),  # a placeholder unit has no text to label
    ]
    found = audit35.frame(records, {"bioasq": QRELS})["bioasq"]
    assert found["hon_only"] == [("q1", "a")]
    assert found["hoff_only"] == [("q1", "b")]
    assert audit35.frame(records, {"bioasq": QRELS}) == audit35.frame(
        list(reversed(records)), {"bioasq": QRELS}
    )


def test_frame_arm_exclusion_drops_a_unit_ranked_top3_by_the_other_arm() -> None:
    records = [_rec(ON, "q1", ["a", "b", "c"]), _rec(OFF, "q1", ["x", "a", "y"])]
    found = audit35.frame(records, {"bioasq": QRELS})["bioasq"]
    assert found["hon_only"] == [("q1", "b"), ("q1", "c")]
    assert found["hoff_only"] == [("q1", "x"), ("q1", "y")]


def _frames(n_on: int, n_off: int) -> dict[str, dict[str, list[tuple[str, str]]]]:
    return {
        "bioasq": {
            "hon_only": [(f"q{i:03d}", f"u{i}") for i in range(n_on)],
            "hoff_only": [(f"q{i:03d}", f"v{i}") for i in range(n_off)],
        },
        "financebench": {"hon_only": [("f1", "p1")], "hoff_only": []},
    }


def test_draw_follows_the_documented_order_with_one_generator() -> None:
    frames = _frames(80, 60)
    items, counts = audit35.draw(frames)
    rng = random.Random(20261120)  # noqa: S311
    expected: list[tuple[str, str, str, str]] = []
    for dataset in sorted(frames):
        for arm in ("hoff_only", "hon_only"):
            pairs = sorted(frames[dataset][arm])
            for qid, unit in rng.sample(pairs, min(50, len(pairs))):
                expected.append((dataset, qid, unit, arm))
    rng.shuffle(expected)
    assert [(i["dataset"], i["qid"], i["unit"], i["arm"]) for i in items] == expected
    assert counts["bioasq"]["hon_only"] == {"frame": 80, "drawn": 50}
    assert counts["bioasq"]["hoff_only"] == {"frame": 60, "drawn": 50}
    assert counts["financebench"]["hon_only"] == {"frame": 1, "drawn": 1}
    assert counts["financebench"]["hoff_only"] == {"frame": 0, "drawn": 0}


def test_draw_takes_the_whole_frame_when_it_holds_fewer_than_50() -> None:
    items, counts = audit35.draw(_frames(7, 3))
    assert counts["bioasq"]["hon_only"]["drawn"] == 7
    assert len([i for i in items if i["dataset"] == "bioasq"]) == 10


def test_the_seeds_are_the_registered_ones() -> None:
    assert audit35.SEED_SAMPLE == 20261120
    assert audit35.SEED_BOOTSTRAP == 20261145


class _Q:
    def __init__(self, text: str, reference: str) -> None:
        self.text, self.reference = text, reference


def test_sample_holds_arm_and_blind_items_never_do() -> None:
    items, counts = audit35.draw(_frames(3, 3))
    questions = {"bioasq": {f"q{i:03d}": _Q(f"Q{i}?", f"ref{i}") for i in range(3)}}
    questions["financebench"] = {"f1": _Q("fq", "fr")}
    texts = {(i["dataset"], i["qid"], i["unit"]): f"text {i['unit']}" for i in items}
    full = audit35.build_items(items, texts, questions)
    assert {"arm", "unit", "question", "reference", "unit_text"} <= set(full[0])
    blind = audit35.blind_items(full)
    assert [b["item_id"] for b in blind] == [f["item_id"] for f in full]
    banned = {"arm", "setup", "score", "rank"}
    assert all(not banned & set(b) for b in blind)
    assert all("hon_only" not in json.dumps(b) and "hoff_only" not in json.dumps(b) for b in blind)
    assert blind[0]["question"] and blind[0]["reference"] and blind[0]["unit_text"]
    assert counts["bioasq"]["hon_only"]["drawn"] == 3


def test_blind_items_go_through_the_audit_label_page_without_an_arm(tmp_path: Path) -> None:
    labelpage35 = load("labelpage35")
    items, _ = audit35.draw(_frames(3, 3))
    questions = {"bioasq": {f"q{i:03d}": _Q(f"Q{i}?", f"ref{i}") for i in range(3)}}
    questions["financebench"] = {"f1": _Q("fq", "fr")}
    texts = {(i["dataset"], i["qid"], i["unit"]): f"text {i['unit']}" for i in items}
    blind = audit35.blind_items(audit35.build_items(items, texts, questions))
    shown = labelpage35.page_items(audit35.SET_NAME, blind)
    assert [s["unit_text"] for s in shown] == [b["unit_text"] for b in blind]
    page = tmp_path / "audit.html"
    labelpage35.write_page(page, audit35.SET_NAME, blind)
    text = page.read_text(encoding="utf-8")
    for arm in audit35.ARMS:
        assert arm not in text
    assert "text u0" in text and "text v0" in text


def test_reference_label_uses_agreement_then_resolution_then_cant_tell() -> None:
    l1 = {"a": "relevant", "b": "relevant", "c": "not_relevant"}
    l2 = {"a": "relevant", "b": "not_relevant", "c": "relevant"}
    ref, unresolved = audit35.reference(l1, l2, {"b": "not_relevant"})
    assert ref == {"a": "relevant", "b": "not_relevant", "c": "cant_tell"}
    assert unresolved == 1


def _labelled(arm_labels: dict[str, list[str]]) -> tuple[list[dict], dict[str, str]]:
    items, ref, n = [], {}, 0
    for arm, labels in arm_labels.items():
        for label in labels:
            item_id = f"i{n}"
            items.append({"item_id": item_id, "dataset": "bioasq", "qid": f"q{n}", "arm": arm})
            ref[item_id] = label
            n += 1
    return items, ref


def test_shares_report_cant_tell_both_ways_with_wilson_intervals() -> None:
    from experiments._lib.stats_d6 import wilson

    items, ref = _labelled({"hon_only": ["relevant"] * 3 + ["cant_tell"] + ["not_relevant"] * 6})
    out = audit35.shares(items, ref)["bioasq"]["hon_only"]
    assert out["n"] == 10 and out["relevant"] == 3 and out["cant_tell"] == 1
    assert out["cant_tell_as_not_relevant"]["share"] == pytest.approx(0.3)
    assert out["cant_tell_as_relevant"]["share"] == pytest.approx(0.4)
    assert out["cant_tell_as_not_relevant"]["wilson"] == list(wilson(3, 10))
    assert out["cant_tell_as_relevant"]["wilson"] == list(wilson(4, 10))


def test_difference_is_hybrid_on_minus_off_with_the_registered_bootstrap() -> None:
    items, ref = _labelled(
        {"hon_only": ["relevant"] * 6 + ["not_relevant"] * 4,
         "hoff_only": ["relevant"] * 2 + ["not_relevant"] * 8}
    )  # fmt: skip
    got = audit35.difference(items, ref, n=200)["bioasq"]["cant_tell_as_not_relevant"]
    assert got["estimate"] == pytest.approx(0.4)

    def stat(rows: list[tuple[str, int]]) -> float:
        on = [v for a, v in rows if a == "hon_only"]
        off = [v for a, v in rows if a == "hoff_only"]
        return math.nan if not on or not off else sum(on) / len(on) - sum(off) / len(off)

    rows = [(i["qid"], (i["arm"], int(ref[i["item_id"]] == "relevant"))) for i in items]
    want = bootstrap35.bootstrap_by_question(rows, stat, n=200, seed=20261145, fill=None)
    assert (got["lower"], got["upper"]) == (want.lower, want.upper)


def test_bias_moves_row_4_by_the_audited_share_at_ranks_1_to_3() -> None:
    records = [
        _rec(ON, "q1", ["g1", "f1", "z"]),
        _rec(OFF, "q1", ["g1", "h1", "z"]),
        _rec(ON, "q2", ["g2", "w", "z"]),  # w is judged-free but in no frame: unchanged
        _rec(OFF, "q2", ["g2", "w", "z"]),
    ]
    for r in records:
        r["ndcg_at_10"] = 1.0
    frame = {"bioasq": {"hon_only": [("q1", "f1")], "hoff_only": [("q1", "h1")]}}
    gold = {"bioasq": {"q1": {"g1"}, "q2": {"g2"}}}
    shares = {"bioasq": {"hon_only": 0.5, "hoff_only": 0.25}}
    out = audit35.bias(records, frame, shares, gold)["bioasq"]
    assert out["reported_row4"] == pytest.approx(0.0)
    adjusted = (0.5 - 0.25) / math.log2(3) / 2  # q1 only moves; mean over 2 questions
    assert out["adjusted_row4"] == pytest.approx(adjusted)
    assert out["bias"] == pytest.approx(adjusted)


def test_bias_leaves_ranks_4_and_up_and_idcg_unchanged() -> None:
    records = [
        _rec(ON, "q1", ["g1", "a", "b", "f1"]),  # f1 at rank 4: no change
        _rec(OFF, "q1", ["g1", "a", "b", "h1"]),
    ]
    for r in records:
        r["ndcg_at_10"] = 1.0
    frame = {"bioasq": {"hon_only": [("q1", "f1")], "hoff_only": [("q1", "h1")]}}
    out = audit35.bias(
        records, frame, {"bioasq": {"hon_only": 1.0, "hoff_only": 0.0}}, {"bioasq": {"q1": {"g1"}}}
    )["bioasq"]
    assert out["bias"] == pytest.approx(0.0)


def _one_arm_case(hoff_frame: list[tuple[str, str]]) -> dict[str, Any]:
    records = [_rec(ON, "q1", ["g1", "f1", "z"]), _rec(OFF, "q1", ["g1", "x", "z"])]
    for r in records:
        r["ndcg_at_10"] = 1.0
    items, ref = _labelled({"hon_only": ["relevant", "not_relevant"]})  # hon share 0.5
    frames = {"bioasq": {"hon_only": [("q1", "f1")], "hoff_only": hoff_frame}}
    gold = {"bioasq": {"q1": {"g1"}}}
    return audit35._bias_by_way(records, frames, audit35.shares(items, ref), gold)


def test_an_empty_arm_frame_adds_no_correction_and_keeps_the_dataset() -> None:
    out = _one_arm_case([])  # hoff_only frame empty, hon_only frame labelled
    for way in audit35.WAYS:
        assert out[way]["bioasq"]["bias"] == pytest.approx(0.5 / math.log2(3))


def test_a_missing_share_for_a_non_empty_frame_stays_undefined() -> None:
    out = _one_arm_case([("q1", "x")])  # hoff_only frame has a unit but no label
    for way in audit35.WAYS:
        assert "bioasq" not in out[way]


def _prepared(tmp: Path) -> Path:
    """Return a passages folder with BioASQ unit files (no search chunk holds any text)."""
    folder = tmp / "passages" / "bioasq"
    folder.mkdir(parents=True)
    for unit in ("a", "c"):
        (folder / f"{unit}.md").write_text(f"passage {unit}", encoding="utf-8")
    return tmp / "passages"


def test_unit_text_comes_from_prepared_files_not_from_search_rows(tmp_path: Path) -> None:
    passages = _prepared(tmp_path)
    needed = [("bioasq", "q1", "a"), ("bioasq", "q2", "c")]
    got = audit35.load_texts(needed, passages=passages, pages=None)
    assert got == {("bioasq", "q1", "a"): "passage a", ("bioasq", "q2", "c"): "passage c"}


def test_financebench_unit_text_uses_the_page_reader(tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []

    def pages(doc: str, label: str) -> str:
        seen.append((doc, label))
        return f"page {doc} {label}"

    got = audit35.load_texts([("financebench", "q", "DOC_X#p7")], passages=None, pages=pages)
    assert got[("financebench", "q", "DOC_X#p7")] == "page DOC_X 7"
    assert seen == [("DOC_X", "7")]


def test_oracle_gold_rows_still_read_the_same_text(tmp_path: Path) -> None:
    oracle35 = load("oracle35")
    passages = _prepared(tmp_path)
    q = type("Q", (), {"relevant": ("c", "a")})()
    rows = oracle35.gold_rows("bioasq", q, passages=passages, pages=None)
    assert [(r["chunk_id"], r["text"]) for r in rows] == [("c", "passage c"), ("a", "passage a")]


def test_kappa_is_l1_against_l2_by_question_with_seed_20261129() -> None:
    from experiments._lib.stats_d6 import cohen_kappa

    items = [
        {"item_id": f"i{n}", "dataset": "bioasq", "qid": f"q{n % 6}", "arm": "hon_only"}
        for n in range(24)
    ]
    l1 = {i["item_id"]: ("relevant" if n % 3 else "not_relevant") for n, i in enumerate(items)}
    l2 = {k: (v if n % 5 else "cant_tell") for n, (k, v) in enumerate(l1.items())}
    got = audit35.kappa(items, l1, l2, n=300)
    rows = [((i["dataset"], i["qid"]), (l1[i["item_id"]], l2[i["item_id"]])) for i in items]

    def stat(pairs: list[tuple[str, str]]) -> float:
        return cohen_kappa([a for a, _ in pairs], [b for _, b in pairs])

    want = bootstrap35.bootstrap_by_question(rows, stat, n=300, seed=20261129, fill=0.0)
    assert got["items"] == 24
    assert got["overall"] == want.as_dict()


def _write_scores(out: Path) -> None:
    rows = [
        _rec(ON, "q1", ["g1", "a", "b"]),
        _rec(OFF, "q1", ["g1", "c", "b"]),
    ]
    for r in rows:
        r["ndcg_at_10"] = 1.0
    path = out / "scores" / "B" / "bioasq"
    path.mkdir(parents=True)
    for r in rows:
        (path / f"{r['setup']}.jsonl").write_text(json.dumps(r) + "\n", encoding="utf-8")


def test_cli_frame_sample_report_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_scores(tmp_path)
    monkeypatch.setattr(audit35.scoring35, "require_half_b", lambda out: None)
    monkeypatch.setattr(audit35, "load_qrels", lambda names: {"bioasq": {"q1": {"g1": 1}}})
    monkeypatch.setattr(
        audit35, "load_questions", lambda names: {"bioasq": {"q1": _Q("Q one?", "ref one")}}
    )
    monkeypatch.setattr(audit35, "load_gold", lambda names: {"bioasq": {"q1": {"g1"}}})
    passages = _prepared(tmp_path)  # the saved search rows hold no text (section 14.2)
    assert audit35.main(["frame", "--out", str(tmp_path)]) == 0
    frame = json.loads((tmp_path / "audit" / "frame.json").read_text())
    assert frame["counts"]["bioasq"] == {"hoff_only": 1, "hon_only": 1}
    assert audit35.main(["sample", "--out", str(tmp_path), "--passages-dir", str(passages)]) == 0
    sample = json.loads((tmp_path / "audit" / "audit-sample.json").read_text())
    blind = json.loads((tmp_path / "audit" / "audit-items-blind.json").read_text())
    assert {i["arm"] for i in sample["items"]} == {"hon_only", "hoff_only"}
    assert all("arm" not in b for b in blind)
    assert {b["unit_text"] for b in blind} == {"passage a", "passage c"}
    ids = [i["item_id"] for i in sample["items"]]
    for who in ("L1", "L2"):
        labels = {i: "relevant" if "a" in i else "not_relevant" for i in ids}
        (tmp_path / "audit" / f"labels-relevance_audit-{who}.json").write_text(
            json.dumps({"set": "relevance_audit", "labeller": who, "labels": labels})
        )
    assert audit35.main(["report", "--out", str(tmp_path), "--n", "50"]) == 0
    report = json.loads((tmp_path / "audit" / "audit-report.json").read_text())
    assert report["shares"]["bioasq"]["hon_only"]["n"] == 1
    assert "bias" in report and "difference" in report
    assert report["kappa"]["items"] == 2 and "overall" in report["kappa"]


def test_kappa_with_no_item_labelled_by_both_gives_undefined_not_an_error() -> None:
    items = [{"item_id": "i0", "dataset": "bioasq", "qid": "q0", "arm": "hon_only"}]
    got = audit35.kappa(items, {"i0": "relevant"}, {}, n=50)
    assert got["items"] == 0
    assert set(got) == {"items", "overall"}
    overall = got["overall"]
    assert set(overall) == set(bootstrap35.BootResult(0.0, 0.0, 0.0, 0, 0, 0, True).as_dict())
    assert (overall["estimate"], overall["lower"], overall["upper"]) == (None, None, None)
    assert overall["testable"] is False


def test_report_is_written_when_the_sample_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "scores" / "B" / "bioasq"
    path.mkdir(parents=True)
    for setup in (ON, OFF):  # only the judged unit g1 is ranked: both frames are empty
        row = {**_rec(setup, "q1", ["g1"]), "ndcg_at_10": 1.0}
        (path / f"{setup}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(audit35.scoring35, "require_half_b", lambda out: None)
    monkeypatch.setattr(audit35, "load_qrels", lambda names: {"bioasq": {"q1": {"g1": 1}}})
    monkeypatch.setattr(audit35, "load_questions", lambda names: {"bioasq": {}})
    monkeypatch.setattr(audit35, "load_gold", lambda names: {"bioasq": {"q1": {"g1"}}})
    passages = _prepared(tmp_path)
    assert audit35.main(["frame", "--out", str(tmp_path)]) == 0
    assert audit35.main(["sample", "--out", str(tmp_path), "--passages-dir", str(passages)]) == 0
    for who in ("L1", "L2"):
        (tmp_path / "audit" / f"labels-relevance_audit-{who}.json").write_text(
            json.dumps({"set": "relevance_audit", "labeller": who, "labels": {}})
        )
    assert audit35.main(["report", "--out", str(tmp_path), "--n", "50"]) == 0
    report = json.loads((tmp_path / "audit" / "audit-report.json").read_text())
    assert report["kappa"]["items"] == 0 and report["kappa"]["overall"]["estimate"] is None
