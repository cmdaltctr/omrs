"""Tasks 2.1, 3.2, 3.3 and 3.5: runtime checks, smoke test and page scoring.

    uv run --no-sync python score_pages.py --arm clef_image --check
    uv run --no-sync python score_pages.py --arm clef_image --phase fit --limit 40
    uv run --no-sync python score_pages.py --arm clef_image --phase fit --resume
    uv run --no-sync python score_pages.py --arm clef_image --phase rest --resume

The same commands with ``--arm jev_image`` run the hosted control. Each page is scored
once; the checkpoint ``output/scores_<arm>.json`` is replaced atomically after each page.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clients import HostedClient, LocalClient, ModelIdGuard, placeholder, post
from exp43_io import (
    EXP_DIR,
    EXPERIMENTS,
    JUNK_DOCS,
    OUTPUT,
    RENDERS,
    TEXTS,
    atomic_json,
    check_memory,
    git_clean,
    hosted_approved,
    log,
    plan,
    read_json,
    sha256,
)

ARMS = ("clef_image", "jev_image")
MODEL_DIR = Path.home() / "Development" / "DATA" / "omrs" / "ocr-models" / "clef-flash"
MODEL = MODEL_DIR / "Clef-Flash-Q8_0.gguf"
MMPROJ = MODEL_DIR / "mmproj-Clef-Flash-Q8_0.gguf"
BINARY = Path(
    os.environ.get(
        "EXP43_LLAMA_SERVER",
        EXPERIMENTS.parent.parent
        / "omrs-feat-dots-mocr-llamacpp-backend/ocr-workers/engines/dots-mocr-llamacpp"
        / ".model-cache/llama.cpp/llama-server",
    )
)
HOST, PORT = "127.0.0.1", 18443
BASE_URL = f"http://{HOST}:{PORT}"
BUILD = 11941
SMOKE_RIGHT, SMOKE_WRONG, SMOKE_MARGIN = ("bd01", 2), ("bd02", 2), 0.2
MAX_FAILURES = 10
MEMORY_EVERY = 25


# ---------------------------------------------------------------- pages


def page_text(doc_id: str, page: int, cache: dict) -> str:
    """Return the saved LiteParse text of one page."""
    if doc_id not in cache:
        cache[doc_id] = read_json(TEXTS / doc_id / "liteparse.json")
    return cache[doc_id][page - 1]


def page_png(row: dict) -> bytes:
    """Return the rendered PNG of one page after checking its hash."""
    path = RENDERS / row["doc_id"] / f"p{row['page']:03d}.png"
    data = path.read_bytes()
    import hashlib

    if hashlib.sha256(data).hexdigest() != row["png_sha256"]:
        raise SystemExit(f"render changed since prepare_inputs: {path.name}")
    return data


def population(rows: list[dict], phase: str) -> list[dict]:
    """Fit: healthy pages outside rf06 and rf07. Rest: every other page with text."""
    fit = [r for r in rows if r["class"] == "healthy" and r["doc_id"] not in JUNK_DOCS]
    if phase == "fit":
        return fit
    fit_keys = {(r["doc_id"], r["page"]) for r in fit}
    return [r for r in rows if r["scored"] and (r["doc_id"], r["page"]) not in fit_keys]


# ---------------------------------------------------------------- local server


def server_command(mmproj: Path | None) -> list[str]:
    """llama-server arguments from plan.json runtime.models[0].server_args."""
    projector = ["--mmproj", str(mmproj)] if mmproj else ["--no-mmproj"]
    return [
        str(BINARY), "-m", str(MODEL), *projector, "--host", HOST, "--port", str(PORT),
        "-np", "1", "-c", "8192", "-b", "8192", "-ub", "8192", "--no-webui", "--offline",
    ]  # fmt: skip


def check_projector(command: list[str], expected_sha256: str) -> dict:
    """R3: the command must load the planned projector file, with the planned hash."""
    if "--mmproj" not in command:
        raise SystemExit("server started without the projector file (--mmproj): stop")
    path = Path(command[command.index("--mmproj") + 1])
    digest = sha256(path)
    if digest != expected_sha256:
        raise SystemExit(f"projector SHA-256 differs from plan: {digest}")
    return {"file": path.name, "sha256": digest, "pass": True}


def start_server(command: list[str], log_path: Path) -> subprocess.Popen:
    """Start llama-server and wait until /health answers."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab")
    process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)  # noqa: S603
    deadline = time.monotonic() + 600
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"llama-server exited with code {process.returncode}")
        try:
            with opener.open(f"{BASE_URL}/health", timeout=5) as response:
                if response.status == 200:
                    return process
        except OSError:
            pass
        time.sleep(2)
    stop_server(process)
    raise SystemExit("llama-server did not become healthy in 600 s")


def stop_server(process: subprocess.Popen) -> None:
    """Stop the server."""
    process.terminate()
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()


