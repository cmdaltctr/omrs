"""Status helpers of the web login item (pre-exp35-harness-and-answer-fixes, design D7).

Read the installed plan, the sign-in link file and the current port, and run
``omrs web status``. Kept apart from ``web_login_item`` so that module stays
under the file-size ceiling. The output and launchctl helpers stay in
``web_login_item``; they are imported at call time because that module
imports this one, so the fakes of the existing tests also cover this code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from . import _launchagent, console
from . import _web_login_item as core


def installed_plan() -> tuple[Path, core.WebLoginItemPlan | None]:
    """Return the plist path and the plan that its content describes.

    The plan is ``None`` when no plist exists. A plist that ``install``
    did not write stops the command.
    """
    from . import web_login_item as wl

    plist_path, _, _ = _launchagent.compute_paths(core.LABEL)
    if not plist_path.exists():
        return plist_path, None
    item = core.read_installed(plist_path)
    try:
        if item is None:
            raise _launchagent.InstallerError(
                f"{plist_path} was not written by 'omrs web install'. "
                "Remove it by hand, then run 'omrs web install'."
            )
        plan = core.build_plan(
            workspace=item.workspace, port=item.port, command_path=item.command_path
        )
    except _launchagent.InstallerError as exc:
        wl._fail(str(exc))
    return plist_path, plan


def read_link(plan: core.WebLoginItemPlan) -> core.LinkInfo | None:
    """Parse the sign-in link file of the running server, if it exists."""
    try:
        return core.parse_link(core.link_file(plan).read_text(encoding="utf-8"))
    except OSError:
        return None


def current_port(plan: core.WebLoginItemPlan) -> int:
    """Return the port of the running server (design D6): the link file, else the saved rule."""
    from . import web_login_item as wl

    info = read_link(plan)
    return info.port if info is not None else wl._target_port(plan)


def show_status(json_output: bool) -> None:
    """Print the state of the login item and exit 0 when the app answers, else 1."""
    from . import web_login_item as wl

    plist_path, plan = installed_plan()
    if plan is None:
        if json_output:
            typer.echo(json.dumps({"installed": False, "plist": str(plist_path)}), err=True)
        else:
            wl._say("The login item is not installed. Run 'omrs web install' to install it.")
        raise typer.Exit(code=1)

    uid = os.getuid()
    loaded = wl._launchctl(_launchagent.print_command(uid, plan.label)).returncode == 0
    port = current_port(plan)
    body = core.fetch_health(wl._HOST, port)
    running_version = None if body is None else body.get("version")
    installed_version = core.installed_version(plan.command_path)
    restart_needed = (
        running_version is not None
        and installed_version is not None
        and running_version != installed_version
    )
    facts = {
        "installed": True,
        "loaded": loaded,
        "running": body is not None,
        "running_version": running_version,
        "installed_version": installed_version,
        "restart_needed": restart_needed,
        "workspace": str(core.workspace_dir(plan)),
        "port": port,
        "address": f"http://{wl._HOST}:{port}/",
        "plist": str(plan.plist_path),
        "stdout_log": str(plan.stdout_log),
        "stderr_log": str(plan.stderr_log),
    }
    if json_output:
        typer.echo(json.dumps(facts, indent=2), err=True)
    else:
        console.print("[bold]Web login item[/bold]")
        for line in core.status_lines(facts):
            wl._say(line)
    raise typer.Exit(code=0 if body is not None else 1)
