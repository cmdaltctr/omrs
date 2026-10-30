"""Experiment 41 summary: score every finished arm and write ``output/summary.json``.

    summarise.py

For each arm that has ``output/ocr_state_<arm>.json`` the script writes
``output/katex_<arm>.json`` and ``output/recall_<arm>.json``, then computes the gates C1 to
C7 of ``protocol.md`` against the Experiment 37 baselines D0 and P0. Run ``analysis.py``
first for C6. Every gate names the file its numbers come from.

Scoring reuses the Experiment 37 scripts by path. ``score_recall.py`` is imported and its
``main`` runs on a shadow folder, because it reads fixed Experiment 37 paths. Two of those
paths (the Experiment 33 transcripts) are dangling symlinks, so the module constants are
pointed at the real folders. ``check_katex.mjs`` runs once per page in its ``--file`` mode,
because its engine mode also reads fixed Experiment 37 paths. KaTeX 0.16.22 must be
installed where Node finds it: ``npm install --prefix tools/katex katex@0.16.22`` in this
folder (``tools/`` is gitignored).

C5 reads ``review_verdicts.json`` in this folder, written after the operator review:
``{"verdicts": {"<arm>": {"<page>": {"verdict": "clean" | "invented"}}}}``. It is null until
that file exists. Interpreter: any Python 3.11 or later.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analysis  # noqa: E402 - same folder; pinned Experiment 37 inputs
import run_ocr  # noqa: E402 - same folder; shared paths

OUT, EXP37 = run_ocr.OUT, run_ocr.EXP37
EXP33_REAL = EXP37.parent / "33-ocr-routing-natural-positive-2026-09-17"
RUNS = ("E-maths", "E-scan", "E-script")
NEW_ARMS = sorted(run_ocr.ARMS)
EIGHT_BIT = ("D2", "D4", "P2", "P4")
KATEX_VERSION = "0.16.22"
GIB = 2**30


def read_json(path: Path) -> Any:
    """Read one JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically."""
    run_ocr.write_atomic(path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")


# ── Scoring (writes katex_<arm>.json and recall_<arm>.json) ───────────────


def score_katex(arm: str, pages: dict[str, Any]) -> dict[str, Any]:
    """Run ``check_katex.mjs --file`` on every ok page of E-maths and E-scan."""
    analysis.check_pinned(["check_katex.mjs"])
    node_path = [str(run_ocr.EXP_DIR / "tools/katex/node_modules"), os.environ.get("NODE_PATH", "")]
    env = {**os.environ, "NODE_PATH": os.pathsep.join(p for p in node_path if p)}
    totals: dict[str, Any] = {}
    out_pages: dict[str, Any] = {}
    for run in ("E-maths", "E-scan"):
        total = {"formulas": 0, "errors": 0, "pages_with_formulas": 0, "pages_not_ok_skipped": 0}
        for key, page in pages.items():
            if page["run"] != run:
                continue
            if page["status"] != "ok":
                total["pages_not_ok_skipped"] += 1
                continue
            done = subprocess.run(  # noqa: S603 - fixed argv
                [
                    shutil.which("node") or "node",
                    str(EXP37 / "check_katex.mjs"),
                    "--file",
                    str(run_ocr.page_path(arm, key)),
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            if done.returncode != 0:
                raise SystemExit(
                    f"check_katex.mjs failed (is KaTeX {KATEX_VERSION} installed?):\n{done.stderr}"
                )
            result = json.loads(done.stdout)
            out_pages[f"{run} {key}"] = {"formulas": result["formulas"], "errors": result["detail"]}
            total["formulas"] += result["formulas"]
            total["errors"] += result["errors"]
            total["pages_with_formulas"] += bool(result["formulas"])
        totals[run] = total
    formulas = sum(t["formulas"] for t in totals.values())
    errors = sum(t["errors"] for t in totals.values())
    rate = round(errors / formulas, 4) if formulas else None
    report = {
        "engine": arm,
        "katex": KATEX_VERSION,
        "rule": "check_katex.mjs --file on each ok page; same rule as Experiment 37",
        "totals": totals,
        "overall": {"formulas": formulas, "errors": errors, "error_rate": rate},
        "pages": out_pages,
    }
    write_json(OUT / f"katex_{arm}.json", report)
    return report


def score_recall(arm: str, engine: str, pages: dict[str, Any]) -> dict[str, Any]:
    """Run Experiment 37 ``score_recall.main`` on a shadow folder that holds this arm's state."""
    analysis.check_pinned(
        [
            "score_recall.py",
            "plan.json",
            f"{analysis.EXP33_REL}/build_labels.py",
            f"{analysis.EXP33_REL}/output/local_ocr/pages.json",
            f"{analysis.EXP33_REL}/output/.transcripts",
            f"{analysis.EXP33_REL}/output/.transcripts_split",
        ]
    )
    spec = importlib.util.spec_from_file_location("exp37_score_recall", EXP37 / "score_recall.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    module.TRANSCRIPTS = EXP33_REAL / "output/.transcripts"
    module.SPLIT = EXP33_REAL / "output/.transcripts_split"
    shadow = OUT / ".recall_shadow" / arm
    shutil.rmtree(shadow, ignore_errors=True)
    (shadow / "output").mkdir(parents=True)
    shutil.copyfile(EXP37 / "plan.json", shadow / "plan.json")
    (shadow / "output" / engine).symlink_to(run_ocr.page_path(arm, "a:1").parent.parent)
    script_pages = {
        key: {"status": "ok"} if p["status"] == "ok" else {"status": "error", "code": p["status"]}
        for key, p in pages.items()
        if p["run"] == "E-script"
    }
    state = {"engines": {engine: {"runs": {"E-script": {"pages": script_pages}}}}}
    write_json(shadow / "output" / f"ocr_state_{engine}.json", state)
    module.EXP_DIR = shadow
    sys.argv = ["score_recall.py", "--engine", engine]
    module.main()
    report = read_json(shadow / "output" / f"recall_{engine}.json")
    report["engine"] = arm
    write_json(OUT / f"recall_{arm}.json", report)
    return report


# ── One view per arm (new arms and the two baselines) ─────────────────────


def baseline_view(arm: str) -> dict[str, Any]:
    """Read an Experiment 37 baseline (D0 or P0) into the same shape as a new arm."""
    engine = run_ocr.BASELINES[arm]
    names = [f"output/{n}_{engine}.json" for n in ("ocr_state", "katex", "recall")]
    analysis.check_pinned(names)
    state = read_json(EXP37 / names[0])["engines"][engine]
    pages: dict[str, Any] = {}
    for run in RUNS:
        for key, p in state["runs"][run]["pages"].items():
            timeout = p.get("code") == "timeout"
            status = "ok" if p["status"] == "ok" else ("timeout" if timeout else "error")
            pages[key] = {
                "run": run,
                "status": status,
                "timeout": timeout,
                "seconds": p["seconds"],
                "includes_start": p["includes_start"],
            }
    files = {"state": names[0], "katex": names[1], "recall": names[2]}
    return {
        "arm": arm,
        "pages": pages,
        "peak_bytes": state["peak_footprint_bytes"],
        "katex": read_json(EXP37 / names[1]),
        "recall": read_json(EXP37 / names[2]),
        "files": {
            k: f"experiments/37-dots-mocr-routing-acceptance-2026-09-30/{v}"
            for k, v in files.items()
        },
    }


def arm_view(arm: str) -> dict[str, Any]:
    """Score a new arm and read its state, KaTeX and recall files."""
    state = read_json(run_ocr.state_path(arm))
    pages = state["pages"]
    procs = state.get("processes", [])
    peak = sum(
        max((p.get(f"{who}_peak_bytes", 0) for p in procs), default=0)
        for who in ("client", "server")
    )
    return {
        "arm": arm,
        "pages": pages,
        "peak_bytes": peak,
        "katex": score_katex(arm, pages),
        "recall": score_recall(arm, state["engine"], pages),
        "processes": procs,
        "files": {
            "state": f"output/ocr_state_{arm}.json",
            "katex": f"output/katex_{arm}.json",
            "recall": f"output/recall_{arm}.json",
        },
    }


# ── Gates ─────────────────────────────────────────────────────────────────


def speeds(pages: dict[str, Any], keys: list[str] | None = None) -> dict[str, Any]:
    """Return count, median, 90th percentile, maximum and total hours of the page times."""
    chosen = [p for k, p in pages.items() if keys is None or k in keys]
    secs = sorted(p["seconds"] for p in chosen if not p["includes_start"])
    if not secs:
        return {"n": 0}
    return {
        "n": len(secs),
        "median_s": round(statistics.median(secs), 2),
        "p90_s": secs[math.ceil(0.9 * len(secs)) - 1],
        "max_s": secs[-1],
        "hours_all_pages": round(sum(p["seconds"] for p in chosen) / 3600, 2),
    }


def ratio_gate(arm: dict[str, Any], base: dict[str, Any], dots: bool) -> dict[str, Any]:
    """C1: median s/page at most half the baseline, on the population of the protocol."""
    if dots:
        keys = list(base["pages"])[:20]
        keys.remove("eq01:2")  # model load, not a page time
    else:
        keys = [k for k, p in base["pages"].items() if p["status"] == "ok"]
    base_speed, arm_speed = speeds(base["pages"], keys), speeds(arm["pages"], keys)
    measured = arm_speed.get("median_s")
    seen = sum(k in arm["pages"] for k in keys)
    return {
        "role": "decides",
        "rule": "median s/page <= 0.5 x baseline median on the same pages",
        "population": "20 pages that ran alone, eq01:2 excluded"
        if dots
        else "pages where P0 finished ok",
        "population_pages": len(keys),
        "arm_pages_run": seen,
        "baseline_median_s": base_speed["median_s"],
        "threshold_s": round(0.5 * base_speed["median_s"], 2),
        "measured": measured,
        "all_257_median_s": speeds(arm["pages"]).get("median_s"),
        "pass": None
        if seen < len(keys) or measured is None
        else measured <= 0.5 * base_speed["median_s"],
        "source": [arm["files"]["state"], base["files"]["state"]],
    }


def gates_for(arm: dict[str, Any], base: dict[str, Any], dots: bool, root: str) -> dict[str, Any]:
    """Return gates C1 to C7 of one arm."""
    pages = arm["pages"]
    complete = len(pages) == 257
    in_run = [k for k, p in pages.items() if p["run"] != "E-script"]
    c1 = ratio_gate(arm, base, dots)
    timeouts = sum(p["timeout"] for p in pages.values())
    rate = arm["katex"]["overall"]["error_rate"]
    recall = arm["recall"]["by_writing_system"]["ALL"]["all"].get("median")
    base_recall = base["recall"]["by_writing_system"]["ALL"]["all"]["median"]
    c4_ready = sum(p["run"] == "E-script" for p in pages.values()) == 189
    gib = round(arm["peak_bytes"] / GIB, 1)
    verdicts = run_ocr.EXP_DIR / "review_verdicts.json"
    reviewed = read_json(verdicts)["verdicts"].get(arm["arm"]) if verdicts.is_file() else None
    similarity = OUT / f"similarity_{arm['arm']}_vs_{base['arm']}.json"
    dice = read_json(similarity)["dice"]["median"] if similarity.is_file() else None
    return {
        "C1": c1,
        "C2": {
            "role": "decides",
            "rule": "0 timeouts at 300 s",
            "measured": timeouts,
            "pages_run": len(pages),
            "pass": False if timeouts else (True if complete else None),
            "source": [arm["files"]["state"]],
        },
        "C3": {
            "role": "decides",
            "rule": "KaTeX error rate <= 0.01 over E-maths + E-scan",
            "measured": rate,
            "formulas": arm["katex"]["overall"]["formulas"],
            "pass": rate <= 0.01 if rate is not None and len(in_run) == 68 else None,
            "source": [arm["files"]["katex"]],
        },
        "C4": {
            "role": "decides",
            "rule": "median E-script recall >= baseline median - 0.05 (no output scores 0)",
            "measured": recall,
            "baseline": base_recall,
            "threshold": round(base_recall - 0.05, 4),
            "pass": recall >= base_recall - 0.05 if c4_ready and recall is not None else None,
            "source": [arm["files"]["recall"], base["files"]["recall"]],
        },
        "C5": {
            "role": "decides",
            "rule": "operator finds no invented text on the review list",
            "measured": None
            if reviewed is None
            else {
                "reviewed": len(reviewed),
                "invented": sorted(k for k, v in reviewed.items() if v["verdict"] == "invented"),
            },
            "pass": None
            if reviewed is None
            else all(v["verdict"] == "clean" for v in reviewed.values()),
            "source": [f"{root}/review_verdicts.json"] if reviewed is not None else [],
        },
        "C6": {
            "role": "information only",
            "rule": "median Dice vs baseline >= 0.90",
            "measured": dice,
            "pass": None if dice is None else dice >= 0.9,
            "source": [f"output/{similarity.name}"] if dice is not None else [],
        },
        "C7": {
            "role": "information only",
            "rule": "peak memory (client + server) < 22.2 GiB for D arms; P arms report only",
            "measured_gib": gib,
            "pass": (gib < 22.2 if dots else None) if arm["peak_bytes"] else None,
            "source": [arm["files"]["state"]],
        },
    }


def reported(arm: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Return the reported-not-gated items of ``plan.json`` that the files can answer."""
    ws = arm["recall"]["by_writing_system"]
    first = [p["seconds"] for p in arm["pages"].values() if p["includes_start"]]
    similarity = OUT / f"similarity_{arm['arm']}_vs_{base['arm']}.json"
    sim = read_json(similarity) if similarity.is_file() else None
    return {
        "speed": {**speeds(arm["pages"]), "source": arm["files"]["state"]},
        "first_page_s": first,
        "peak_memory_gib": {
            "total": round(arm["peak_bytes"] / GIB, 2),
            "source": arm["files"]["state"],
        },
        "similarity": None
        if sim is None
        else {
            "median": sim["dice"]["median"],
            "share_below_0_9": sim["dice"]["share_below_0_9"],
            "lowest_20": sim["lowest_20"],
            "source": f"output/{similarity.name}",
        },
        "formulas_altered_or_missing": None
        if sim is None
        else {
            **{k: v for k, v in sim["formulas"].items() if k != "pages_with_difference"},
            "source": f"output/{similarity.name}",
        },
        "recall_by_writing_system": {
            name: {
                "all_median": row["all"].get("median"),
                "local_tier_median": row["local_tier_same_pages"].get("median"),
            }
            for name, row in ws.items()
        }
        | {"source": arm["files"]["recall"]},
        "conversion_load_crosscheck_outcome": "recorded by hand in report.md (tasks 3.1 to 3.4)",
        "p_arm_cap_hits": sum(p.get("cap_hits", 0) for p in arm["pages"].values()),
    }


def main() -> int:
    """Build ``output/summary.json``."""
    plan = run_ocr.load_plan()
    root = "experiments/41-ocr-runtimes-2026-10-30"
    views = {b: baseline_view(b) for b in run_ocr.BASELINES}
    arms: dict[str, Any] = {}
    for name in NEW_ARMS:
        if not run_ocr.state_path(name).is_file():
            continue
        view = arm_view(name)
        dots = run_ocr.ARMS[name][0] == "dots-mocr"
        base = views["D0" if dots else "P0"]
        gates = gates_for(view, base, dots, root)
        main_gates = [gates[g]["pass"] for g in ("C1", "C2", "C3", "C4", "C5")]
        arms[name] = {
            "engine": run_ocr.ARMS[name][0],
            "backend": run_ocr.ARMS[name][1],
            "baseline": base["arm"],
            "pages_run": len(view["pages"]),
            "gates": gates,
            "all_decide_gates_pass": False
            if False in main_gates
            else (True if all(main_gates) else None),
            "reported_not_gated": reported(view, base),
        }
        failed = [g for g in ("C3", "C4", "C5") if gates[g]["pass"] is False]
        if name in EIGHT_BIT:
            diagnostic = {"D2": "D1", "D4": "D3", "P2": "P1", "P4": "P3"}[name]
            arms[name]["diagnostic_trigger"] = {
                "triggered": bool(failed),
                "failed_gates": failed,
                "diagnostic_arm": diagnostic,
            }
    pairs = {}
    for gguf, mlx in (("D4", "D2"), ("P4", "P2")):
        if gguf in arms and mlx in arms:
            pairs[f"{gguf}_vs_{mlx}"] = {
                a: {
                    "median_s": arms[a]["gates"]["C1"]["all_257_median_s"],
                    "katex_error_rate": arms[a]["gates"]["C3"]["measured"],
                    "recall_median": arms[a]["gates"]["C4"]["measured"],
                    "timeouts": arms[a]["gates"]["C2"]["measured"],
                    "peak_gib": arms[a]["gates"]["C7"]["measured_gib"],
                }
                for a in (gguf, mlx)
            }
    summary = {
        "experiment_id": plan["experiment_id"],
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan_sha256": run_ocr.sha256_file(run_ocr.EXP_DIR / "plan.json"),
        "inputs_sha256": analysis.check_pinned(sorted(analysis.PINNED)),
        "baselines": {
            b: {
                "pages": len(v["pages"]),
                "speed": speeds(v["pages"]),
                "peak_gib": round(v["peak_bytes"] / GIB, 1),
                "katex_error_rate": v["katex"]["overall"]["error_rate"],
                "recall_median": v["recall"]["by_writing_system"]["ALL"]["all"]["median"],
                "source": v["files"],
            }
            for b, v in views.items()
        },
        "arms": arms,
        "matched_runtime": pairs,
        "decision": {
            a: arms[a]["all_decide_gates_pass"] if a in arms else None for a in ("D4", "P4")
        },
    }
    write_json(OUT / "summary.json", summary)
    print(f"summary.json: arms {sorted(arms) or 'none'}; decision {summary['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
