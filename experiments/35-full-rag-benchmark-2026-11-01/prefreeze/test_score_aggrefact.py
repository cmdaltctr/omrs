"""Tests of the LLM-AggreFact scorer command on runner output from stub judges."""

from __future__ import annotations

import json

import pytest
import run_aggrefact as run
import score_aggrefact as score
from aggrefact_testkit import StubJudge, make_split, truthful


@pytest.fixture
def split(tmp_path, monkeypatch):
    return make_split(tmp_path, monkeypatch)


def _run(split, out, decide=truthful, *extra):
    argv = ["--strategy", "clef_flash", "--parquet", str(split), "--out-dir", str(out), *extra]
    assert run.main(argv, make_judge=lambda s, o, g: StubJudge(s, decide)) == 0


def _score(out, *extra):
    return score.main(["--strategy", "clef_flash", "--out-dir", str(out), *extra])


def test_scores_a_complete_file_atomically(split, tmp_path, capsys):
    out = tmp_path / "out"
    _run(split, out)
    assert _score(out) == 0
    target = out / "aggrefact-clef_flash-scores.json"
    summary = json.loads(target.read_text(encoding="utf-8"))
    assert not (out / "aggrefact-clef_flash-scores.json.tmp").exists()
    assert summary["partial"] is False and summary["rows_scored"] == 30
    assert summary["average"] == pytest.approx(100.0) and summary["RAGTruth"] == pytest.approx(100)
    assert summary["status"] == "fail"  # 100 is far from the published 76.6
    assert summary["pass_rule"]["average_gap"] == pytest.approx(23.4)
    assert summary["judge_call"] == {
        "model": "stub/model:Q8_0", "sha256": "ab" * 32, "version": "clef-flash-claim/1",
        "host": None,
    }  # fmt: skip
    assert summary["run"]["model"] == "ggml-org/Clef-Flash-GGUF:Q8_0"
    assert set(summary["datasets"]) == {"AggreFact-CNN", "Wice", "RAGTruth"}
    assert "[score] clef_flash: fail" in capsys.readouterr().out


def test_error_rows_lower_the_score_and_are_counted(split, tmp_path):
    out = tmp_path / "out"

    def fail_positives_of_wice(idx):
        # Wice holds rows 10 to 19; the odd ones are label 1.
        if 10 <= idx < 20 and idx % 2:
            return "unparseable", "request-failed"
        return truthful(idx)

    _run(split, out, fail_positives_of_wice)
    assert _score(out) == 0
    summary = json.loads((out / "aggrefact-clef_flash-scores.json").read_text(encoding="utf-8"))
    wice = summary["datasets"]["Wice"]
    assert wice["errors"] == 5 and wice["fn"] == 5 and wice["tp"] == 0
    assert wice["balanced_accuracy"] == pytest.approx(50.0)  # TPR 0, TNR 1
    assert summary["rows_counted_wrong"] == 5
    assert summary["average"] == pytest.approx((100 + 50 + 100) / 3)


def test_partial_file_is_refused_then_allowed(split, tmp_path, capsys):
    out = tmp_path / "out"
    _run(split, out, truthful, "--limit", "12")
    assert _score(out) == 2
    assert "12 distinct rows, not 30" in capsys.readouterr().out
    assert not (out / "aggrefact-clef_flash-scores.json").exists()
    assert _score(out, "--allow-partial") == 0
    summary = json.loads((out / "aggrefact-clef_flash-scores.json").read_text(encoding="utf-8"))
    assert summary["status"] == "partial" and summary["partial"] is True


def test_missing_file_is_a_plain_refusal(tmp_path, capsys):
    assert _score(tmp_path) == 2
    assert "does not exist" in capsys.readouterr().out
