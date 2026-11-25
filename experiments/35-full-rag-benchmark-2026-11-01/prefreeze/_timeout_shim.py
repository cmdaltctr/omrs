"""Test helper: a ``timeout`` stand-in for hosts that lack GNU coreutils ``timeout``.

The pod image has GNU ``timeout``; some macOS CI runners do not. Tests call
``add_timeout_if_missing(bin_dir)`` so the chain scripts find one on ``PATH``.
It supports the one form the chain uses: ``timeout -s SIGNAL -k GRACE SECONDS cmd ...``
(both options may be left out) and exits 124 when the command runs past SECONDS, as
GNU ``timeout`` does. It signals the command only; the chain kills the process group.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

_SHIM = """#!{python}
import signal, subprocess, sys
args = sys.argv[1:]
grace, sig = 0.0, signal.SIGTERM
while args[:1] in (["-k"], ["-s"]):
    if args[0] == "-k":
        grace = float(args[1])
    else:
        sig = getattr(signal, "SIG" + args[1])
    args = args[2:]
limit, cmd = float(args[0]), args[1:]
proc = subprocess.Popen(cmd)
try:
    sys.exit(proc.wait(timeout=limit))
except subprocess.TimeoutExpired:
    proc.send_signal(sig)
    try:
        proc.wait(timeout=grace or None)
    except subprocess.TimeoutExpired:
        proc.kill()
    sys.exit(124)
"""


def add_timeout_if_missing(bin_dir: Path) -> None:
    """Write a ``timeout`` shim into *bin_dir* when the host has no ``timeout``."""
    if shutil.which("timeout"):
        return
    shim = bin_dir / "timeout"
    shim.write_text(_SHIM.format(python=sys.executable), encoding="utf-8")
    shim.chmod(0o755)
