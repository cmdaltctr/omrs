"""Scratch OMRS settings and the managed router for the sweep (change task 3.5, D2, D6, D6a).

Each runner process writes ``output/config/omrs.jsonc`` before OMRS reads its
settings, so the process's own managed router serves the plan models:

* one ``llamacpp_models`` entry per model of the plan ``runtime`` block. Its
  preset is the model's ``server_args`` (plan.json is the one source). Its
  file is ``$SWEEP_GGUF_DIR/<file>``; there is no default folder;
* the router is ``managed`` on ``127.0.0.1:18080``; Part B sets
  ``llamacpp_router_models_max`` to 1; Part C fast mode changes the 4B
  embedding entry by ``parallel=8 kv-unified=true`` only;
* ``OMRS_CONFIG_DIR`` and ``OMRS_STATE_DIR`` point inside ``output/``, and no
  ``LLAMACPP_*`` environment variable stays set (an environment value would
  lock a field over the file, and the retired ones stop start-up).

Router lifecycle, per process (OMRS code, nothing here launches a program):
:func:`start_router` stops any router of the scratch state folder that no
OMRS process uses (``RuntimeManager.sweep``), then joins the router lease
(``compose_runtimes.router_lease_for`` gives ``RouterLease``; ``join`` starts
``llama-server`` after the preset writer writes ``models.ini``) and loads each
named model (``RouterLease.ensure_ready``). The process's ``RuntimeManager``
leaves the lease at exit (``atexit``, and SIGTERM through
``install_sigterm_exit``), which stops the router when no other client holds it.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
OUTPUT = EXP_DIR / "output"
CONFIG_DIR = OUTPUT / "config"
STATE_DIR = OUTPUT / "state"

#: The scratch router port (D2): neither the live app nor the Llama app uses it.
ROUTER_PORT = 18080
ROUTER_URL = f"http://127.0.0.1:{ROUTER_PORT}/v1"
#: The folder of the four GGUF files. Required: no default path.
GGUF_DIR_ENV = "SWEEP_GGUF_DIR"
#: Part B loads one model at a time (D2, D6).
PART_B_MODELS_MAX = 1
#: Part C fast mode: the only change to the exact 4B preset (D6a).
FAST_MODE_CHANGES: Mapping[str, Any] = {"parallel": 8, "kv-unified": True}
#: Plan keys that are not router preset keys, with the only value the run accepts.
#: D6a: speculative decoding is off by the b11941 default, recorded by the /props snapshot.
RECORD_ONLY_KEYS: Mapping[str, Any] = {"spec-type": "none"}


class RouterConfigError(RuntimeError):
    """The scratch settings cannot be built, or OMRS refuses them."""


# --- plan models ---------------------------------------------------------------


def gguf_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Return the folder that ``SWEEP_GGUF_DIR`` names.

    Raises:
        RouterConfigError: The variable is unset or blank.
    """
    env = os.environ if environ is None else environ
    value = env.get(GGUF_DIR_ENV, "").strip()
    if not value:
        raise RouterConfigError(
            f"{GGUF_DIR_ENV} is not set; set it to the folder that holds the plan GGUF files"
        )
    return Path(value).expanduser()


def model_name(model: Mapping[str, Any]) -> str:
    """Return the router request name ``<repository>:<quant>`` of one plan model.

    The quantisation tag is the last ``-`` part of the file stem
    (``Qwen3-4B-Q8_0.gguf`` gives ``Q8_0``).
    """
    quant = Path(model["file"]).stem.rsplit("-", 1)[-1]
    return f"{model['repository']}:{quant}"


def entry_id(model: Mapping[str, Any]) -> str:
    """Return the ``llamacpp_models`` key of one plan model: its role, without dots."""
    return str(model["role"]).lower().replace(".", "")


def _is_embedding(model: Mapping[str, Any]) -> bool:
    return model.get("server_args", {}).get("embeddings") is True


