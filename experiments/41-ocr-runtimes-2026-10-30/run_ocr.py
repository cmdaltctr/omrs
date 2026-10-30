"""Experiment 41 OCR runner: one arm, one page list, one loopback model server.

The operator starts the server by hand (llama-server for D3, D4, P3, P4; mlx_vlm.server for
D1, D2, P1, P2) with the flags of the ``runtime`` block in ``plan.json``. This script is only
a client. For a GGUF arm it checks the live server against the plan before the first page.

    run_ocr.py --arm D4 --base-url http://127.0.0.1:9932 [--pages smoke] [--resume] [--dry-run]
    run_ocr.py --arm D2 --base-url http://127.0.0.1:9933 --model <mlx model> --pages E-maths
    run_ocr.py --status [--arm D4]

``--base-url`` has no default (port 9931 is the live app). ``--pages`` is ``all``, ``smoke``
(eq01:2, eq01:3) or a list name. Run every arm with
``~/.omrs/ocr-workers/engines/paddleocr-vl/.venv/bin/python`` (P arms also need
``OMRS_OCR_MODEL_CACHE``). Worktree copies of the engines go first on ``sys.path``.

D arms send one OpenAI-style chat request per page, so one client serves llama-server and
mlx_vlm.server. P arms run ``PaddleOCRVL`` with a server backend through the engine's own
``parse``. Output: ``output/<arm>/<doc>/p<NNN>.md``, ``output/ocr_state_<arm>.json``.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import io
import json
import os
import shlex
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
WORKTREE = EXP_DIR.parents[1]
OUT = EXP_DIR / "output"
EXP37 = WORKTREE.parent / "omrs-v3/experiments/37-dots-mocr-routing-acceptance-2026-09-30"
SOURCES_SHA256 = "d616b2de351d8e3307c5053f7760838c008d619a5866e1de1b7c29001b005df3"

#: arm -> (engine, backend). D1, D3, P1 and P3 are the conditional 16-bit diagnostics.
ARMS = {f"D{n}": ("dots-mocr", "mlx" if n < 3 else "llamacpp") for n in (1, 2, 3, 4)} | {
    f"P{n}": ("paddleocr-vl", "mlx" if n < 3 else "llamacpp") for n in (1, 2, 3, 4)
}
BASELINES = {"D0": "dots-mocr", "P0": "paddleocr-vl"}
SMOKE = ("eq01:2", "eq01:3")
TIMEOUT_S = 300
CHAT_PATH = "/v1/chat/completions"
P_MAX_NEW_TOKENS = 4096  # the P0 value (protocol "Token cap rule")
PEAK_INDEX = 2 + 28  # ri_lifetime_max_phys_footprint in RUSAGE_INFO_V4


def utc() -> str:
    """Return the current UTC time as an ISO string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_atomic(path: Path, text: str) -> None:
    """Write *text* through a ``.tmp`` file and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of *path*."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def page_path(arm: str, key: str) -> Path:
    """Return where the page text of *arm* lives (Experiment 37 folders for D0 and P0)."""
    doc, page = key.split(":")
    name = f"p{int(page):03d}.md"
    return (EXP37 / "output" / BASELINES[arm] if arm in BASELINES else OUT / arm) / doc / name


def state_path(arm: str) -> Path:
    """Return the state file of *arm*."""
    return OUT / f"ocr_state_{arm}.json"


def load_plan() -> dict[str, Any]:
    """Read ``plan.json``."""
    return json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))


def page_lists(plan: dict[str, Any]) -> dict[str, list[str]]:
    """Return the frozen page lists after checking their SHA-256 against the plan."""
    lists = plan["page_lists"]["lists"]
    text = json.dumps(lists, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(text.encode()).hexdigest() != plan["page_lists"]["sha256"]:
        raise SystemExit("page lists differ from the SHA-256 in plan.json")
    return lists


def select_pages(lists: dict[str, list[str]], spec: str) -> dict[str, str]:
    """Return ``{page key: list name}`` in run order for ``all``, ``smoke`` or a list name."""
    every = {key: name for name, keys in lists.items() for key in keys}
    if spec not in ("all", "smoke", *lists):
        raise SystemExit(f"--pages must be all, smoke or one of {', '.join(lists)}")
    return {
        k: v for k, v in every.items() if spec in ("all", v) or (spec == "smoke" and k in SMOKE)
    }


def resolve_pdf(path: Path) -> Path:
    """Follow a corpus symlink; map a dangling one (old project folder) onto omrs-v3."""
    target = os.readlink(path) if path.is_symlink() and not path.exists() else ""
    if "/experiments/" in target:
        return WORKTREE.parent / "omrs-v3/experiments" / target.split("/experiments/", 1)[1]
    return path


def corpus(keys: list[str]) -> dict[str, Path]:
    """Return the PDF of each document in *keys* after checking sources.json, SHA-256 and pages."""
    from pypdf import PdfReader

    if sha256_file(EXP37 / "sources.json") != SOURCES_SHA256:
        raise SystemExit("Experiment 37 sources.json changed (OI-7)")
    sources = json.loads((EXP37 / "sources.json").read_text(encoding="utf-8"))["documents"]
    last: dict[str, int] = {}
    for doc, page in (key.split(":") for key in keys):
        last[doc] = max(last.get(doc, 0), int(page))
    paths: dict[str, Path] = {}
    for doc in (d for d in sources if d["doc_id"] in last):
        path = resolve_pdf(EXP37 / doc["local_path"])
        if not path.is_file() or sha256_file(path) != doc["sha256"]:
            raise SystemExit(f"corpus file missing or changed: {path}")
        if last[doc["doc_id"]] > len(PdfReader(str(path)).pages):
            raise SystemExit(f"{doc['doc_id']}: a listed page is outside the document")
        paths[doc["doc_id"]] = path
    if last.keys() - paths.keys():
        raise SystemExit(f"documents not in sources.json: {sorted(last.keys() - paths.keys())}")
    return paths


def sh(*argv: str) -> str:
    """Run a fixed system command and return its standard output."""
    return subprocess.run(argv, capture_output=True, text=True, check=False).stdout.strip()  # noqa: S603


def server_pid(base_url: str) -> int | None:
    """Return the pid that listens on the port of *base_url*, or None."""
    port = urllib.parse.urlsplit(base_url).port
    pids = sh("/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t").split()
    return int(pids[0]) if pids else None


def peak_footprint(pid: int) -> int | None:
    """Return the lifetime peak physical footprint of *pid* in bytes (macOS), or None.

    The kernel keeps this high-water mark, Metal allocations included, so one read per page is
    enough. Experiment 37 read child processes only; the server is not a child of this script.
    """
    buf = (ctypes.c_uint64 * 48)()
    lib = ctypes.CDLL("/usr/lib/libproc.dylib")
    return int(buf[PEAK_INDEX]) if lib.proc_pid_rusage(pid, 4, ctypes.byref(buf)) == 0 else None


def sample_peaks(proc: dict[str, Any], base_url: str) -> None:
    """Update the client and server peaks (their sum is the arm's memory); stop on a new server."""
    if server_pid(base_url) != proc["server_pid"]:
        raise SystemExit(f"[stop] the server on {base_url} is not pid {proc['server_pid']} now")
    for who, pid in (("client", os.getpid()), ("server", proc["server_pid"])):
        peak = peak_footprint(pid)
        proc[f"{who}_peak_bytes"] = max(proc.get(f"{who}_peak_bytes", 0), peak or 0)


def verify_gguf(plan: dict[str, Any], arm: str, base_url: str, command: str) -> dict[str, Any]:
    """Check the live llama-server against the ``runtime`` block; return the run-record value.

    The arm's models have a ``role`` that starts with the arm id and a space (``"D4 ..."``);
    the one whose role contains ``mmproj`` is the projector. ``verify_llamacpp_runtime`` cannot
    see the mmproj, so its path and the pinned flags come from the server's command line.

    Raises:
        PreflightError: The build, a hash or a pinned flag differs from the plan.
    """
    from _lib.llamacpp_runtime import verify_llamacpp_runtime
    from _lib.preflight import PreflightError

    from omrs.core.experiment_records.record import RecordError
    from omrs.core.experiment_records.runtime_block import load_runtime_block

    # The frozen plan carries a free-text "note" on each tolerance; the schema forbids extra keys.
    runtime = {**plan["runtime"]}
    runtime["tolerance"] = [
        {k: v for k, v in t.items() if k != "note"} for t in runtime.get("tolerance", [])
    ]
    try:
        block = load_runtime_block({**plan, "runtime": runtime})
    except RecordError as exc:
        raise SystemExit(f"cannot run a GGUF arm: {exc}") from None
    mine = [m for m in block.models if m.role.startswith(arm + " ")]
    projector = [m for m in mine if "mmproj" in m.role.lower()]
    models = [m for m in mine if m not in projector]
    if len(models) != 1 or len(projector) != 1:
        raise SystemExit(f"the runtime block needs one model and one mmproj role '{arm} ...'")
    found = verify_llamacpp_runtime(block.model_copy(update={"models": models}), base_url=base_url)
    argv = shlex.split(command)
    flags = dict(zip(argv, argv[1:], strict=False))
    mmproj = flags.get("--mmproj")
    if mmproj is None or Path(mmproj).name != projector[0].file:
        raise PreflightError(f"server --mmproj is {mmproj!r}, the plan names {projector[0].file}")
    if (digest := sha256_file(Path(mmproj))) != projector[0].sha256:
        raise PreflightError(f"mmproj SHA-256: plan {projector[0].sha256}, file {digest}")
    for flag, want in models[0].server_args.items():
        if flag != "--mmproj" and flags.get(flag) != str(want):
            raise PreflightError(
                f"server flag {flag} is {flags.get(flag)!r}, the plan pins {want!r}"
            )
    found.models.append({"file": projector[0].file, "sha256": digest})
    return found.as_run_record()


class DotsClient:
    """dots.mocr through an OpenAI-style chat server (llama-server or mlx_vlm.server)."""

    packages = ("pypdfium2", "pillow")

    def __init__(self, base_url: str, model: str | None) -> None:
        from omrs_ocr_dots_mocr.engine import MAX_NEW_TOKENS, PROMPT, DotsMocrEngine
        from omrs_ocr_dots_mocr.layout import page_markdown

        self._engine, self._cap, self._prompt = DotsMocrEngine(), MAX_NEW_TOKENS, PROMPT
        self._to_markdown, self._model, self._url = page_markdown, model, base_url + CHAT_PATH

    def parse(self, pdf: Path, page: int) -> dict[str, Any]:
        """Render, ask the server, convert; a page at the token cap gives empty text."""
        buffer = io.BytesIO()
        self._engine.render_page(pdf, page).save(buffer, format="PNG")  # lossless pixels
        image = {"url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()}
        parts = [{"type": "image_url", "image_url": image}, {"type": "text", "text": self._prompt}]
        body: dict[str, Any] = {
            "messages": [{"role": "user", "content": parts}],
            "temperature": 0,
            "max_tokens": self._cap,
            "stream": False,
            **({"model": self._model} if self._model else {}),
        }
        request = urllib.request.Request(  # noqa: S310 - loopback URL, checked in main
            self._url, json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # ignore proxies
        with opener.open(request, timeout=TIMEOUT_S) as response:
            data = json.loads(response.read())
        choice, tokens = data["choices"][0], int(data["usage"]["completion_tokens"])
        text, reason = self._to_markdown(
            choice["message"].get("content") or "", hit_token_cap=tokens >= self._cap
        )
        return {
            "text": text,
            "status": "empty" if reason else "ok",
            "reason": reason,
            "completion_tokens": tokens,
            "finish_reason": choice.get("finish_reason"),
        }


class PaddleClient:
    """PaddleOCR-VL with a server backend, through the engine's own ``parse``."""

    packages = ("paddleocr", "paddlex", "pypdfium2", "pillow")

    def __init__(self, backend: str, base_url: str, model: str | None) -> None:
        cache = os.environ.get("OMRS_OCR_MODEL_CACHE", "").strip()
        if not cache or not (Path(cache).expanduser() / "paddleocr-vl").is_dir():
            raise SystemExit("set OMRS_OCR_MODEL_CACHE to a folder that holds paddleocr-vl/")
        import omrs_ocr_paddleocr_vl.engine as engine

        engine.WORKER_DIR = OUT / ".ocr-tmp"  # temporary files stay out of ocr-workers/
        engine.WORKER_DIR.mkdir(parents=True, exist_ok=True)
        engine._apply_worker_cache_env()  # before any Paddle import
        from paddleocr import PaddleOCRVL
        from paddlex.inference.models.doc_vlm.predictor import DocVLMGenAIClientPredictor

        self._block_tokens: list[int] = []
        original = DocVLMGenAIClientPredictor._doc_vlm_genai_collect_responses

        def collect(this: Any, futures: Any) -> Any:
            # PaddleX drops the usage of each block request. Read it, then hand over.
            for future in futures:
                usage = getattr(future.result(), "usage", None)
                if usage is not None and usage.completion_tokens is not None:
                    self._block_tokens.append(int(usage.completion_tokens))
            return original(this, futures)

        DocVLMGenAIClientPredictor._doc_vlm_genai_collect_responses = collect
        # P0 settings (engine.py line 90) plus the server backend: only the VL step changes.
        pipeline = PaddleOCRVL(
            pipeline_version="v1.6",
            device="cpu",
            use_ocr_for_image_block=True,
            format_block_content=True,
            vl_rec_backend={"llamacpp": "llama-cpp-server", "mlx": "mlx-vlm-server"}[backend],
            vl_rec_server_url=base_url + "/v1",
            vl_rec_api_model_name=model,
        )
        predict = pipeline.predict
        pipeline.predict = lambda **kw: predict(
            temperature=0, max_new_tokens=P_MAX_NEW_TOKENS, **kw
        )
        # Hand the engine our pipeline through its singleton; its page-subset code runs as is.
        engine._PIPELINE_SINGLETON = pipeline
        self._engine = engine.ENGINE

    def parse(self, pdf: Path, page: int) -> dict[str, Any]:
        """Parse one page; a page that finishes after the request timeout counts as a timeout."""
        self._block_tokens.clear()
        started = time.perf_counter()
        text = self._engine.parse(pdf, [page])[0]
        if time.perf_counter() - started > TIMEOUT_S:
            raise TimeoutError(f"page finished after {TIMEOUT_S} s")
        tokens = list(self._block_tokens)
        return {
            "text": text,
            "status": "ok" if text.strip() else "empty",
            "reason": None if text.strip() else "no_text",
            "blocks": len(tokens),
            "cap_hits": sum(t >= P_MAX_NEW_TOKENS for t in tokens),
            "completion_tokens": sum(tokens),
        }


def run_one(client: DotsClient | PaddleClient, pdf: Path, key: str, out: Path) -> dict[str, Any]:
    """Run one page and return its state entry (without time and run name)."""
    try:
        result = client.parse(pdf, int(key.split(":")[1]))
        write_atomic(out, result.pop("text"))
        return {"status": result.pop("status"), "timeout": False, **result}
    except TimeoutError:
        return {"status": "timeout", "timeout": True}
    except urllib.error.URLError as exc:
        late = isinstance(exc.reason, TimeoutError)
        return {"status": "timeout" if late else "error", "timeout": late, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001 - any page failure is a result, not a crash
        return {"status": "error", "timeout": False, "message": f"{type(exc).__name__}: {exc}"}


def run_pages(args: argparse.Namespace, plan: dict[str, Any], pages: dict[str, str]) -> int:
    """Check the server, then run the pages that have no result yet."""
    engine, base_url, path = ARMS[args.arm][0], args.base_url, state_path(args.arm)
    if path.is_file() and not args.resume:
        print(f"{path.name} exists: pass --resume to continue", file=sys.stderr)
        return 1
    if (pid := server_pid(base_url)) is None:
        print(f"nothing listens on {base_url}", file=sys.stderr)
        return 1
    runtime, command = None, sh("/bin/ps", "-o", "command=", "-p", str(pid))
    if args.backend == "llamacpp":
        from _lib.preflight import PreflightError

        try:
            runtime = verify_gguf(plan, args.arm, base_url, command)
        except PreflightError as exc:
            print(f"RUNTIME CHECK FAILED, no page written: {exc}", file=sys.stderr)
            return 3
    elif not args.model:
        print("--model is required for the mlx backend", file=sys.stderr)
        return 1
    os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    paths = corpus(list(pages))
    client: DotsClient | PaddleClient = (
        DotsClient(base_url, args.model)
        if engine == "dots-mocr"
        else PaddleClient(args.backend, base_url, args.model)
    )
    from _lib.run_record import record_run_start

    record_run_start(EXP_DIR, runtime=runtime)
    state: dict[str, Any] = {"arm": args.arm, "engine": engine, "backend": args.backend}
    state.update(json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"pages": {}})
    proc = {
        "started_utc": utc(),
        "base_url": base_url,
        "server_pid": pid,
        "server_started": sh("/bin/ps", "-o", "lstart=", "-p", str(pid)),
        "server_command": command,
        "client_packages": {n: metadata.version(n) for n in client.packages},
    }
    state.setdefault("processes", []).append(proc)
    state.update(pid=os.getpid(), finished_utc=None, current=None)

    def save() -> None:
        state["heartbeat_utc"] = utc()
        write_atomic(path, json.dumps(state, indent=1, ensure_ascii=False) + "\n")

    def on_signal(signum: int, _frame: Any) -> None:
        raise SystemExit(f"stopped by signal {signum}")

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGHUP, on_signal)
    first = True
    try:
        for key, run in pages.items():
            out, prior = page_path(args.arm, key), state["pages"].get(key)
            if prior and (prior["status"] in ("timeout", "error") or out.is_file()):
                continue
            state["current"] = {"page": key, "since_utc": utc()}
            save()
            started = time.perf_counter()
            entry = run_one(client, paths[key.split(":")[0]], key, out)
            if entry["status"] == "error" and server_pid(base_url) != pid:
                raise SystemExit(f"[stop] the server on {base_url} is gone after {key}")
            seconds = round(time.perf_counter() - started, 2)
            stamp = {"run": run, "seconds": seconds, "includes_start": first, "utc": utc()}
            state["pages"][key] = {**entry, **stamp}
            first = False
            sample_peaks(proc, base_url)
            save()
            print(f"[{args.arm}] {key} {entry['status']} {seconds} s", flush=True)
        state["finished_utc"] = utc()
    finally:
        state.update(current=None, pid=None)
        save()
    return 0


def print_status(arm: str | None) -> int:
    """Print the progress of one arm, or of every arm that has a state file."""
    names = [arm] if arm else [a for a in ARMS if state_path(a).is_file()]
    for name in names:
        if not state_path(name).is_file():
            print(f"{name}: nothing has run")
            continue
        state = json.loads(state_path(name).read_text(encoding="utf-8"))
        pages = state["pages"]
        count = Counter(p["status"] for p in pages.values())
        timed = [p["seconds"] for p in pages.values() if not p["includes_start"]]
        last = max(pages.items(), key=lambda item: item[1]["utc"], default=("none", {}))
        print(
            f"{name}: pages {len(pages)}, ok {count['ok']}, empty {count['empty']}, "
            f"timeouts {count['timeout']}, errors {count['error']}, "
            f"median {round(statistics.median(timed), 2) if timed else None} s/page, "
            f"last {last[0]} {last[1].get('seconds')} s, "
            f"{'running' if state.get('pid') else 'not running'}"
        )
    if not names:
        print("no state files yet: nothing has run")
    return 0


def parse_args() -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--arm", choices=sorted(ARMS))
    parser.add_argument("--backend", choices=("mlx", "llamacpp"))
    parser.add_argument("--pages", default="all")
    parser.add_argument("--base-url", help="loopback server address (no default)")
    parser.add_argument("--model", help="model name in the request (required for mlx)")
    parser.add_argument("--resume", action="store_true", help="keep the pages already done")
    parser.add_argument("--dry-run", action="store_true", help="check inputs, call no model")
    parser.add_argument("--status", action="store_true", help="show progress and exit")
    return parser.parse_args()


def main() -> int:
    """Run, dry-run or report the status of one arm."""
    for sub in ("src", "experiments", "ocr-workers/core/src", "ocr-workers/engines/dots-mocr/src"):
        sys.path.insert(0, str(WORKTREE / sub))
    sys.path.insert(0, str(WORKTREE / "ocr-workers/engines/paddleocr-vl/src"))
    args = parse_args()
    if args.status:
        return print_status(args.arm)
    if not args.arm or args.backend not in (None, ARMS[args.arm][1]):
        print("--arm is required and --backend must match the arm", file=sys.stderr)
        return 1
    args.backend = ARMS[args.arm][1]
    plan = load_plan()
    lists = page_lists(plan)
    pages = select_pages(lists, args.pages)
    paths = corpus(list(pages))
    if args.dry_run:
        counts = ", ".join(f"{n} {sum(p == n for p in pages.values())}" for n in lists)
        print(f"{args.arm}: {len(pages)} pages ({counts}); page lists, {len(paths)} PDFs verified")
        print("dry run: no model called, no server contacted, nothing written")
        return 0
    if not args.base_url:
        print("--base-url is required (there is no default)", file=sys.stderr)
        return 1
    parts = urllib.parse.urlsplit(args.base_url)
    if parts.hostname not in ("127.0.0.1", "localhost", "::1") or not parts.port:
        print(f"--base-url must be loopback with a port: {args.base_url}", file=sys.stderr)
        return 1
    args.base_url = args.base_url.rstrip("/")
    return run_pages(args, plan, pages)


if __name__ == "__main__":
    sys.exit(main())
