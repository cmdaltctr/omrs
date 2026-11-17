"""Join step of Experiment 35 (tasks 6.1, 6.2; design D10; H-13, H-28).

Usage (reads saved files only; runs on the Mac without the environment record)::

    join35.py --out-dir OUT [--records POD1.jsonl ...] [--smoke] [--runs N]
              [--experiment-dir DIR]

It first merges the pod run-record files into ``<experiment>/output/run-records.jsonl``
(:func:`merge_records`), then checks the output folder and writes
``<out>/join.json`` with ``ok`` and every failure. Checks per dataset:

- a passing ``<dataset>/rebuild.json`` (G2, design D20);
- each search setup: a ``search`` done-marker in run 1 (design D34);
- each answer setup and run: done-markers ``answer``, ``judge-chat``,
  ``judge-clef_flash``, ``ragas`` and ``claimkinds``; at least as many
  ``ragas.jsonl`` rows as answers; equal ``*.key.json`` contents across runs;
- every ``answer``, ``judge-*`` and ``search`` done-marker: a clean
  fingerprint check whose table version is the sealed one;
- every joined run: a main-run record whose command names its dataset, setup,
  stage and run (a ``prefreeze`` or ``smoke`` line does not count), and a
  machine record equal to ``environment.json`` in GPU, image, llama.cpp build
  and the shared GGUF hashes;
- each saved row has a trace line (a lost one is rebuilt and counted) and a
  question in its stage key.

A drop step in ``drops.json`` (``budget35.py``) removes what it drops from the
checks and is listed under ``dropped``; drop step 1 removes Legal answers.

``--smoke --runs 1`` checks run 1 of the setups on disk, counts any record
line and writes a report marked ``smoke``; G1 and the statistics refuse it.
A main join that passes writes ``<out>/answer-scores.jsonl`` (one record per
dataset, setup, run and question, ``joinscores35.answer_scores``) through
``scoring35.write_scores`` (half-B guard). ``join.json`` also holds
``uncited_segment_share`` per dataset and setup, ``returned_model`` per role,
``traces_rebuilt`` and ``records_merged``.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import arms  # noqa: E402
import budget35  # noqa: E402
import datasets35  # noqa: E402
import joinscores35  # noqa: E402
import scoring35  # noqa: E402
from outputs35 import Layout, read_rows, write_json  # noqa: E402

from omrs.core.experiment_records.run_record import RunRecord  # noqa: E402

ANSWER_STAGES = ("answer", "judge-chat", "judge-clef_flash", "ragas", "claimkinds")
CHECKED = ("search", "answer", "judge-chat", "judge-clef_flash")
ENV_FIELDS = ("gpu", "image", "llama_cpp_build", "gguf_sha256")
RECORDS = Path("output") / "run-records.jsonl"


def merge_records(experiment: Path, pods: Iterable[Path]) -> int:
    """Append the pod record lines the experiment file lacks, in start-time order (task 6.2).

    Earlier lines are never rewritten. Every new line must be a valid run record.

    Returns:
        The number of lines appended.
    """
    target = experiment / RECORDS
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    held = {line.strip() for line in text.splitlines() if line.strip()}
    new: dict[str, datetime] = {}
    for pod in pods:
        for line in Path(pod).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and line not in held and line not in new:
                new[line] = RunRecord.model_validate_json(line).started_at
    if not new:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        if text and not text.endswith("\n"):
            handle.write("\n")
        handle.writelines(line + "\n" for line in sorted(new, key=lambda k: (new[k], k)))
    return len(new)


def _records(experiment: Path, smoke: bool) -> set[tuple[str, str, str, int]]:
    """Return ``(dataset, setup, stage, run)`` of each counted record line."""
    found = set()
    for line in read_rows(experiment / RECORDS):
        if not smoke and (line.get("prefreeze") or line.get("smoke")):
            continue
        words = shlex.split(line["command"])
        opts = {w: words[i + 1] for i, w in enumerate(words[:-1]) if w.startswith("--")}
        if {"--dataset", "--setup", "--stage"} <= set(opts):
            run = int(opts.get("--run", 1))
            found.add((opts["--dataset"], opts["--setup"], opts["--stage"], run))
    return found


def _marker(folder: Path, stage: str) -> dict[str, Any] | None:
    path = folder / f".done-{stage}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class _Join:
    """One join over one output folder; collects failures in check order."""

    def __init__(self, out: Path, experiment: Path, smoke: bool) -> None:
        self.layout = Layout(out)
        self.failures: list[str] = []
        self.records = _records(experiment, smoke)
        env = self.layout.environment
        self.env = json.loads(env.read_text(encoding="utf-8")) if env.exists() else None
        if self.env is None:
            self.failures.append(f"{env} is missing")
        self.traces_rebuilt = 0

    def fingerprint(self, where: str, marker: Mapping[str, Any], dataset: str, setup: str) -> None:
        checks = marker.get("checks") or {}
        sealed_path = self.layout.fingerprint(dataset, arms.parse_setup(setup).index)
        sealed = json.loads(sealed_path.read_text(encoding="utf-8")) if sealed_path.exists() else {}
        found = (checks.get("fingerprint") or {}).get("table_version")
        if checks.get("table_version_unchanged") is not True or found != sealed.get(
            "table_version"
        ):
            self.failures.append(
                f"{where}: fingerprint check not clean (table version {found}, sealed "
                f"{sealed.get('table_version')}, unchanged {checks.get('table_version_unchanged')})"
            )

    def machine(self, where: str, folder: Path) -> None:
        lines = read_rows(folder / "machine.jsonl")
        if not lines:
            self.failures.append(f"{where}: no machine record")
        for line in lines:
            mine = line.get("environment") or {}
            for name in ENV_FIELDS[:3]:
                if self.env is not None and mine.get(name) != self.env.get(name):
                    self.failures.append(f"{where}: machine {name} differs from environment.json")
            built, ran = (self.env or {}).get("gguf_sha256") or {}, mine.get("gguf_sha256") or {}
            if any(built[f] != ran[f] for f in sorted(set(built) & set(ran))):
                self.failures.append(f"{where}: machine gguf_sha256 differs from environment.json")

    def run(self, where: str, folder: Path, key: tuple[str, str, str, int]) -> None:
        if key not in self.records:
            self.failures.append(f"{where}: no main-run run record names this run")
        self.machine(where, folder)
        added, failures = joinscores35.rebuild_traces(folder, key[0])
        self.traces_rebuilt += added
        self.failures += failures

    def search(self, dataset: str, setup: str) -> None:
        folder = self.layout.run_dir(dataset, "search", setup, 1)
        where = f"{dataset}/{setup}/search run1"
        marker = _marker(folder, "search")
        if marker is None:
            self.failures.append(f"{where}: no search done-marker")
            return
        self.fingerprint(where, marker, dataset, setup)
        self.run(where, folder, (dataset, setup, "search", 1))

    def answer(self, dataset: str, setup: str, runs: Sequence[int]) -> None:
        keys: dict[str, dict[int, Any]] = {}
        for run in runs:
            folder = self.layout.run_dir(dataset, "answer", setup, run)
            where = f"{dataset}/{setup}/run{run}"
            for stage in ANSWER_STAGES:
                marker = _marker(folder, stage)
                if marker is None:
                    self.failures.append(f"{where}: no {stage} done-marker")
                elif stage in CHECKED:
                    self.fingerprint(f"{where} {stage}", marker, dataset, setup)
            answers, ragas = read_rows(folder / "answer.jsonl"), read_rows(folder / "ragas.jsonl")
            if len(ragas) < len(answers):
                self.failures.append(
                    f"{where}: ragas has {len(ragas)} rows for {len(answers)} answers"
                )
            for path in sorted(folder.glob("*.key.json")):
                keys.setdefault(path.name, {})[run] = json.loads(path.read_text(encoding="utf-8"))
            if folder.is_dir():
                self.run(where, folder, (dataset, setup, "answer", run))
        for name, by_run in keys.items():
            first = by_run[min(by_run)]
            fields = sorted(
                {f for v in by_run.values() for f in {*v, *first} if v.get(f) != first.get(f)}
            )
            if fields or len(by_run) != len(runs):
                where = ", ".join(fields) or "runs"
                self.failures.append(f"{dataset}/{setup}: {name} differs across runs in {where}")


def _on_disk(out: Path, kind: str) -> list[str]:
    return sorted({p.name for p in out.glob(f"*/{kind}/*") if p.is_dir()})


def join(
    out: Path,
    *,
    experiment: Path,
    records: Iterable[Path] = (),
    search_setups: Sequence[str],
    answer_setups: Sequence[str],
    datasets: Sequence[str] = datasets35.DATASETS,
    runs: Sequence[int] = (1, 2, 3),
    smoke: bool = False,
    requested: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Merge the pod records, check the output folder and write ``join.json``; return it."""
    merged = merge_records(experiment, records)
    steps = budget35.read_drops(out)
    kept = budget35.answer_datasets(steps)
    state = _Join(out, experiment, smoke)
    answer_dirs: list[tuple[str, str, int, Path]] = []
    for dataset in datasets:
        rebuild = out / dataset / "rebuild.json"
        if not (rebuild.exists() and json.loads(rebuild.read_text(encoding="utf-8")).get("ok")):
            state.failures.append(f"{dataset}: no passing rebuild.json")
        for setup in search_setups:
            state.search(dataset, setup)
        if dataset not in kept:
            continue
        for setup in answer_setups:
            state.answer(dataset, setup, runs)
            answer_dirs += [
                (dataset, setup, r, state.layout.run_dir(dataset, "answer", setup, r)) for r in runs
            ]
    scores = [s for d, st, r, f in answer_dirs for s in joinscores35.answer_scores(f, d, st, r)]
    report = {
        "ok": not state.failures,
        "smoke": smoke,
        "runs": list(runs),
        "failures": state.failures,
        "dropped": [{"step": s, "name": budget35.DROP_STEPS[s]} for s in sorted(steps)],
        "records_merged": merged,
        "traces_rebuilt": state.traces_rebuilt,
        "uncited_segment_share": joinscores35.uncited_share(scores),
        "returned_model": joinscores35.returned_models(
            [f for *_, f in answer_dirs], requested or {}
        ),
    }
    write_json(out / "join.json", report)
    if report["ok"] and not smoke:
        scoring35.write_scores(out / "answer-scores.jsonl", scores, half="B", root=out)
    return report


