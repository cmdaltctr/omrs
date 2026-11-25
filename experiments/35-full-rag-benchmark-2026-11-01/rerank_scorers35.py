"""The two scorers of the reranker rank check ``rerank_check35.py`` (task 15.10, G12).

* llama.cpp: one ``POST /v1/rerank`` per pair. :func:`managed_router` starts
  OMRS's managed router with the candidate file only (Experiment 48's
  ``router_config.start_router``, as ``live35.py`` does), holds one model
  session while the pairs are scored (the lease's idle stop cannot stop the
  router mid-check), and stops the router on exit. :func:`external_router`
  reuses a server that already runs and leaves it running.
* Reference: the transformers recipe of the Qwen3-Reranker model card, one
  pair at a time: the probability of "yes" against "no" at the last position,
  with the card's default instruction. It runs in its own environment (the
  ``torch`` extra), on the GPU in bfloat16. ``torch`` and ``transformers`` are
  imported inside the functions only, so importing this module never imports
  them.
* :func:`server_live` tells whether a llama.cpp server answers at a URL. The
  reference refuses to start while one does: an 8B reference in bfloat16
  (about 16 GB) and an 8B llama.cpp server (about 9 to 12 GB) need more than
  the 24 GB of an RTX 4090.

:func:`run_llamacpp` and :func:`run_reference` are the two run steps behind
the ``llamacpp`` and ``reference`` commands: refusals first, then the
pre-freeze run record (task 16.35), then the scores with both times.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experiments._lib import run_guard
from experiments._lib.run_record import record_run_start

from omrs.core.experiment_records.runtime_block import RuntimeBlock

EXP_DIR = Path(__file__).resolve().parent
EXP48_DIR = EXP_DIR.parent / "48-pipeline-sweep-llamacpp-2026-11-01"
_TIMEOUT_SECONDS = 600.0
_PROBE_SECONDS = 2.0
_SIZE = re.compile(r"reranker-(\d+(?:\.\d+)?)b", re.IGNORECASE)

#: The transformers recipe of the Qwen3-Reranker model card (default instruction).
INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"
PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the "
    'Query and the Instruct provided. Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n<|im_start|>user\n"
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
MAX_LENGTH = 8192
#: Sizes the reference refuses on the CPU (G12: hours; 8B in float32 exceeds the pod memory).
CPU_REFUSED = ("4b", "8b")

Pair = Mapping[str, str]


class CheckRefused(ValueError):
    """The check cannot start or cannot compare; nothing is scored or written."""


def write_json(path: Path, data: Any) -> None:
    """Write *data* as sorted, indented JSON to *path* through a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def model_size(name: str) -> str:
    """Return the size (``0.6b``, ``4b`` or ``8b``) in a reranker model id or file name.

    Raises:
        ValueError: The name holds no ``Reranker-<size>B`` part.
    """
    found = _SIZE.search(name)
    if found is None:
        raise ValueError(f"cannot read the reranker size from {name!r}")
    return f"{found.group(1)}b"


# --- llama.cpp ---------------------------------------------------------------------


def post_json(url: str, body: Mapping[str, Any]) -> Any:
    """POST *body* as JSON to *url* and return the parsed reply."""
    # The URL is the loopback router address that guard_run has already checked.
    request = urllib.request.Request(  # noqa: S310
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read())


def llamacpp_scores(
    pairs: Sequence[Pair],
    *,
    base_url: str,
    model: str,
    post: Callable[[str, Mapping[str, Any]], Any] = post_json,
) -> list[float]:
    """Score each pair with one ``POST /v1/rerank`` holding that one passage.

    Returns:
        The ``relevance_score`` of each pair, in pair order, unchanged.
    """
    url = base_url.rstrip("/") + "/v1/rerank"
    scores = []
    for pair in pairs:
        reply = post(url, {"model": model, "query": pair["query"], "documents": [pair["passage"]]})
        scores.append(float(reply["results"][0]["relevance_score"]))
    return scores


@contextmanager
def external_router(base_url: str, model: str) -> Iterator[tuple[str, str]]:
    """Yield ``(base URL, request name)`` of a server that already runs; leave it running."""
    yield base_url.rstrip("/").removesuffix("/v1"), model


