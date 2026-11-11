"""Tests for the GLM-5.3 ``chat`` runner (Exp 35 task 6.4); no network, stub judge."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import run_glm_chat as glm


class StubJudge:
    """Says ``supported`` unless the claim contains ``false``; one call record per row."""

    name = "chat"
    version = "chat-oneword/1"

    async def judge(self, claim: str, _evidence: list[str]) -> SimpleNamespace:
        verdict = "unsupported" if "false" in claim else "supported"
        call = SimpleNamespace(error=None, p_yes=None, model="glm-5.3", sha256=None,
                               version=self.version, host="api.z.ai", settings={})  # fmt: skip
        return SimpleNamespace(verdict=verdict, call=call)


@pytest.fixture
def triples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def triple(cls: str, label: str, claim: str) -> dict[str, str]:
        return {"attack_class": cls, "label": label, "claim": claim, "evidence": "e"}

    data = {"triples": [
        triple("faithful", "supported", "a true claim"),
        triple("negation", "unsupported", "a false claim"),
        triple("negation", "unsupported", "missed"),
    ]}  # fmt: skip
    path = tmp_path / "ground-truth.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(glm, "EXP20_TRIPLES", path)
    return path


def run(tmp_path: Path, *extra: str) -> int:
    argv = ["--set", "exp20", "--out-dir", str(tmp_path / "out"), "--concurrency", "2", *extra]
    return glm.main(argv, make_judge=lambda _out, _reasoning: StubJudge())


def test_values_point_chat_judge_at_the_coding_plan_with_a_key_reference() -> None:
    values = glm.build_values("low")
    assert values["openai_compatible_base_url"] == "https://api.z.ai/api/coding/paas/v4"
    assert values["openai_compatible_api_key"] == "env://OMRS_EXP35_ZAI_KEY"
    answer = values["answer"]
    assert (answer["verify_judge"], answer["verify_provider"], answer["verify_model"]) == (
        "chat", "openai_compatible", "glm-5.3")  # fmt: skip
    assert answer["verify_reasoning"] == "low" and answer["verify_temperature"] == 0


def test_every_row_written_once_and_scored(tmp_path: Path, triples: Path) -> None:
    assert run(tmp_path) == 0
    path = tmp_path / "out" / "exp20-chat-low.jsonl"
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    rows = [line for line in lines if line["kind"] == "row"]
    assert sorted(r["idx"] for r in rows) == [0, 1, 2]
    assert lines[0]["kind"] == "header" and sum(line["kind"] == "facts" for line in lines) == 1
    assert run(tmp_path, "--score") == 0
    summary = json.loads((tmp_path / "out" / "exp20-chat-low-scores.json").read_text())
    assert summary["unsupported_recall"] == 0.5 and summary["false_rejection"] == 0.0
    assert summary["keep_low"] is False


def test_resume_judges_only_missing_rows(tmp_path: Path, triples: Path) -> None:
    assert run(tmp_path) == 0
    path = tmp_path / "out" / "exp20-chat-low.jsonl"
    kept = [line for line in path.read_text().splitlines() if '"idx": 2' not in line]
    path.write_text("\n".join(kept) + "\n")
    assert run(tmp_path, "--resume") == 0
    rows = [json.loads(x) for x in path.read_text().splitlines() if '"kind": "row"' in x]
    assert sorted(r["idx"] for r in rows) == [0, 1, 2]


def test_existing_file_without_resume_is_refused(tmp_path: Path, triples: Path) -> None:
    assert run(tmp_path) == 0
    assert run(tmp_path) == 2


def test_failed_rows_never_count_as_caught_or_rejected() -> None:
    rows = [
        {"label": 0, "verdict": "unsupported", "error": None},
        {"label": 0, "verdict": None, "error": "timeout"},
        {"label": 1, "verdict": "supported", "error": None},
        {"label": 1, "verdict": None, "error": "timeout"},
    ]
    summary = glm.exp20_summary(rows)
    assert summary["unsupported_recall"] == 1.0
    assert summary["false_rejection"] == 0.0
    assert summary["errors"] == 2
    assert summary["keep_low"] is False


def test_score_refuses_a_partial_file(tmp_path: Path, triples: Path) -> None:
    assert run(tmp_path) == 0
    path = tmp_path / "out" / "exp20-chat-low.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    assert run(tmp_path, "--score") == 2
