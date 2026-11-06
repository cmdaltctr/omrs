"""``omrs llamacpp`` command group (change one-llamacpp-router, task 6.2, design D12).

``install`` downloads the pinned llama.cpp build, checks it and places
``llama-server`` in the OMRS data folder. It is headless (no prompt), starts
no server and reports on stderr (gotcha #5). A refusal exits 1 with its
reason.
"""

from __future__ import annotations

from typing import Annotated, NoReturn

import typer
from rich.markup import escape

from ...integrations.llamacpp_runtime import pins, provision
from . import app, console

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
