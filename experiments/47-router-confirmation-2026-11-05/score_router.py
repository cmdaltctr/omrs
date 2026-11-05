"""Steps 3 and 4: runtime checks, then the shipped document router on every page.

    uv run --no-sync python score_router.py --arm clef_router --check
    uv run --no-sync python score_router.py --arm clef_router --limit 10
    uv run --no-sync python score_router.py --arm clef_router --resume

The same commands with ``--arm jev_router`` run the optional hosted reference,
only after a dated approval in plan.json ``decision_register``.

The run calls the shipped code path and nothing else decides a page:
``page_routing.page_evidence`` (the scan), ``page_rules.pipeline.run_rules``
(every page rule in order, the ``document_router`` rule at order 40) and
``compose_decision.build_page_judge`` (the shipped ``PageJudge``, its prompt,
text head, page render, request and threshold). The settings are an injected
``EffectiveSettings`` with one decision model entry and the shipped router
template. :class:`exp47_io.RecordingJudge` only records each answer.

The checkpoint ``output/scores_<arm>.json`` is replaced after every answer,
under an exclusive lock taken before it is read.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import subprocess
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from exp47_io import (
    CORPUS,
    EXP_DIR,
    EXPERIMENTS,
    INPUTS,
    MANIFEST,
    MIN_FREE_MEMORY,
    OUTPUT,
    RecordingJudge,
    StopRules,
    atomic_json,
    check_identity,
    check_template,
    check_threshold,
    git_clean,
    hosted_approved,
    log,
    plan,
    private_path,
    read_json,
    require_check,
    sha256,
    text_sha256,
)
from label_pages import labels_frozen

# exp47_io puts experiments/ on sys.path, so _lib imports after it.
from _lib.run_safety import (  # noqa: E402
    RunStop,
    check_free_memory,
    exclusive_lock,
    start_until_ready,
    stop_child,
)

HOST, PORT = "127.0.0.1", 18447
ROUTER, ENTRY = "exp47-router", "exp47-model"
MEMORY_EVERY = 25
Server = Callable[[dict, bool], contextlib.AbstractContextManager[tuple[str, dict | None]]]


# ---------------------------------------------------------------- settings


def router_settings(current: dict, arm: str, address: str) -> Any:
    """An EffectiveSettings with one decision model entry and the shipped router template."""
    from omrs.config.settings_maps import DecisionModelEntry, DocumentRouterEntry
    from omrs.core.settings import EffectiveSettings

    spec, router = current["arms"][arm], current["router"]
    entry = {"kind": spec["kind"], "address": address, "model": spec["model"], "images": True}
    entry.update({"server": "external"} if spec["kind"] == "llamacpp" else {"key": spec["key"]})
    recipe = DocumentRouterEntry(
        model=ENTRY,
        question=router["question"],
        threshold=spec["threshold"],
        images=router["images"],
        max_chars=router["max_chars"],
        send_off_machine=spec["hosted"],
    )
    return EffectiveSettings(
        document_router=ROUTER,
        decision_models={ENTRY: DecisionModelEntry(**entry)},
        document_routers={ROUTER: recipe},
    )


# ---------------------------------------------------------------- local server


def model_paths(spec: dict) -> tuple[Path, Path, Path]:
    """llama-server binary, model file and projector file (environment, never a home path)."""
    binary = os.environ.get("EXP47_LLAMA_SERVER")
    folder = os.environ.get("EXP47_MODEL_DIR")
    if not binary or not folder:
        raise RunStop("set EXP47_LLAMA_SERVER and EXP47_MODEL_DIR (protocol section 5)")
    return Path(binary), Path(folder) / spec["model_file"], Path(folder) / spec["projector_file"]


def server_command(spec: dict, projector: bool) -> list[str]:
    """llama-server arguments from plan.json ``runtime.models[0].server_args``."""
    binary, model, mmproj = model_paths(spec)
    loaded = ["--mmproj", str(mmproj)] if projector else ["--no-mmproj"]
    return [
        str(binary),
        "-m",
        str(model),
        *loaded,
        "--host",
        HOST,
        "--port",
        str(PORT),
        "-np",
        "1",
        "-c",
        "8192",
        "-b",
        "8192",
        "-ub",
        "8192",
        "--no-webui",
        "--offline",
    ]


def healthy() -> bool:
    """True when ``GET /health`` answers 200 (loopback, no proxy)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://{HOST}:{PORT}/health", timeout=5) as response:
        return response.status == 200


