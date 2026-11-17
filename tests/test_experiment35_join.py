"""Experiment 35 join step, ``join35.py`` (tasks 6.1, 6.2, 15.9 join part, 16.29 join part)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests import _exp35_join_fixtures as fx
from tests._exp35_fixtures import load

join35 = load("join35")


@pytest.fixture
def built(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    out, experiment = tmp_path / "out", tmp_path / "exp"
    pods = fx.build(out, experiment)
    return out, experiment, pods


def _join(out: Path, experiment: Path, pods: list[Path], **kw: object) -> dict:
    kw.setdefault("runs", fx.RUNS)
    return join35.join(
        out,
        experiment=experiment,
        records=pods,
        search_setups=fx.SETUPS,
        answer_setups=fx.SETUPS,
        datasets=fx.DATASETS,
        requested=fx.REQUESTED,
        **kw,
    )


def _run(out: Path, dataset: str = "bioasq", setup: str = fx.SETUPS[0], run: int = 2) -> Path:
    return out / dataset / "answer" / setup / f"run{run}"


def _fails(report: dict, *words: str) -> bool:
    return any(all(w in f for w in words) for f in report["failures"])


def test_a_complete_folder_passes_and_writes_the_answer_scores(built) -> None:
    out, experiment, pods = built
    report = _join(out, experiment, pods)
    assert report["ok"] is True, report["failures"]
    assert json.loads((out / "join.json").read_text())["ok"] is True
    lines = (out / "answer-scores.jsonl").read_text().splitlines()
    scores = [json.loads(line) for line in lines]
    assert len(scores) == 2 * 2 * 3 * 2
    first = scores[0]
    assert {"qid", "doc_id", "run", "cut_tokens"} <= set(first)
    assert first["faithfulness_glm_factual"] == 1.0
    assert first["faithfulness_glm_factual_uncited"] == 0.5
    assert first["ragas_answer_correctness"] == 0.75
    assert report["uncited_segment_share"]["bioasq"][fx.SETUPS[0]] == 0.5


def test_search_run_one_only_passes_and_a_missing_search_marker_fails(built) -> None:
    out, experiment, pods = built
    (out / "bioasq" / "search" / fx.SETUPS[1] / "run1" / ".done-search.json").unlink()
    report = _join(out, experiment, pods)
    assert report["ok"] is False
    assert _fails(report, "bioasq", fx.SETUPS[1], "search")
    assert not (out / "answer-scores.jsonl").exists()


def test_a_missing_judge_marker_names_dataset_setup_run_and_stage(built) -> None:
    out, experiment, pods = built
    (_run(out) / ".done-judge-chat.json").unlink()
    report = _join(out, experiment, pods)
    assert _fails(report, "bioasq", fx.SETUPS[0], "run2", "judge-chat")


@pytest.mark.parametrize("stage", ["ragas", "claimkinds"])
def test_a_missing_ragas_or_claimkinds_marker_fails(built, stage: str) -> None:
    out, experiment, pods = built
    (_run(out) / f".done-{stage}.json").unlink()
    assert _fails(_join(out, experiment, pods), "bioasq", fx.SETUPS[0], "run2", stage)


def test_fewer_ragas_rows_than_answers_fails(built) -> None:
    out, experiment, pods = built
    path = _run(out) / "ragas.jsonl"
    path.write_text(path.read_text().splitlines()[0] + "\n")
    assert _fails(_join(out, experiment, pods), "run2", "ragas", "1 rows", "2 answers")


def test_different_keys_across_runs_name_the_fields(built) -> None:
    out, experiment, pods = built
    (_run(out) / "answer.key.json").write_text(json.dumps({"seed": 2, "qids": list(fx.QIDS)}))
    assert _fails(_join(out, experiment, pods), "answer.key.json", "seed")


@pytest.mark.parametrize(
    "checks",
    [
        {**fx.CHECKS, "table_version_unchanged": False},
        {**fx.CHECKS, "fingerprint": {**fx.CHECKS["fingerprint"], "table_version": 4}},
    ],
)
def test_a_changed_fingerprint_check_fails(built, checks: dict) -> None:
    out, experiment, pods = built
    (_run(out) / ".done-answer.json").write_text(json.dumps({"checks": checks}))
    assert _fails(_join(out, experiment, pods), "run2", "answer", "fingerprint")


@pytest.mark.parametrize("flag", [None, "prefreeze", "smoke"])
def test_a_run_needs_a_main_run_record(built, flag: str | None) -> None:
    out, experiment, pods = built
    wanted = fx.command("bioasq", fx.SETUPS[0], "answer", 2)
    for pod in pods:
        lines = [json.loads(line) for line in pod.read_text().splitlines()]
        kept = []
        for line in lines:
            if line["command"] == wanted:
                if flag is None:
                    continue
                line[flag] = True
            kept.append(line)
        fx.write_rows(pod, kept)
    assert _fails(_join(out, experiment, pods), "bioasq", fx.SETUPS[0], "run2", "run record")


def test_a_dataset_without_a_passing_rebuild_fails(built) -> None:
    out, experiment, pods = built
    (out / "legal" / "rebuild.json").write_text(json.dumps({"ok": False}))
    assert _fails(_join(out, experiment, pods), "legal", "rebuild.json")


def test_a_machine_record_that_differs_names_the_run_and_field(built) -> None:
    out, experiment, pods = built
    env = {**fx.ENV, "llama_cpp_build": 11000}
    fx.write_rows(_run(out) / "machine.jsonl", [{"host": "h", "pod_id": "p", "environment": env}])
    assert _fails(_join(out, experiment, pods), "run2", "llama_cpp_build")


def test_drop_step_one_removes_legal_answers(built) -> None:
    out, experiment, pods = built
    import shutil

    shutil.rmtree(out / "legal" / "answer")
    assert _fails(_join(out, experiment, pods), "legal", "answer")
    (out / "drops.json").write_text(json.dumps({"drops": [{"step": 1, "reason": "ceiling"}]}))
    report = _join(out, experiment, [])
    assert report["ok"] is True, report["failures"]
    assert report["dropped"] == [{"step": 1, "name": "Legal RAG Bench answer generation"}]


def test_a_missing_trace_line_is_rebuilt_and_counted(built) -> None:
    out, experiment, pods = built
    traces = _run(out) / "traces.jsonl"
    lines = traces.read_text().splitlines()
    traces.write_text("".join(line + "\n" for line in lines[:1] + lines[2:]))
    report = _join(out, experiment, pods)
    assert report["ok"] is True, report["failures"]
    assert report["traces_rebuilt"] == 1
    rebuilt = json.loads(traces.read_text().splitlines()[-1])
    assert (rebuilt["stage"], rebuilt["question_id"], rebuilt["status"]) == ("answer", "q2", "ok")
    assert rebuilt["benchmark_revision"] == "r"
    assert _join(out, experiment, [])["traces_rebuilt"] == 0


def test_a_row_with_no_matching_item_fails(built) -> None:
    out, experiment, pods = built
    path = _run(out) / "answer.jsonl"
    path.write_text(path.read_text() + json.dumps({"qid": "q9", "answer": ""}) + "\n")
    assert _fails(_join(out, experiment, pods), "run2", "q9", "no matching")


def test_smoke_join_checks_run_one_only_and_is_marked(tmp_path: Path) -> None:
    out, experiment = tmp_path / "out", tmp_path / "exp"
    pods = fx.build(out, experiment, runs=(1,))
    for pod in pods:
        lines = [{**json.loads(line), "smoke": True} for line in pod.read_text().splitlines()]
        fx.write_rows(pod, lines)
    report = _join(out, experiment, pods, runs=(1,), smoke=True)
    assert report["ok"] is True, report["failures"]
    assert report["smoke"] is True
    assert not (out / "answer-scores.jsonl").exists()


def test_returned_model_differences_are_counted_per_role(built) -> None:
    out, experiment, pods = built
    path = _run(out) / "answer.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["model_returned"] = "deepseek/other"
    fx.write_rows(path, rows)
    report = _join(out, experiment, pods)
    assert report["returned_model"]["answer"] == {"rows": 24, "differs": 1, "unknown": 0}
    assert report["returned_model"]["ragas-judge"]["differs"] == 0


def test_rows_without_a_returned_model_count_as_unknown(built) -> None:
    # The answer and chat judge rows as the stages write them today (task 15.9 gap).
    out, experiment, pods = built
    folder = _run(out)
    for name, field in (("answer.jsonl", None), ("judge-chat.jsonl", [])):
        rows = [json.loads(line) for line in (folder / name).read_text().splitlines()]
        fx.write_rows(folder / name, [{**r, "model_returned": field} for r in rows])
    report = _join(out, experiment, pods)
    assert report["returned_model"]["answer"]["unknown"] == 2
    assert report["returned_model"]["judge-glm"]["unknown"] == 24


def test_merge_appends_pod_records_in_start_order_once(built) -> None:
    out, experiment, pods = built
    existing = fx.record("run_arms.py --dataset bioasq --stage ingest", -5)
    target = experiment / "output" / "run-records.jsonl"
    target.write_text(json.dumps(existing) + "\n")
    before = target.read_bytes()
    assert join35.merge_records(experiment, pods) == 16
    after = target.read_bytes()
    assert after.startswith(before)
    times = [json.loads(line)["started_at"] for line in after.decode().splitlines()[1:]]
    assert times == sorted(times)
    assert join35.merge_records(experiment, pods) == 0
    assert target.read_bytes() == after


def test_main_smoke_finds_setups_on_disk(tmp_path: Path) -> None:
    out, experiment = tmp_path / "out", tmp_path / "exp"
    pods = fx.build(out, experiment, runs=(1,))
    argv = ["--out-dir", str(out), "--smoke", "--runs", "1", "--experiment-dir", str(experiment)]
    code = join35.main([*argv, "--records", *map(str, pods)])
    report = json.loads((out / "join.json").read_text())
    assert code == 0, report["failures"]
    assert report["smoke"] is True
