"""GGUF folder and scratch router settings from the environment.

Shared copy of the settings half of the Experiment 48 ``router_config.py``
(change ``pre-exp35-harness-and-answer-fixes``, design D4). The router launch
helpers (``start_router``, ``held``, memory and pid readers) stay in the
Experiment 48 folder; they start programs, and this module starts none.

Each runner process writes ``<config_dir>/omrs.jsonc`` before OMRS reads its
settings, so the process's own managed router serves the plan's models:

* one ``llamacpp_models`` entry per model in the plan ``runtime`` block, with the
  model's ``server_args`` as the preset (``plan.json`` is the one source);
* the model file is ``$SWEEP_GGUF_DIR/<file>``; the folder has no default and is
  resolved to an absolute path when it is read;
* the router is ``managed`` on ``127.0.0.1:18080``;
* ``OMRS_CONFIG_DIR`` and ``OMRS_STATE_DIR`` point at the folders the caller
  names, and no ``LLAMACPP_*`` environment variable stays set (an environment
  value would lock a field over the file, and retired ones stop start-up).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

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


def gguf_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Return the absolute folder that ``SWEEP_GGUF_DIR`` names.

    The path is resolved here, once, so a later step that runs from another
    working folder still finds the files.

    Raises:
        RouterConfigError: The variable is unset or blank, or the folder does not exist.
    """
    env = os.environ if environ is None else environ
    value = env.get(GGUF_DIR_ENV, "").strip()
    if not value:
        raise RouterConfigError(
            f"{GGUF_DIR_ENV} is not set; set it to the folder that holds the plan GGUF files"
        )
    folder = Path(value).expanduser().resolve()
    if not folder.is_dir():
        raise RouterConfigError(f"{GGUF_DIR_ENV} names {folder}, which is not an existing folder")
    return folder


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


def write_settings(values: Mapping[str, Any], config_dir: Path) -> Path:
    """Write *values* to ``<config_dir>/omrs.jsonc`` atomically; return the path."""
    from omrs.config.user_config import CONFIG_FILE

    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / CONFIG_FILE
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def check_settings_file(config_dir: Path) -> None:
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
    extra: Mapping[str, str],
    *,
    config_dir: Path,
    state_dir: Path,
    environ: MutableMapping[str, str] | None = None,
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
    env["OMRS_CONFIG_DIR"] = str(config_dir)
    env["OMRS_STATE_DIR"] = str(state_dir)
    return removed


def configure(
    plan: Mapping[str, Any],
    *,
    embed_file: str,
    part_b: bool = False,
    fast: bool = False,
    config_dir: Path,
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
        if key == "llamacpp_models":
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


def load_settings() -> Any:
    """Return fresh OMRS ``Settings`` from the environment and the scratch file."""
    from omrs.config import Settings

    return Settings()
