"""``omrs llamacpp`` command group (change one-llamacpp-router, task 6.2, design D12).

``install`` downloads the pinned llama.cpp build, checks it and places
``llama-server`` in the OMRS data folder. With a managed router it then
downloads each listed model that has no file into the Hugging Face cache, at
the repo's current revision (task 6.2a). It writes no setting: ``omrs web``
records the cached file in the model list when the router first needs it
(gotcha 18). It is headless (no prompt), starts no server and reports on
stderr (gotcha #5). A refusal exits 1 with its reason.
"""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Annotated, NoReturn

import typer
from rich.markup import escape

from ...core.providers import model_sources
from ...integrations import huggingface_models as hf_models
from ...integrations.llamacpp_runtime import pins, provision
from . import app, console

#: Bytes read per step when the downloaded file is hashed.
_HASH_CHUNK = 1024 * 1024

llamacpp_app = typer.Typer(
    name="llamacpp",
    help="Install the pinned llama.cpp build that OMRS runs.",
    no_args_is_help=True,
)
app.add_typer(llamacpp_app, name="llamacpp")

_LINUX_FLAVOURS = ("cpu", "cuda")


@llamacpp_app.callback()
def llamacpp() -> None:
    """Install the pinned llama.cpp build that OMRS runs."""


def _fail(message: str) -> NoReturn:
    console.print(f"[red]Error:[/red] {escape(message)}", soft_wrap=True)
    raise typer.Exit(code=1)


def _check_flavour(flavour: str | None) -> None:
    """Refuse a flavour the host or the command does not take."""
    if flavour is None:
        return
    try:
        detected = provision.detect_flavour()
    except pins.NotSupported:
        detected = None  # install reports not-supported
    if detected == "metal":
        _fail(
            "--flavour does not apply on macOS: Apple silicon has one build (metal). "
            "Run the command without --flavour."
        )
    if flavour not in _LINUX_FLAVOURS:
        _fail(f"--flavour must be cpu or cuda, not '{flavour}'.")


@llamacpp_app.command()
def install(
    flavour: Annotated[
        str | None,
        typer.Option(
            "--flavour",
            help="Linux x86-64 build: cpu or cuda. Default: cuda when an NVIDIA driver is "
            "loaded, else cpu. Not used on macOS.",
        ),
    ] = None,
) -> None:
    """Download, check and place the pinned llama.cpp build. No server starts."""
    _check_flavour(flavour)
    try:
        built = provision.install_pinned_build(flavour, lambda line: console.print(line))
    except provision.ProvisionError as exc:
        _fail(f"{exc.reason}: {exc}")
    console.print(
        f"llama.cpp {pins.LLAMA_TAG} ({built.flavour}) is ready: {escape(str(built.path))}",
        soft_wrap=True,
    )
    _download_missing_models()


def _download_missing_models() -> None:
    """Download each listed model with no file, when OMRS runs the router."""
    from ... import compose

    settings = compose.get_settings()
    if settings.llamacpp_router_server != "managed":
        return
    for entry in settings.llamacpp_models.values():
        if not (entry.file or "").strip():
            _download_model(entry.model)


def _download_model(model: str) -> None:
    """Download *model* (``org/name:QUANT``) at its repo's current revision and report it."""
    console.print(f"Downloading {escape(model)}", soft_wrap=True)
    repo, _, label = model.rpartition(":")
    try:
        listed = hf_models.list_repo_files(repo)
        found = model_sources.group_gguf_files(listed.files)
        chosen = next((e for e in found if e.label == label), None)
        if chosen is None:
            _fail(f"{model}: the repo holds no {label} GGUF file.")
        done = [0]

        def progress(count: int) -> None:
            before = done[0] * 10 // max(chosen.size_bytes, 1)
            done[0] += count
            if done[0] * 10 // max(chosen.size_bytes, 1) > before:
                console.print(f"  {done[0] / 1e9:.1f} of {chosen.size_bytes / 1e9:.1f} GB")

        path = hf_models.download_files(
            repo,
            listed.revision,
            chosen.files,
            on_bytes=progress,
            cancel=threading.Event(),
            token=os.environ.get("HF_TOKEN") or None,
        )
    except hf_models.ModelHostError as exc:
        _fail(f"{model}: {exc.reason}")
    console.print(f"  {escape(path)} (SHA-256 {_sha256(path)})", soft_wrap=True)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