@contextlib.contextmanager
def local_server(current: dict, projector: bool = True) -> Iterator[tuple[str, dict | None]]:
    """Start llama-server, check build and hashes, yield its address; always stop it."""
    from omrs.core.experiment_records.runtime_block import load_runtime_block

    from _lib.llamacpp_runtime import verify_llamacpp_runtime

    command = server_command(current["arms"]["clef_router"], projector)
    log_path = private_path("logs", "llama_server.log")
    process = start_until_ready(command, ready=healthy, log_path=log_path)
    try:
        found = verify_llamacpp_runtime(
            load_runtime_block(current), base_url=f"http://{HOST}:{PORT}"
        )
        yield f"http://{HOST}:{PORT}", {**found.as_run_record(), "pid": process.pid}
    finally:
        stop_child(process)


@contextlib.contextmanager
def hosted_endpoint(current: dict, projector: bool = True) -> Iterator[tuple[str, dict | None]]:
    """The hosted reference address; nothing to start."""
    yield current["arms"]["jev_router"]["address"], None


def live_checks(current: dict, runtime: dict) -> dict:
    """R1 build line, R2 runtime record, R3 projector hash, R6 loopback bind."""
    spec = current["arms"]["clef_router"]
    binary, _, mmproj = model_paths(spec)
    out = subprocess.run([str(binary), "--version"], capture_output=True, text=True, check=False)  # noqa: S603
    line = next((x for x in (out.stdout + out.stderr).splitlines() if "build" in x), "")
    listen = subprocess.run(  # noqa: S603
        ["/usr/sbin/lsof", "-nP", "-a", "-p", str(runtime["pid"]), "-iTCP", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    addresses = re.findall(r"TCP (\S+) \(LISTEN\)", listen)
    build = current["runtime"]["models"][0]["build"]
    return {
        "R1_build": {"value": line.strip(), "pass": f"build {build}" in line},
        "R2_runtime": {"value": {k: v for k, v in runtime.items() if k != "pid"}, "pass": True},
        "R3_projector": {
            "value": spec["projector_sha256"],
            "pass": sha256(mmproj) == spec["projector_sha256"],
        },
        "R6_bind": {
            "value": addresses,
            "pass": bool(addresses) and all(a.startswith(f"{HOST}:") for a in addresses),
        },
    }


# ---------------------------------------------------------------- shared preconditions


def preconditions(current: dict, arm: str, clean: Callable[[Path], bool]) -> None:
    """Checks every check run and every scoring run makes before any request."""
    check_threshold(current, arm, clean)
    check_template(current, EXPERIMENTS.parent)
    reasons = labels_frozen(current, clean)
    if reasons:
        raise RunStop("labels are not frozen: " + "; ".join(reasons))
    if current["arms"][arm]["hosted"] and not hosted_approved(
        current, current["arms"][arm]["provider"]
    ):
        raise RunStop(f"{arm}: no dated operator approval in decision_register; nothing was sent")


def runtime_check(
    arm: str,
    current: dict,
    *,
    server: Server,
    record: Callable[..., Any],
    transport: Any = None,
    clean: Callable[[Path], bool] = git_clean,
) -> dict:
    """R1 to R6 for the local arm, R4 for the hosted arm; write runtime_check_<arm>.json."""
    from omrs.compose_decision import reset_decision_checks, test_decision_model

    preconditions(current, arm, clean)
    local = not current["arms"][arm]["hosted"]
    checks: dict[str, Any] = {}
    with server(current, True) as (address, runtime):
        record(EXP_DIR, runtime=runtime and {k: v for k, v in runtime.items() if k != "pid"})
        if local:
            checks.update(live_checks(current, runtime))
        reset_decision_checks()
        found = test_decision_model(
            router_settings(current, arm, address), ENTRY, transport=transport
        )
        checks["R4_shipped_checks"] = {"value": found, "pass": found["status"] == "ok"}
    if local:
        with server(current, False) as (address, _):
            reset_decision_checks()
            found = test_decision_model(
                router_settings(current, arm, address), ENTRY, transport=transport
            )
            checks["R5_no_projector"] = {
                "value": found,
                "pass": found["status"] == "projector-not-loaded",
            }
    result = {
        "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "identity": check_identity(current, arm),
        "checks": checks,
        "passed": all(c["pass"] for c in checks.values()),
    }
    atomic_json(OUTPUT / f"runtime_check_{arm}.json", result)
    log(f"[check {arm}] passed={result['passed']}")
    return result


# ---------------------------------------------------------------- scoring


def score_document(doc_id: str, doc: dict, pdf: Path, ctx: dict) -> None:
    """Run the shipped page rules on one document's page range; record every answer."""
    from omrs.integrations.ocr_worker.routes import OcrRoutes
    from omrs.integrations.pdf.page_rules import document_router
    from omrs.integrations.pdf.page_rules.pipeline import run_rules

    rows = {r["page"]: r for r in doc["rows"]}
    if sha256(pdf) != doc["pdf_sha256"]:
        raise RunStop(f"{doc_id}: PDF differs from inputs.json: stop")
    evidence = [e for e in ctx["scan"](pdf) if e.page in rows]
    for entry in evidence:  # point 4: the text the router reads is the text that was labelled
        if text_sha256(entry.markdown or "") != rows[entry.page]["markdown_sha256"]:
            raise RunStop(f"{doc_id} p{entry.page}: page text differs from inputs.json: stop")
    payload, calls = ctx["payload"], []

    def on_call(call: dict) -> None:
        calls.append(call)
        payload["calls"][doc_id] = calls
        ctx["save"]()
        ctx["after_call"](call)

    judge = RecordingJudge(ctx["judge"], payload["calls"].get(doc_id, []), on_call)
    flagged = {e.page for e in evidence if e.needs_ocr}
    result = run_rules(pdf, evidence, flagged, ctx["settings"], OcrRoutes(), judge=judge)
    run = next(r for r in result.runs if r.name == "document_router")
    counts = run.outcome.state
    if judge.unused() or counts.status != document_router.STATUS_OK:
        raise RunStop(
            f"{doc_id}: router status {counts.status}, {judge.unused()} saved answers unused"
        )
    candidates = document_router._candidates(run.ctx)
    if len(candidates) != len(calls):
        raise RunStop(f"{doc_id}: {len(candidates)} pages to judge but {len(calls)} answers: stop")
    scored = []
    for entry, call in zip(candidates, calls, strict=True):
        head = (entry.markdown or "")[: ctx["judge"].max_chars]
        if call["head_sha256"] != text_sha256(head):
            raise RunStop(f"{doc_id} p{entry.page}: answer is for another text head: stop")
        if call["image_sha256"] != rows[entry.page]["png_sha256"]:
            raise RunStop(f"{doc_id} p{entry.page}: page image differs from inputs.json: stop")
        scored.append(
            {
                "doc_id": doc_id,
                "page": entry.page,
                "p_yes": call["p_yes"],
                "seconds": call["seconds"],
                "rejected": entry.page in run.outcome.add,
            }
        )
    failed = [s["page"] for s in scored if s["p_yes"] is None]
    if failed:
        payload["failures"][doc_id] = failed
    else:
        payload["failures"].pop(doc_id, None)
        payload["documents"][doc_id] = {
            "rows": scored,
            "router_counts": asdict(counts),
            "flagged": sorted(flagged),
            "claimed": sorted(run.ctx.claimed),
        }
        payload["calls"].pop(doc_id, None)
    ctx["save"]()


def run_arm(
    arm: str,
    current: dict,
    *,
    limit: int | None,
    resume: bool,
    server: Server,
    record: Callable[..., Any],
    transport: Any = None,
    scan: Any = None,
    clean: Callable[[Path], bool] = git_clean,
    corpus: Path = CORPUS,
    memory: Callable[[], Any] | None = None,
) -> dict:
    """Score every document of one arm once; checkpoint after every answer."""
    from omrs.compose_decision import build_page_judge, reset_decision_checks

    preconditions(current, arm, clean)  # point 8: every scoring run checks the threshold
    hosted = current["arms"][arm]["hosted"]
    require_check(arm, check_identity(current, arm), local=not hosted)  # point 10
    rules = StopRules.from_plan(current)
    memory = memory or (lambda: check_free_memory(MIN_FREE_MEMORY))
    files = {d["id"]: d["file"] for d in read_json(MANIFEST)["documents"]}
    inputs = read_json(INPUTS)["documents"]
    target = OUTPUT / f"scores_{arm}.json"
    with exclusive_lock(private_path("locks", f"scores_{arm}.lock")):  # point 6: before the read
        if target.exists() and not resume:
            raise RunStop(f"{target.name} exists; use --resume")
        ident = check_identity(current, arm)
        payload = (
            read_json(target)
            if target.exists()
            else {"identity": ident, "documents": {}, "calls": {}, "failures": {}}
        )
        if payload["identity"] != ident:
            raise RunStop("checkpoint identity changed; resume refused")
        todo = [d for d in inputs if d not in payload["documents"]][:limit]
        left = sum(len(inputs[d]["rows"]) for d in todo)
        rules.before_start(hosted, left)  # point 7: cost, before any request
        seconds = [r["seconds"] for d in payload["documents"].values() for r in d["rows"]]
        sent, failed = len(seconds), 0

        def save() -> None:
            atomic_json(target, payload)

        def after_call(call: dict) -> None:
            nonlocal left, sent, failed
            left -= 1
            if call.get("replayed"):
                return
            sent, failed = sent + 1, failed + (call["p_yes"] is None)
            seconds.append(call["seconds"])
            if sent % MEMORY_EVERY == 0:
                memory()
            rules.after_call(hosted, seconds, left, sent)
            rules.after_failure(failed)

        memory()
        with server(current, True) as (address, runtime):
            run_runtime = runtime and {k: v for k, v in runtime.items() if k != "pid"}
            record(EXP_DIR, runtime=run_runtime)  # point 9: before the first request
            reset_decision_checks()
            settings = router_settings(current, arm, address)
            judge = build_page_judge(settings, transport=transport)
            if judge is None or judge.status is not None:
                raise RunStop(f"the router cannot run: {judge and judge.status}")
            ctx = {
                "payload": payload,
                "save": save,
                "after_call": after_call,
                "judge": judge,
                "settings": settings,
                "scan": scan or _shipped_scan(),
            }
            for doc_id in todo:
                score_document(doc_id, inputs[doc_id], corpus / files[doc_id], ctx)
                log(f"[{arm}] {doc_id} done; {left} pages left")
    return payload


def _shipped_scan() -> Any:
    from omrs.integrations.pdf.page_routing import page_evidence

    return page_evidence


def main() -> None:
    """Run the runtime check or score one arm."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=("clef_router", "jev_router"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--limit", type=int, help="documents to score in this run (speed trial)")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    current = plan()
    from _lib.run_record import record_run_start

    server = hosted_endpoint if current["arms"][args.arm]["hosted"] else local_server
    if args.check:
        result = runtime_check(args.arm, current, server=server, record=record_run_start)
        if not result["passed"]:
            raise SystemExit(1)
        return
    run_arm(
        args.arm,
        current,
        limit=args.limit,
        resume=args.resume,
        server=server,
        record=record_run_start,
    )


if __name__ == "__main__":
    main()
