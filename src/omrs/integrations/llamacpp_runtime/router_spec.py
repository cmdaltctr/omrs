"""The router runtime: its spec, its argument list and its state folder (design D1, D8).

OMRS runs one upstream ``llama-server`` in router mode under runtime id
``router`` (capability ``llamacpp-router``). The argument list is fixed: the
preset file, the model limit, the memory margin and a loopback host and port.
Every model setting lives in ``models.ini`` (:mod:`.preset_writer`), so a
preset edit is never a new router version: the router digest covers the
binary and this argument list only.

State folder (design D8)::

    <state>/runtimes/router/
      start.lock  clients.lock  server.json  server.log  models.ini  hashes.json
      empty-cache/  empty-config/
      models/<model id>/clients.lock  request.lock
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Mapping
from pathlib import Path

from .pins import LLAMA_BUILD
from .rules import BASE_ENVIRONMENT
from .spec import RuntimeSpec
from .state import runtime_dir

#: The one router runtime id.
ROUTER_ID = "router"
#: The capability that owns the router's per-model rules.
ROUTER_CAPABILITY = "llamacpp-router"
#: The preset file the router reads (``--models-preset``).
PRESET_FILE = "models.ini"
#: The SHA-256 cache of listed model files (design D5).
HASHES_FILE = "hashes.json"
#: ``LLAMA_CACHE`` of the router child: an empty folder (design D4).
EMPTY_CACHE_DIR = "empty-cache"
#: ``XDG_CONFIG_HOME`` of the router child: an empty folder (design D4).
EMPTY_CONFIG_DIR = "empty-config"
#: The folder of per-model lock folders.
MODELS_DIR = "models"
#: Hex characters of SHA-256 that name a model folder.
MODEL_ID_CHARS = 16


def router_dir(root: Path) -> Path:
    """Return ``<root>/runtimes/router``."""
    return runtime_dir(root, ROUTER_ID)


def model_id(model: str) -> str:
    """Return the folder name of *model*: the first 16 hex of SHA-256 of the name.

    Every process derives the same id, so the web app and the CLI share one
    ``models/<model id>/`` folder for one model.
    """
    return hashlib.sha256(model.encode("utf-8")).hexdigest()[:MODEL_ID_CHARS]


def model_dir(root: Path, model: str) -> Path:
    """Return ``<root>/runtimes/router/models/<model id>``."""
    return router_dir(root) / MODELS_DIR / model_id(model)


def router_spec(
    *, binary: str, root: Path, port: int, models_max: int, memory_margin_mib: int
) -> RuntimeSpec:
    """Return the managed router spec with its fixed argument list.

    The values come from settings already checked by ``config`` (ranges,
    loopback rule). This builder adds no default of its own.

    Args:
        binary: Absolute path of ``llama-server``.
        root: The state root; the preset file sits in its router folder.
        port: The port of ``llamacpp_router_url``.
        models_max: ``llamacpp_router_models_max``.
        memory_margin_mib: ``llamacpp_router_memory_margin_mib``.

    Returns:
        A spec whose ``argv`` is exactly ``[binary, "--models-preset", <preset>,
        "--models-max", N, "--models-memory-margin", M, "--host", "127.0.0.1",
        "--port", P]`` and whose build floor is the pinned build.
    """
    preset = router_dir(root) / PRESET_FILE
    argv = (
        binary,
        "--models-preset",
        str(preset),
        "--models-max",
        str(models_max),
        "--models-memory-margin",
        str(memory_margin_mib),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    )
    return RuntimeSpec(
        id=ROUTER_ID, role="router", mode="managed", binary=binary, argv=argv, min_build=LLAMA_BUILD
    )


def external_router_spec(url: str) -> RuntimeSpec:
    """Return the external router spec: a URL only, nothing starts or stops."""
    return RuntimeSpec(id=ROUTER_ID, role="router", mode="external", binary="", url_base=url)


def router_environment(environ: Mapping[str, str], folder: Path) -> dict[str, str]:
    """Return the router child's environment and empty its two scratch folders (design D4).

    The child gets the minimal ADR-084 variables, plus ``LLAMA_CACHE`` and
    ``XDG_CONFIG_HOME`` pointed at ``empty-cache/`` and ``empty-config/``.
    b11941 lists every model of its Hugging Face cache and reads
    ``$XDG_CONFIG_HOME/llama.cpp/config.ini`` before its flags, so both
    folders are made empty at every start. No Hugging Face variable and no
    provider key reaches the child.

    Args:
        environ: The environment of the OMRS process.
        folder: The router folder (``<state>/runtimes/router``).
    """
    env = {name: environ[name] for name in BASE_ENVIRONMENT if name in environ}
    for name, variable in ((EMPTY_CACHE_DIR, "LLAMA_CACHE"), (EMPTY_CONFIG_DIR, "XDG_CONFIG_HOME")):
        path = folder / name
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True)
        env[variable] = str(path)
    return env
