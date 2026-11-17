"""Experiment 35 length-controlled check, ``lengthcheck35.py`` (task 16.19; section 11.2).

300 claims from ``c2048`` crossed answers (seed 20261119) are judged again by
GLM-5.3 (``chat``) and Clef-Flash against one 512-token window of each cited
chunk; the report gives the verdict change rate with a Wilson interval.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from experiments._lib import stats_d6
from tests._exp35_fixtures import load

lengthcheck35 = load("lengthcheck35")
outputs35 = load("outputs35")

FILLER = " ".join(f"w{i}" for i in range(600))
SETUPS = ("e4b-c2048-roff-hoff", "e4b-c512-roff-hoff", "e4b-c2048-r4b-hon-t20k")


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _build(out: Path, n: int = 4, datasets=("bioasq",)) -> None:
    for dataset in datasets:
        for setup in SETUPS:
            folder = out / dataset / "answer" / setup / "run1"
            answers, judges = [], []
            for i in range(n):
                text = f"{FILLER} alpha beta{i}"
                answers.append(
                    {
                        "qid": f"q{i}",
                        "answer": f"Alpha beta{i} [1].",
                        "evidence": [{"ordinal": 1, "text": text}],
                    }
                )
                judges.append({"qid": f"q{i}", "verdicts": [{"index": 0, "verdict": "supported"}]})
            _write(folder / "answer.jsonl", answers)
            _write(folder / "judge-chat.jsonl", judges)
            _write(folder / "judge-clef_flash.jsonl", judges)


def _offsets(text: str) -> list[tuple[int, int]]:
    return [m.span() for m in re.finditer(r"\S+", text)]


class _Judge:
    def __init__(self, verdict: str = "unsupported", fail: int = 0) -> None:
        self.verdict, self.fail, self.seen = verdict, fail, []

    async def judge(self, claim: str, texts: list[str]):
        self.seen.append(texts)
        if self.fail:
            self.fail -= 1
            raise RuntimeError("down")
        return SimpleNamespace(verdict=self.verdict, call=None)


def _ctx(out: Path, judges: dict, *, resume: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        layout=outputs35.Layout(out),
        judges=judges,
        offsets=_offsets,
        key={"seed": 1},
        resume=resume,
        args=SimpleNamespace(rate_limit_attempts=1, judges="chat,clef_flash"),
    )


def test_pool_holds_cited_claims_of_every_c2048_crossed_answer(tmp_path: Path) -> None:
    # Section 11.2: "300 claims from c2048 crossed answers", no dataset limit, so Legal
    # answers enter too (drop step 1 removes them by removing the answers).
    _build(tmp_path, datasets=("bioasq", "legal"))
    pool = lengthcheck35.pool(tmp_path)
    assert {(p["dataset"], p["setup"]) for p in pool} == {
        ("bioasq", "e4b-c2048-roff-hoff"),
        ("legal", "e4b-c2048-roff-hoff"),
    }
    assert pool[0]["original"] == {"chat": "supported", "clef_flash": "supported"}


def test_pool_leaves_out_refusal_claims(tmp_path: Path) -> None:
    _build(tmp_path)
    claimkinds35 = load("claimkinds35")
    folder = tmp_path / "bioasq" / "answer" / SETUPS[0] / "run1"
    key = claimkinds35.claim_key("q0", "Alpha beta0.")
    _write(folder / "claim-kinds.jsonl", [{"claim_key": key, "qid": "q0", "kind": "refusal"}])
    assert "q0" not in {p["qid"] for p in lengthcheck35.pool(tmp_path)}


def test_draw_is_seeded_and_capped(tmp_path: Path) -> None:
    pool = [{"item_id": f"i{n:03d}"} for n in range(400)]
    first = lengthcheck35.draw(pool)
    assert len(first) == 300 and first == lengthcheck35.draw(list(reversed(pool)))
    assert lengthcheck35.SEED == 20261119
    assert len(lengthcheck35.draw(pool[:5])) == 5


def test_windows_are_512_tokens_and_the_best_shares_most_words() -> None:
    text = " ".join(f"t{i}" for i in range(1100))
    windows = lengthcheck35.windows(text, _offsets(text))
    assert [len(w.split()) for w in windows] == [512, 512, 76]
    assert lengthcheck35.best_window("T600 and t601", windows) == windows[1]
    assert lengthcheck35.best_window("nothing shared", windows) == windows[0]


def test_stage_rejudges_on_windows_and_reports_the_change_rate(tmp_path: Path) -> None:
    _build(tmp_path)
    judges = {"chat": _Judge("unsupported"), "clef_flash": _Judge("supported")}
    assert asyncio.run(lengthcheck35.lengthcheck_stage(_ctx(tmp_path, judges))) == 0
    assert all(len(t[0].split()) <= 512 and "alpha" in t[0] for t in judges["chat"].seen)
    report = json.loads((tmp_path / "lengthcheck" / "lengthcheck.json").read_text())
    assert report["seed"] == 20261119 and report["claims"] == 4
    assert report["chat"]["changed"] == 4 and report["chat"]["rate"] == 1.0
    assert (report["chat"]["low"], report["chat"]["high"]) == pytest.approx(stats_d6.wilson(4, 4))
    assert report["clef_flash"]["changed"] == 0
    assert "gate" not in report


def test_a_judge_error_is_resent_and_the_third_closes_it(tmp_path: Path) -> None:
    _build(tmp_path, n=1)
    chat = _Judge("supported", fail=3)
    judges = {"chat": chat, "clef_flash": _Judge("supported")}
    for n in range(3):
        try:
            asyncio.run(lengthcheck35.lengthcheck_stage(_ctx(tmp_path, judges, resume=n > 0)))
        except lengthcheck35.StageIncomplete:
            assert n < 2
    report = json.loads((tmp_path / "lengthcheck" / "lengthcheck.json").read_text())
    assert report["chat"]["n"] == 0 and report["chat"]["missing"] == 1


def test_drop_step_two_skips_the_check(tmp_path: Path) -> None:
    _build(tmp_path)
    (tmp_path / "drops.json").write_text(json.dumps({"drops": [{"step": 2, "reason": "x"}]}))
    judges = {"chat": _Judge(), "clef_flash": _Judge()}
    assert asyncio.run(lengthcheck35.lengthcheck_stage(_ctx(tmp_path, judges))) == 0
    assert not (tmp_path / "lengthcheck").exists()