@contextmanager
def managed_router(entry: Mapping[str, Any], work: Path) -> Iterator[tuple[str, str]]:
    """Start OMRS's managed router with *entry* only; yield ``(base URL, request name)``.

    The scratch ``omrs.jsonc`` and the router state (``server.log``) go under
    *work*. The GGUF file comes from ``$SWEEP_GGUF_DIR``. The router stops when
    the block ends, also on an error.

    Raises:
        RouterConfigError: The file is missing, OMRS refuses the preset, or an
            environment value overrides the scratch file.
    """
    from experiments._lib import router_env

    if str(EXP48_DIR) not in sys.path:
        sys.path.insert(0, str(EXP48_DIR))
    import router_config

    plan = {"runtime": {"models": [dict(entry)]}}
    config_dir = work / "config"
    router_env.prepare_environment({}, config_dir=config_dir, state_dir=work / "state")
    values = {
        "local_backend": "llamacpp",
        "llamacpp_router_server": "managed",
        "llamacpp_router_url": router_env.ROUTER_URL,
        "llamacpp_router_models_max": 1,
        "llamacpp_models": router_env.model_entries(plan, router_env.gguf_dir()),
    }
    router_env.write_settings(values, config_dir)
    router_env.check_settings_file(config_dir)
    router_env.check_resolved(router_env.load_settings(), values)
    router = router_config.start_router([entry["file"]], plan)
    try:
        with router_config.held(router, plan, entry["file"]) as name:
            yield router_env.ROUTER_URL.removesuffix("/v1"), name
    finally:
        router.leave()


def server_live(base_url: str, *, opener: Callable[..., Any] = urllib.request.urlopen) -> bool:
    """Return True when any HTTP server answers ``GET <base_url>/health``.

    An HTTP error status (for example 503 while a model loads) counts as live.
    A refused connection or a time-out counts as down.
    """
    try:
        with opener(f"{base_url.rstrip('/')}/health", timeout=_PROBE_SECONDS):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


# --- reference ---------------------------------------------------------------------


def reference_text(query: str, passage: str) -> str:
    """Return the model card's user text for one pair, with the default instruction."""
    return f"<Instruct>: {INSTRUCTION}\n<Query>: {query}\n<Document>: {passage}"


def cuda_device() -> str | None:
    """Return the name of CUDA device 0, or None when torch sees no CUDA device."""
    import torch

    return str(torch.cuda.get_device_name(0)) if torch.cuda.is_available() else None


def transformers_scores(
    pairs: Sequence[Pair], *, model_id: str, revision: str, device: str
) -> tuple[list[float], dict[str, Any]]:
    """Score each pair with the transformers recipe of the Qwen3-Reranker model card.

    As the card: the prefix and suffix tokens around the tokenised user text
    (truncated to 8,192 tokens in all), then the log-softmax of the "no" and
    "yes" logits at the last position. bfloat16 on CUDA, float32 on the CPU.
    The two logits are cast to float32 before the log-softmax, so bfloat16
    rounding of the softmax adds no ties.

    Returns:
        The probability of "yes" per pair, in pair order, and the run facts
        (``device``, ``dtype``, ``torch`` and ``transformers`` versions).
    """
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision, dtype=dtype)
    model = model.to(device).eval()
    yes, no = tokenizer.convert_tokens_to_ids("yes"), tokenizer.convert_tokens_to_ids("no")
    prefix = tokenizer.encode(PREFIX, add_special_tokens=False)
    suffix = tokenizer.encode(SUFFIX, add_special_tokens=False)
    room = MAX_LENGTH - len(prefix) - len(suffix)
    scores = []
    with torch.no_grad():
        for pair in pairs:
            body = tokenizer(
                reference_text(pair["query"], pair["passage"]),
                padding=False,
                truncation="longest_first",
                return_attention_mask=False,
                max_length=room,
            )["input_ids"]
            ids = torch.tensor([prefix + body + suffix], device=device)
            logits = model(input_ids=ids, logits_to_keep=1).logits[0, -1]
            two = torch.stack([logits[no], logits[yes]]).float()
            scores.append(float(torch.log_softmax(two, dim=0)[1].exp()))
    info = {
        "device": device,
        "dtype": str(dtype).removeprefix("torch."),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
    }
    return scores, info


