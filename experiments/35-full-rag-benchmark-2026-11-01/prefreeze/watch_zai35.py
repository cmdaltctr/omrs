"""Send the GLM-5.3 base URL to the pod and print it nowhere (Exp 35, owner 2026-11-26).

The watcher reads the owner's mode-600 file on the Mac (``zai35.base_url_file``), checks
its SHA-256 against ``plan.json`` ``pins.glm_judge.base_url_sha256``, and writes one line
to the pod's mode-600 file :data:`ZAI_ENV` through ssh standard input. The value is on
no command line, in no log and in no dry-run line. ``launch35.sh`` sources the file.
Test hook: ``MAC_WATCH35_PLAN`` names another ``plan.json``.
"""

from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

EXP = Path(__file__).resolve().parent.parent
if str(EXP) not in sys.path:
    sys.path.insert(0, str(EXP))
import zai35  # noqa: E402

ZAI_ENV = "/workspace/.zai_env"
SEND_CMD = (
    f"umask 077; cat > {ZAI_ENV}.tmp && chmod 600 {ZAI_ENV}.tmp && mv {ZAI_ENV}.tmp {ZAI_ENV}"
)


def _plan() -> dict:
    path = Path(os.environ.get("MAC_WATCH35_PLAN") or EXP / "plan.json")
    return json.loads(path.read_text(encoding="utf-8"))


def problems() -> list[str]:
    """Name each problem of the base URL file; never print the value."""
    path = zai35.base_url_file()
    if not path.is_file():
        return [f"GLM-5.3 base URL file {path} not found (mode 600, one line)"]
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        return [f"GLM-5.3 base URL file {path} must be mode 600"]
    try:
        zai35.base_url(_plan(), environ={})
    except zai35.EndpointError as error:
        return [f"GLM-5.3 base URL file {path}: {error}"]
    return []


def send(ssh_base: Sequence[str], timeout: float = 120) -> bool:
    """Write the base URL line to :data:`ZAI_ENV` over ssh standard input."""
    line = f"{zai35.BASE_URL_ENV}={shlex.quote(zai35.base_url(_plan(), environ={}))}\n"
    try:
        found = subprocess.run(  # noqa: S603 - a fixed argument list
            [*ssh_base, SEND_CMD], input=line.encode("utf-8"), capture_output=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False
    return found.returncode == 0


def run_setup(pod: Any, commands: Sequence[str]) -> bool:
    """Run the setup *commands* on *pod*; send the base URL just before the last (the launch)."""
    ok: Callable[[str], bool] = lambda c: pod.ok(c, timeout=900)  # noqa: E731
    return all(ok(c) for c in commands[:-1]) and send(pod.ssh_base) and ok(commands[-1])


def dry_lines(commands: Sequence[str]) -> list[str]:
    """Return the step 5 dry-run lines, with the base URL step and no value."""
    lines = [f"5 ssh {shlex.quote(c)}" for c in commands]
    step = f"5 ssh {shlex.quote(SEND_CMD)} < the {zai35.BASE_URL_ENV} line (value not shown)"
    return [*lines[:-1], step, lines[-1]]
