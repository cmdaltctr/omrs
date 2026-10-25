"""``omrs experiments`` command group (experiment-format-v1, design D10).

``check`` reports problems in the experiments directory and writes nothing.
``index`` compares or rewrites the generated index in ``EXP_README.md``.
``new`` creates an experiment folder from the packaged templates. The rules
live in ``omrs.core.experiment_records``; this module only formats output.
All output goes to stderr, including ``--json`` (gotcha #5).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.markup import escape

from ...core.experiment_records.check import Finding, check_experiments, has_failures
from ...core.experiment_records.index import (
    README_FILE,
    IndexFileError,
    index_is_current,
    read_readme,
    render_index,
    write_index,
)
from ...core.experiment_records.record import Category, RecordError, Size
from ...core.experiment_records.reserved import load_reservations
from ...core.experiment_records.scaffold import ScaffoldError, create_experiment
from ...core.experiment_records.scan import scan_experiments
from . import _JSON_HELP, app, console

experiments_app = typer.Typer(
    name="experiments",
    help="Check, index and create research experiment folders.",
    no_args_is_help=True,
)
app.add_typer(experiments_app, name="experiments")

DirArgument = Annotated[
    Path,
    typer.Argument(help="The experiments directory.", show_default=True),
]
_DEFAULT_DIR = Path("experiments")


@experiments_app.callback()
def experiments() -> None:
    """Check, index and create research experiment folders."""


def _fail(message: str) -> NoReturn:
    console.print(f"[red]Error:[/red] {escape(message)}", soft_wrap=True)
    raise typer.Exit(code=1)


def _summary(findings: tuple[Finding, ...]) -> str:
    counts = {severity: 0 for severity in ("error", "warning", "info")}
    for finding in findings:
        counts[finding.severity] += 1
    return f"{counts['error']} errors, {counts['warning']} warnings, {counts['info']} info"


@experiments_app.command()
def check(
    directory: DirArgument = _DEFAULT_DIR,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit with code 1 on warnings too.")
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help=_JSON_HELP)] = False,
) -> None:
    """Report problems in the experiment folders. Writes no file.

    Exits with code 1 when an error is found, or a warning with --strict.
    """
    try:
        findings = check_experiments(directory)
    except OSError as exc:
        _fail(str(exc))
    if json_output:
        typer.echo(json.dumps([f.model_dump() for f in findings], indent=2), err=True)
    elif not findings:
        console.print(f"No problems in {escape(str(directory))}.", soft_wrap=True)
    else:
        for finding in findings:
            where = f"{finding.folder}: " if finding.folder else ""
            line = f"{finding.severity:<7} {finding.code:<26} {where}{finding.message}"
            console.print(escape(line), soft_wrap=True)
        console.print(_summary(findings), soft_wrap=True)
    if has_failures(findings, strict=strict):
        raise typer.Exit(code=1)


@experiments_app.command()
def index(
    directory: DirArgument = _DEFAULT_DIR,
    write: Annotated[
        bool, typer.Option("--write", help=f"Replace the marked block in {README_FILE}.")
    ] = False,
) -> None:
    """Print the generated index, or write it into EXP_README.md with --write.

    Without --write, exits with code 1 when EXP_README.md is out of date.
    """
    readme = directory / README_FILE
    try:
        folders = scan_experiments(directory)
        reservations = load_reservations(directory)
        if write:
            changed = write_index(readme, folders, reservations)
            state = "Wrote the index to" if changed else "The index is already up to date in"
            console.print(f"{state} {escape(str(readme))}.", soft_wrap=True)
            return
        typer.echo(render_index(folders, reservations), err=True, nl=False)
        current = index_is_current(read_readme(readme), folders, reservations)
    except (OSError, RecordError, IndexFileError) as exc:
        _fail(str(exc))
    if not current:
        _fail(f"{readme} is out of date. Run `omrs experiments index --write`.")
    console.print(f"The index in {escape(str(readme))} is up to date.", soft_wrap=True)


def _parse_date(text: str | None) -> date:
    if text is None:
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError:
        _fail(f"date {text!r} must be a real day written YYYY-MM-DD")


@experiments_app.command()
def new(
    slug: Annotated[str, typer.Argument(help="Lower-case words joined by hyphens.")],
    title: Annotated[str, typer.Option("--title", help="One-line title.")],
    category: Annotated[Category, typer.Option("--category", help="Experiment category.")],
    size: Annotated[Size, typer.Option("--size", help="Quick, Standard or Confirmatory.")],
    directory: DirArgument = _DEFAULT_DIR,
    follow_up: Annotated[
        str | None,
        typer.Option("--follow-up", help="Take the next free letter of this experiment number."),
    ] = None,
    day: Annotated[
        str | None, typer.Option("--date", help="Planning date, YYYY-MM-DD. Defaults to today.")
    ] = None,
) -> None:
    """Create an experiment folder with its record and template files, then print its path."""
    planned = _parse_date(day)
    try:
        folder = create_experiment(
            directory,
            slug=slug,
            title=title,
            category=category,
            size=size,
            day=planned,
            follow_up=follow_up,
        )
    except (ScaffoldError, RecordError, OSError) as exc:
        _fail(str(exc))
    console.print(escape(str(folder)), soft_wrap=True)
