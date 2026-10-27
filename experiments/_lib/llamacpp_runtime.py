"""Check a live llama.cpp server against the plan (reproducible-experiment-runtime, D5).

Call :func:`verify_llamacpp_runtime` once at the start of a run, before any
item is scored, and pass its result to ``record_run_start``::

    from _lib.llamacpp_runtime import verify_llamacpp_runtime
    from _lib.run_record import record_run_start
    from omrs.core.experiment_records.runtime_block import load_runtime_block

    block = load_runtime_block(json.loads((folder / "plan.json").read_text()))
    found = verify_llamacpp_runtime(block, base_url="http://127.0.0.1:9931")
    record_run_start(folder, runtime=found.as_run_record())

The check reads the build number from ``GET /props`` (``build_info``) and the
path of each model file from ``GET /v1/models`` (router mode) or from
``/props`` ``model_path`` (single-model mode). It hashes each file with
SHA-256 and compares build and hashes with the plan. A difference raises
:class:`PreflightError`, which stops the run before any score is written.

The server must be on this machine (ADR-074 decision 6), so the model files
can be hashed. Hashes are not cached, because a cache could hide a replaced
file. Only ``llama.cpp`` entries are checked. Hosted references and the
other arms of a runtime comparison are skipped.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from omrs.core.experiment_records.runtime_block import LLAMA_CPP, RuntimeBlock

try:
    from .preflight import PreflightError
except ImportError:  # imported as top-level ``_lib`` from an experiment folder
    from _lib.preflight import PreflightError  # type: ignore[no-redef]

__all__ = ["FoundModel", "FoundRuntime", "verify_llamacpp_runtime"]

_BUILD_INFO = re.compile(r"^b(?P<number>[0-9]+)(?:-|$)")
_MODEL_FLAGS = ("--model", "-m")
_TIMEOUT_SECONDS = 10.0
_CHUNK_BYTES = 1 << 20


class FoundModel(TypedDict):
    """One model file the server loads: its file name and SHA-256."""

    file: str
    sha256: str


@dataclass(frozen=True)
class FoundRuntime:
    """What the live server runs, as found by :func:`verify_llamacpp_runtime`.

    Attributes:
        build: The llama.cpp build number from ``/props``.
        models: One entry per checked plan model, in plan order.
    """

    build: int
    models: list[FoundModel] = field(default_factory=list)

    def as_run_record(self) -> dict[str, Any]:
        """Return the value for the optional ``runtime`` key of a run record."""
        return {
            "build": self.build,
            "models": [{"file": m["file"], "sha256": m["sha256"]} for m in self.models],
        }


def _require_loopback(base_url: str) -> str:
    parts = urllib.parse.urlsplit(base_url)
    host = parts.hostname or ""
    loopback = host == "localhost"
    if not loopback:
        try:
            loopback = ipaddress.ip_address(host) in (
                ipaddress.ip_address("127.0.0.1"),
                ipaddress.ip_address("::1"),
            )
        except ValueError:
            loopback = False
    if parts.scheme not in ("http", "https") or not loopback:
        raise PreflightError(
            f"the llama.cpp server must be on a loopback address "
            f"(127.0.0.1, localhost or ::1); {base_url!r} is not"
        )
    return base_url.rstrip("/")


def _get_json(base_url: str, path: str) -> Any:
    # An empty ProxyHandler keeps a proxy setting from routing loopback traffic away.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = base_url + path
    try:
        with opener.open(url, timeout=_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        raise PreflightError(f"cannot read {url} from the llama.cpp server: {exc}") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"{url} did not return JSON: {exc}") from None


def _server_build(props: Any) -> int:
    info = props.get("build_info") if isinstance(props, dict) else None
    match = _BUILD_INFO.match(info) if isinstance(info, str) else None
    if match is None:
        raise PreflightError(
            f"the server /props build_info {info!r} does not name a build such as b11671"
        )
    return int(match.group("number"))


def _model_arg(args: Any) -> str | None:
    if not isinstance(args, list):
        return None
    for index, arg in enumerate(args):
        if not isinstance(arg, str):
            continue
        if arg in _MODEL_FLAGS and index + 1 < len(args) and isinstance(args[index + 1], str):
            return str(args[index + 1])
        if arg.startswith("--model="):
            return arg.removeprefix("--model=")
    return None


def _loaded_paths(base_url: str, props: Any) -> list[str]:
    single = props.get("model_path") if isinstance(props, dict) else None
    if isinstance(single, str) and single and single != "none":
        return [single]
    listing = _get_json(base_url, "/v1/models")
    entries = listing.get("data") if isinstance(listing, dict) else None
    paths = []
    for entry in entries if isinstance(entries, list) else []:
        status = entry.get("status") if isinstance(entry, dict) else None
        path = _model_arg(status.get("args")) if isinstance(status, dict) else None
        if path:
            paths.append(path)
    return paths


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as exc:
        raise PreflightError(f"cannot read the model file {path.name}: {exc}") from None
    return digest.hexdigest()


def verify_llamacpp_runtime(block: RuntimeBlock, *, base_url: str) -> FoundRuntime:
    """Compare the live llama.cpp server with the ``runtime`` block of the plan.

    Args:
        block: The validated ``runtime`` block of ``plan.json``.
        base_url: The server address, for example ``http://127.0.0.1:9931``.

    Returns:
        The build and the ``{file, sha256}`` of each checked model.

    Raises:
        PreflightError: The address is not a loopback address, the server
            cannot be read, the build differs from the plan, the server does
            not list a planned file, or a file's SHA-256 differs from the plan.
            The message names the expected and the found value.
    """
    base = _require_loopback(base_url)
    props = _get_json(base, "/props")
    build = _server_build(props)
    planned = [model for model in block.models if model.runtime == LLAMA_CPP]
    for model in planned:
        if model.build != build:
            raise PreflightError(
                f"llama.cpp build differs from the plan for {model.file}: "
                f"the plan records build {model.build}, the server reports build {build}"
            )
    by_name = {Path(path).name: Path(path) for path in _loaded_paths(base, props)}
    found: list[FoundModel] = []
    for model in planned:
        path = by_name.get(model.file)
        if path is None:
            listed = ", ".join(sorted(by_name)) or "no model file"
            raise PreflightError(
                f"the server does not list the planned file {model.file}; it lists {listed}"
            )
        digest = _sha256(path)
        if digest != model.sha256:
            raise PreflightError(
                f"the SHA-256 of {model.file} differs from the plan: "
                f"the plan records {model.sha256}, the file has {digest}"
            )
        found.append({"file": model.file, "sha256": digest})
    return FoundRuntime(build=build, models=found)