def chat_model(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the one plan model that is not an embedding model (answers, claim check)."""
    found = [m for m in plan["runtime"]["models"] if not _is_embedding(m)]
    if len(found) != 1:
        raise RouterConfigError(f"the plan must hold one chat model; it holds {len(found)}")
    return found[0]


def plan_model(plan: Mapping[str, Any], file: str) -> Mapping[str, Any]:
    """Return the plan model of *file*."""
    for model in plan["runtime"]["models"]:
        if model["file"] == file:
            return model
    raise RouterConfigError(f"the plan runtime block lists no model file {file}")


def preset_from_server_args(server_args: Mapping[str, Any], *, file: str) -> dict[str, Any]:
    """Return the router preset of one plan model's ``server_args``.

    The values stay as the plan writes them, with two spelling rules:

    * a JSON boolean for a preset key whose words are ``on`` and ``off``
      (``flash-attn``, ``fit``) becomes ``on`` or ``off``, as design D6a writes it;
    * a key of :data:`RECORD_ONLY_KEYS` with its accepted value is left out.

    Raises:
        RouterConfigError: OMRS's preset rules refuse a key or a value. The
            message names the file, the key and the OMRS rule.
    """
    from omrs.config.llamacpp_preset import PRESET_KEYS, preset_problems

    preset: dict[str, Any] = {}
    for key, value in server_args.items():
        if key in RECORD_ONLY_KEYS and value == RECORD_ONLY_KEYS[key]:
            continue
        spec = PRESET_KEYS.get(key)
        words = set(spec.choices) if spec is not None and spec.kind == "choice" else set()
        if isinstance(value, bool) and {"on", "off"} <= words:
            value = "on" if value else "off"
        preset[key] = value
    problems = preset_problems(preset)
    if problems:
        text = "; ".join(f"{p.key}: {p.rule}" for p in problems)
        raise RouterConfigError(f"{file}: OMRS refuses the preset: {text}")
    return preset


def model_entries(
    plan: Mapping[str, Any], folder: Path, *, fast_file: str | None = None
) -> dict[str, dict[str, Any]]:
    """Return one ``llamacpp_models`` entry per plan model, in plan order.

    Args:
        plan: The parsed ``plan.json``.
        folder: The ``SWEEP_GGUF_DIR`` folder.
        fast_file: The model whose preset takes :data:`FAST_MODE_CHANGES` (Part C fast).

    Raises:
        RouterConfigError: A model file is missing, or OMRS refuses a preset.
    """
    entries: dict[str, dict[str, Any]] = {}
    for model in plan["runtime"]["models"]:
        path = folder / model["file"]
        if not path.is_file():
            raise RouterConfigError(f"model file {path} is missing; check {GGUF_DIR_ENV}")
        preset = preset_from_server_args(model["server_args"], file=model["file"])
        if model["file"] == fast_file:
            preset.update(FAST_MODE_CHANGES)
        entries[entry_id(model)] = {
            "model": model_name(model),
            "file": str(path),
            "sha256": model["sha256"],
            "preset": preset,
        }
    return entries


def build_settings(
    plan: Mapping[str, Any],
    folder: Path,
    *,
    embed_file: str,
    part_b: bool = False,
    fast: bool = False,
) -> dict[str, Any]:
    """Return the ``omrs.jsonc`` values of one run (design D2).

    Args:
        plan: The parsed ``plan.json``.
        folder: The ``SWEEP_GGUF_DIR`` folder.
        embed_file: The embedding model of this run (``llamacpp_embed_model``).
        part_b: Load one model at a time (``llamacpp_router_models_max`` 1).
        fast: Part C fast mode on the *embed_file* entry.
    """
    chat = model_name(chat_model(plan))
    values: dict[str, Any] = {
        "embed_provider": "llamacpp",
        "local_backend": "llamacpp",
        "metadata_llm_provider": "local",
        "llamacpp_router_server": "managed",
        "llamacpp_router_url": ROUTER_URL,
        "llamacpp_embed_model": model_name(plan_model(plan, embed_file)),
        "llamacpp_chat_model": chat,
        "answer": {
            "provider": "llamacpp",
            "model": chat,
            "verify_provider": "local",
            "verify_model": chat,
        },
        "llamacpp_models": model_entries(plan, folder, fast_file=embed_file if fast else None),
    }
    if part_b:
        values["llamacpp_router_models_max"] = PART_B_MODELS_MAX
    return values


# --- the scratch file and the environment --------------------------------------


def write_settings(values: Mapping[str, Any], config_dir: Path = CONFIG_DIR) -> Path:
    """Write *values* to ``<config_dir>/omrs.jsonc`` atomically; return the path."""
    from omrs.config.user_config import CONFIG_FILE

    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / CONFIG_FILE
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def check_settings_file(config_dir: Path = CONFIG_DIR) -> None:
    """Read the scratch file with OMRS's reader; stop on any problem it lists.

    Raises:
        RouterConfigError: The file is broken, or a key is ignored (the
            message names each key and OMRS's rule).
    """
    from omrs.config.settings_file import read_settings_file

    found = read_settings_file(config_dir)
    if found.state != "ok" or found.problems:
        text = "; ".join(f"{p.key}: {p.message}" for p in found.problems) or found.state
        raise RouterConfigError(f"OMRS does not accept {found.path}: {text}")


def prepare_environment(
    extra: Mapping[str, str], environ: MutableMapping[str, str] | None = None
) -> list[str]:
    """Point OMRS at the scratch folders, set *extra* and drop every ``LLAMACPP_*`` key.

    Returns:
        The removed ``LLAMACPP_*`` names, sorted.
    """
    env = os.environ if environ is None else environ
    removed = sorted(name for name in env if name.startswith("LLAMACPP_"))
    for name in removed:
        del env[name]
    env.update(extra)
    env["OMRS_CONFIG_DIR"] = str(CONFIG_DIR)
    env["OMRS_STATE_DIR"] = str(STATE_DIR)
    return removed


def configure(
    plan: Mapping[str, Any],
    *,
    embed_file: str,
    part_b: bool = False,
    fast: bool = False,
    config_dir: Path = CONFIG_DIR,
) -> Path:
    """Build, write and check the scratch ``omrs.jsonc`` of one run; return its path."""
    values = build_settings(plan, gguf_dir(), embed_file=embed_file, part_b=part_b, fast=fast)
    path = write_settings(values, config_dir)
    check_settings_file(config_dir)
    check_resolved(load_settings(), values)
    return path


def resolved_conflicts(settings: Any, values: Mapping[str, Any]) -> list[str]:
    """Name each value in *values* that OMRS resolved to something else.

    An environment variable or ``.env`` entry beats ``omrs.jsonc``, so the file
    alone does not fix the provider. Preset entries (``llamacpp_models``) are
    checked by OMRS's own file reader.
    """
    found: list[str] = []
    for key, want in values.items():
        # A key field holds a reference (``env://``, ``file://``) that OMRS resolves to the
        # secret itself, so a comparison means nothing and its message would print the key.
        if key == "llamacpp_models" or key.endswith("_api_key"):
            continue
        pairs = (
            [
                (f"{key}.{sub}", getattr(getattr(settings, key), sub), value)
                for sub, value in want.items()
            ]
            if isinstance(want, Mapping)
            else [(key, getattr(settings, key), want)]
        )
        found += [
            f"{name}: the sweep needs {w!r}, OMRS resolved {r!r}" for name, r, w in pairs if r != w
        ]
    return found


def check_resolved(settings: Any, values: Mapping[str, Any]) -> None:
    """Stop when an environment variable or ``.env`` entry overrides the scratch file.

    Raises:
        RouterConfigError: The message names each key, the wanted and the resolved value.
    """
    problems = resolved_conflicts(settings, values)
    if problems:
        raise RouterConfigError(
            "the environment overrides the sweep settings: "
            + "; ".join(problems)
            + ". Unset the variable, or remove it from .env, and run again."
        )


# --- OMRS settings and the router ----------------------------------------------


def load_settings() -> Any:
    """Return fresh OMRS ``Settings`` from the environment and the scratch file."""
    from omrs.config import Settings

    return Settings()


def dry_run_summary(settings: Any) -> dict[str, Any]:
    """Return what OMRS resolved from the scratch file, and every role problem."""
    from omrs.compose_answer import llamacpp_roles

    return {
        "config_dir": os.environ.get("OMRS_CONFIG_DIR", ""),
        "state_dir": os.environ.get("OMRS_STATE_DIR", ""),
        "llamacpp_router_server": settings.llamacpp_router_server,
        "llamacpp_router_url": settings.llamacpp_router_url,
        "llamacpp_router_models_max": settings.llamacpp_router_models_max,
        "llamacpp_embed_model": settings.llamacpp_embed_model,
        "llamacpp_chat_model": settings.llamacpp_chat_model,
        "answer_model": settings.answer.model,
        "verify_model": settings.answer.verify_model,
        "models": {e.model: dict(e.preset) for e in settings.llamacpp_models.values()},
        "role_problems": [list(p) for p in llamacpp_roles(settings).problems],
    }


def dry_run(path: Path) -> None:
    """Print what OMRS loads from *path* and exit; nothing starts and nothing is sent."""
    summary = dry_run_summary(load_settings())
    print(f"[dry-run] wrote {path}", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    if summary["role_problems"]:
        raise SystemExit("[dry-run] OMRS lists role problems; see above")
    raise SystemExit(0)


def verify_url(settings: Any) -> str:
    """Return ``llamacpp_router_url`` without ``/v1``: the base the live-server check reads."""
    return str(settings.llamacpp_router_url).rstrip("/").removesuffix("/v1")


def start_router(files: Sequence[str], plan: Mapping[str, Any]) -> Any:
    """Start (or join) the scratch router through OMRS and load each model of *files*.

    Returns:
        The process's ``RouterLease``. The router stops when the process exits.

    Raises:
        RouterConfigError: OMRS cannot build the managed router (the reason names why).
    """
    from omrs.compose import get_settings
    from omrs.compose_runtime_manager import runtime_manager
    from omrs.compose_runtimes import router_lease_for
    from omrs.integrations.llamacpp_runtime import install_sigterm_exit

    install_sigterm_exit()
    runtime_manager().sweep()  # a router left by a killed run stops: this start is fresh
    router = router_lease_for(get_settings())
    if isinstance(router, str):
        raise RouterConfigError(f"OMRS cannot start the managed router: {router}")
    url = router.join()
    print(f"[router] joined {url}", flush=True)
    for file in files:
        name = model_name(plan_model(plan, file))
        router.ensure_ready(name)
        print(f"[router] loaded {name}", flush=True)
    return router


@contextlib.contextmanager
def held(router: Any, plan: Mapping[str, Any], file: str) -> Iterator[str]:
    """Hold one router session for *file* while the caller sends direct requests.

    ``/tokenize`` and ``/v1/embeddings`` calls of the runners go straight to the
    router, not through the lease, so without an open session the lease's
    10-minute idle stop could stop the router mid-stage. Do not ingest through
    OMRS inside this block: a one-slot model's request lock is held.

    Yields:
        The router request name of *file*.
    """
    name = model_name(plan_model(plan, file))
    with router.model_session(name):
        yield name


def router_memory_bytes(state_dir: Path = STATE_DIR) -> int | None:
    """Return the resident memory of the recorded router and its model children, in bytes.

    ``None`` when no router of *state_dir* runs. Works on macOS and Linux
    (OMRS's ``children.tree_rss``).
    """
    from omrs.integrations.llamacpp_runtime import children, process
    from omrs.integrations.llamacpp_runtime.router_spec import router_dir
    from omrs.integrations.llamacpp_runtime.state import read_server_record

    record = read_server_record(router_dir(state_dir))
    if record is None or not process.owns(record.pid, record.binary):
        return None
    return children.tree_rss(record.pid, record.binary)


def router_pids(state_dir: Path = STATE_DIR) -> set[int]:
    """Return the recorded router pid and its direct children (the model servers).

    Empty when no router of *state_dir* runs. The GPU memory sampler (task 4.4)
    calls this at every sample, because the router starts model servers on demand.
    """
    from omrs.integrations.llamacpp_runtime import children, process
    from omrs.integrations.llamacpp_runtime.router_spec import router_dir
    from omrs.integrations.llamacpp_runtime.state import read_server_record

    record = read_server_record(router_dir(state_dir))
    if record is None or not process.owns(record.pid, record.binary):
        return set()
    return {record.pid, *children.direct_children(record.pid)}