def _requested(experiment: Path) -> dict[str, str]:
    plan = experiment / "plan.json"
    if not plan.exists():
        return {}
    refs = json.loads(plan.read_text(encoding="utf-8"))["runtime"]["references"]
    return {r["role"]: r["model"] for r in refs}


def main(argv: Sequence[str] | None = None) -> int:
    """Join one output folder; return 0 when it passes, else 1."""
    parser = argparse.ArgumentParser(prog="join35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the shared output folder")
    parser.add_argument("--records", type=Path, nargs="*", default=[], help="pod run-record files")
    parser.add_argument(
        "--smoke", action="store_true", help="check a smoke folder (setups on disk)"
    )
    parser.add_argument("--runs", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--experiment-dir", type=Path, default=EXP_DIR)
    args = parser.parse_args(argv)
    out = args.out_dir
    if args.smoke:
        search, answer = _on_disk(out, "search"), _on_disk(out, "answer")
        datasets = [d for d in datasets35.DATASETS if (out / d).is_dir()]
    else:
        chosen = json.loads((out / "selection.json").read_text(encoding="utf-8"))
        search = list(arms.SEARCH_SETUPS)
        answer = [s.name for s in arms.answer_setups(chosen["embedder"], chosen["reranker"])]
        datasets = list(datasets35.DATASETS)
    report = join(
        out,
        experiment=args.experiment_dir,
        records=args.records,
        search_setups=search,
        answer_setups=answer,
        datasets=datasets,
        runs=tuple(range(1, args.runs + 1)),
        smoke=args.smoke,
        requested=_requested(args.experiment_dir),
    )
    for failure in report["failures"]:
        print(f"[join] {failure}", flush=True)
    print(f"[join] {'passes' if report['ok'] else 'FAILS'}: {out / 'join.json'}", flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