# --- the two run steps -------------------------------------------------------------


def candidate_block(entry: Mapping[str, Any]) -> RuntimeBlock:
    """Return a runtime block that holds the one candidate reranker file."""
    tolerance = [{"metric": "spearman", "max_abs_change": 0.0}]
    return RuntimeBlock.model_validate({"models": [dict(entry)], "tolerance": tolerance})


def _rows(pairs: Sequence[Pair], scores: Sequence[float]) -> list[dict[str, Any]]:
    return [{"pair_id": p["pair_id"], "score": s} for p, s in zip(pairs, scores, strict=True)]


def run_llamacpp(
    folder: Path,
    entry: Mapping[str, Any],
    pairs: Sequence[Pair],
    *,
    out: Path,
    router: AbstractContextManager[tuple[str, str]],
    kind: str,
    pairs_sha256: str,
    score: Callable[..., list[float]] = llamacpp_scores,
    guard: Callable[..., Any] = run_guard.guard_run,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    command: str | None = None,
) -> dict[str, Any]:
    """Enter *router*, guard the run as a pre-freeze run, score every pair, write the file.

    Raises:
        PreflightError: The server does not serve the planned file, hash or
            server arguments. Nothing is scored and nothing is written.
    """
    block = candidate_block(entry)
    started = now()
    with router as (base_url, model):
        found = guard(
            folder, block, base_url=base_url, command=command, check_args=True, prefreeze=True
        )
        scores = score(pairs, base_url=base_url, model=model)
    result = {
        "side": "llamacpp",
        **{key: entry[key] for key in ("role", "repository", "file")},
        "sha256": found.models[0]["sha256"],
        "build": found.build,
        "server_args": dict(entry.get("server_args") or {}),
        "router": kind,
        "base_url": base_url,
        "model": model,
        "pairs_sha256": pairs_sha256,
        "started_at": started.isoformat(),
        "finished_at": now().isoformat(),
        "scores": _rows(pairs, scores),
    }
    write_json(out / f"{entry['file']}.llamacpp.json", result)
    return result


def run_reference(
    folder: Path,
    pairs: Sequence[Pair],
    *,
    model_id: str,
    revision: str,
    out: Path,
    server_url: str,
    pairs_sha256: str,
    live: Callable[[str], bool],
    device: Callable[[], str | None],
    score: Callable[..., tuple[list[float], dict[str, Any]]],
    allow_cpu: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    command: str | None = None,
) -> dict[str, Any]:
    """Refuse while a server answers, or 4B and 8B on the CPU; else record the run and score.

    Raises:
        CheckRefused: A server answers at *server_url*, or there is no CUDA
            device for a 4B or 8B model and no *allow_cpu*. Nothing is written.
    """
    if live(server_url):
        raise CheckRefused(
            f"a server answers at {server_url}; stop it first: an 8B reference in bfloat16 "
            "and an 8B llama.cpp server need more than 24 GB together"
        )
    size = model_size(model_id)
    gpu = device()
    if gpu is None and size in CPU_REFUSED and not allow_cpu:
        raise CheckRefused(
            f"no CUDA device: {model_id} on the CPU takes hours, and 8B in float32 exceeds "
            "the pod memory; run it on the GPU, or pass --allow-cpu"
        )
    started = now()
    prereg = folder / run_guard.PREREGISTRATION
    sha = hashlib.sha256(prereg.read_bytes()).hexdigest() if prereg.is_file() else None
    record_run_start(folder, command=command, prefreeze=True, preregistration_sha256=sha)
    where = "cuda" if gpu else "cpu"
    scores, info = score(pairs, model_id=model_id, revision=revision, device=where)
    result = {
        "side": "reference",
        "hf_model": model_id,
        "hf_revision": revision,
        "size": size,
        "gpu": gpu,
        **info,
        "server_url_checked": server_url,
        "pairs_sha256": pairs_sha256,
        "started_at": started.isoformat(),
        "finished_at": now().isoformat(),
        "scores": _rows(pairs, scores),
    }
    write_json(out / f"reference-{model_id.rsplit('/', 1)[-1]}.json", result)
    return result