def listen_addresses(pid: int) -> list[str]:
    """R6: the TCP listen addresses of the server process."""
    out = subprocess.run(  # noqa: S603
        ["/usr/sbin/lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return re.findall(r"TCP (\S+) \(LISTEN\)", out)


def version_line() -> str:
    """R1: the llama-server --version line."""
    out = subprocess.run([str(BINARY), "--version"], capture_output=True, text=True, check=False)  # noqa: S603
    return next((x for x in (out.stdout + out.stderr).splitlines() if "build" in x), "").strip()


def live_checks(current: dict, process: subprocess.Popen, command: list[str]) -> tuple[dict, Any]:
    """R1, R2, R3 and R6 on the running server."""
    sys.path.insert(0, str(EXPERIMENTS))
    from _lib.llamacpp_runtime import verify_llamacpp_runtime

    from omrs.core.experiment_records.runtime_block import load_runtime_block

    line = version_line()
    if f"build {BUILD}" not in line:
        raise SystemExit(f"llama-server is not build {BUILD}: {line}")
    found = verify_llamacpp_runtime(load_runtime_block(current), base_url=BASE_URL)
    frozen = next(f for f in current["frozen"] if "mmproj" in f["item"])
    addresses = listen_addresses(process.pid)
    if not addresses or not all(a.startswith(f"{HOST}:") for a in addresses):
        raise SystemExit(f"server listens beyond loopback: {addresses}")
    checks = {
        "R1_build": {"value": line, "pass": True},
        "R2_runtime": {"value": found.as_run_record(), "pass": True},
        "R3_projector": check_projector(command, frozen["sha256"]),
        "R6_bind": {"value": addresses, "pass": True},
    }
    return checks, found


# ---------------------------------------------------------------- scoring


def make_scorer(arm: str, current: dict) -> Any:
    """Return score(row, text, png) -> dict for one arm."""
    question = current["request"]["question"]
    if arm == "clef_image":
        client = LocalClient(BASE_URL, question)
        return lambda row, text, png: client.score(text, png)
    if not hosted_approved(current):
        raise SystemExit("no dated operator approval for TypeSafe in plan.json: not run")
    client = HostedClient(question, current["arms"]["jev_image"]["model"], send=post)
    return lambda row, text, png: client.score(text, png, placeholder(row["doc_id"], row["page"]))


def smoke(score: Any, rows: list[dict]) -> dict:
    """R4: right text must score above wrong text by the planned margin."""
    by_key = {(r["doc_id"], r["page"]): r for r in rows}
    target = by_key[SMOKE_RIGHT]
    cache: dict = {}
    png = page_png(target)
    right = score(target, page_text(*SMOKE_RIGHT, cache), png)
    wrong = score(target, page_text(*SMOKE_WRONG, cache), png)
    passed = right["p_yes"] - wrong["p_yes"] >= SMOKE_MARGIN
    result = {"page": "bd01 p2", "right": right, "wrong": wrong, "margin": SMOKE_MARGIN, "pass": passed}
    if not passed:
        raise SystemExit(f"smoke test failed: right {right['p_yes']:.4f}, wrong {wrong['p_yes']:.4f}")
    return result


def identity(arm: str, current: dict) -> dict:
    """Bind resume to the question, inputs and model of the arm."""
    model = (
        current["runtime"]["models"][0]["sha256"]
        if arm == "clef_image"
        else current["arms"]["jev_image"]["model"]
    )
    return {
        "arm": arm,
        "question": current["request"]["question"],
        "text_head_chars": current["request"]["text_head_chars"],
        "inputs_sha256": sha256(OUTPUT / "inputs.json"),
        "model": model,
    }


def unscored_failures(payload: dict) -> set[tuple[str, int]]:
    """Pages that failed and still have no score (amendment A2: a resume retries them)."""
    scored = {(r["doc_id"], r["page"]) for r in payload["rows"]}
    return {(f["doc_id"], f["page"]) for f in payload["failures"]} - scored


def run_pages(arm: str, phase: str, score: Any, current: dict, limit: int | None, resume: bool) -> dict:
    """Score the phase population once per page, checkpointing after each."""
    rows = read_json(OUTPUT / "inputs.json")["rows"]
    pages = population(rows, phase)
    if phase == "fit" and any(r["doc_id"] in JUNK_DOCS or r["class"] != "healthy" for r in pages):
        raise AssertionError("fit population holds a junk or rf06/rf07 page")
    if phase == "rest":
        threshold = current["thresholds"][arm]["value"]
        if threshold is None or not git_clean(EXP_DIR / "plan.json"):
            raise SystemExit(f"commit the {arm} threshold in plan.json before phase rest")
    target = OUTPUT / f"scores_{arm}.json"
    ident = identity(arm, current)
    if target.exists() and not resume:
        raise SystemExit(f"{target.name} exists; use --resume")
    payload = read_json(target) if target.exists() else {"identity": ident, "rows": [], "failures": []}
    if payload["identity"] != ident:
        raise SystemExit("checkpoint identity changed; resume refused")
    done = {(r["doc_id"], r["page"]) for r in payload["rows"]}
    guard = ModelIdGuard(payload["rows"][0]["model"] if payload["rows"] else None)
    cache: dict = {}
    new = 0
    for row in pages:
        key = (row["doc_id"], row["page"])
        if key in done:
            continue
        if limit is not None and new >= limit:
            break
        if new % MEMORY_EVERY == 0:
            check_memory()
        try:
            result = score(row, page_text(*key, cache), page_png(row))
        except (RuntimeError, ValueError, KeyError) as error:
            message = str(error)
            if arm == "jev_image" and re.match(r"HTTP (400|401|403|422)", message):
                raise SystemExit(f"hosted API refused the request: {message}") from None
            payload["failures"].append({"doc_id": key[0], "page": key[1], "error": message[:200]})
            atomic_json(target, payload)
            log(f"[{arm}] failure {key[0]} p{key[1]}: {message[:120]}")
            if len(unscored_failures(payload)) > MAX_FAILURES:
                raise SystemExit(f"more than {MAX_FAILURES} failed pages: stop (INCONCLUSIVE)") from None
            continue
        guard.check(result["model"])
        payload["rows"].append({"doc_id": key[0], "page": key[1], "phase": phase, **result})
        atomic_json(target, payload)
        new += 1
        log(f"[{arm} {phase}] {key[0]} p{key[1]}: P(yes)={result['p_yes']:.4f} {result['seconds']:.1f}s")
    scored = {(r["doc_id"], r["page"]) for r in payload["rows"]}
    remaining = [r for r in population(rows, "fit") + population(rows, "rest")
                 if (r["doc_id"], r["page"]) not in scored]  # fmt: skip
    mine = [r for r in payload["rows"] if r["phase"] == phase][-max(new, 1):]
    mean = sum(r["seconds"] for r in mine) / len(mine) if mine else 0.0
    estimate = {"new_pages": new, "mean_seconds": mean, "remaining_pages": len(remaining),
                "remaining_hours": mean * len(remaining) / 3600}  # fmt: skip
    tokens = [r["input_tokens"] for r in mine if r.get("input_tokens")]
    if tokens:
        total_pages = len(scored) + len(remaining)
        estimate["mean_input_tokens"] = sum(tokens) / len(tokens)
        estimate["projected_usd_all_pages"] = estimate["mean_input_tokens"] * total_pages * 42e-9
    log(f"[{arm} {phase}] estimate: {estimate}")
    return estimate


def no_projector_check(current: dict) -> dict:
    """R5: without the projector the image request fails and the runner stops."""
    command = server_command(None)
    try:
        check_projector(command, "")
        raise AssertionError("runner accepted a server without the projector")
    except SystemExit as stop:
        runner_stop = str(stop)
    process = start_server(command, OUTPUT / ".logs" / "llama_no_mmproj.log")
    try:
        client = LocalClient(BASE_URL, current["request"]["question"])
        rows = {(r["doc_id"], r["page"]): r for r in read_json(OUTPUT / "inputs.json")["rows"]}
        target = rows[SMOKE_RIGHT]
        try:
            reply = client.score(page_text(*SMOKE_RIGHT, {}), page_png(target))
            server = {"error": None, "unexpected_score": reply["p_yes"]}
        except RuntimeError as error:
            server = {"error": str(error)[:300]}
    finally:
        stop_server(process)
    return {"runner_stop": runner_stop, "server": server, "pass": server.get("error") is not None}


def main() -> None:
    """Parse arguments and run one check or scoring phase."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--phase", choices=("fit", "rest"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    current = plan()
    sys.path.insert(0, str(EXPERIMENTS))
    from _lib.run_record import record_run_start

    rows = read_json(OUTPUT / "inputs.json")["rows"]
    process = None
    checks: dict = {"utc": datetime.now(UTC).isoformat(timespec="seconds"), "arm": args.arm}
    runtime = None
    try:
        if args.arm == "clef_image":
            command = server_command(MMPROJ)
            process = start_server(command, OUTPUT / ".logs" / "llama_server.log")
            live, found = live_checks(current, process, command)
            checks.update(live)
            runtime = found.as_run_record()
        score = make_scorer(args.arm, current)
        checks["R4_smoke"] = smoke(score, rows)
        if not args.check:
            record_run_start(EXP_DIR, runtime=runtime)
            checks["estimate"] = run_pages(args.arm, args.phase, score, current, args.limit, args.resume)
    finally:
        if process is not None:
            stop_server(process)
    if args.check:
        if args.arm == "clef_image":
            checks["R5_no_projector"] = no_projector_check(current)
        checks["passed"] = all(v.get("pass", True) for v in checks.values() if isinstance(v, dict))
        atomic_json(OUTPUT / f"runtime_check_{args.arm}.json", checks)
        log(f"[check {args.arm}] passed={checks['passed']}")
        if not checks["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
