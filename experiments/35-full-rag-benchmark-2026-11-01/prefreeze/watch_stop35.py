"""Stop the chain on the pod before the Mac pulls, after an abnormal end of the watcher.

Idle, the wall-clock cap and a signal end the watcher while the chain may still run a
stage. Without a stop, the pull could copy outputs that the stage still writes (PR 224).
``tmux kill-session`` hangs up the chain; its ``finish`` trap (pod_test_session.sh) then
kills the stage, stops the background processes and writes the tarball and its .sha256.
The watcher waits a bounded time for the .sha256, so the pull finds a finished tarball.
Every step is best effort: a failure or a timeout is logged and the pull goes on.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

STOP_REASONS = ("interrupted", "idle", "wall-cap")
STOP_SSH_S, DRAIN_S, DRAIN_STEP_S = 60, 180, 10  # one call; wait for the tarball; between checks


def stop_chain(
    pod: Any,
    reason: str,
    *,
    session: str,
    tarball: str,
    say: Callable[[str], None],
    now: Callable[[], float],
    pause: Callable[[float], None],
) -> None:
    """Send the stop and wait up to ``DRAIN_S`` s for the chain's tarball; never raise."""
    if reason not in STOP_REASONS:
        return
    say(f"{reason}: stopping the chain on the pod before the pull")
    sent = pod.ssh(f"tmux kill-session -t {session}", STOP_SSH_S)
    if sent is None or sent.returncode != 0:
        say("  the stop failed (no session, or SSH failed); pulling anyway")
        return
    start = now()
    while now() - start < DRAIN_S:
        found = pod.ssh(f"test -f {tarball}.sha256", STOP_SSH_S)
        if found is None or found.returncode != 1:  # 0: the tarball is done; else SSH is lost
            return
        pause(DRAIN_STEP_S)
    say(f"  no tarball after {DRAIN_S} s; pulling anyway")
