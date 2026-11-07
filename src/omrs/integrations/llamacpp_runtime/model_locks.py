"""Per-model client and request locks of the router (design D8; task 4.1).

Each listed model has ``models/<model id>/clients.lock``. A process that uses
model X holds a shared lock on it until it leaves. A process that wants to
change X's preset section takes it exclusive, without blocking and only
while it holds the router's ``start.lock``: success means no other process
uses X. A one-slot model (``parallel = 1``) also has ``request.lock``, held
exclusive for each request, so requests to it serialise across processes
while requests to other models do not wait.

Lock order (no wait cycle):

* a process blocks on ``start.lock`` while it may hold the router
  ``clients.lock`` (shared), model ``clients.lock`` files (shared) and no
  ``request.lock``;
* under ``start.lock`` it tries model ``clients.lock`` files without
  blocking only;
* it blocks on a model ``request.lock`` last, holding no ``start.lock``; each
  holder ends after one bounded request.
"""

from __future__ import annotations

from pathlib import Path

from .locks import LockFile
from .router_spec import model_dir


class ModelHolds:
    """This process's shared holds on model ``clients.lock`` files.

    Not thread-safe; the router lease calls it under its own lock.

    Args:
        root: The state root.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._holds: dict[str, LockFile] = {}

    def held(self, model: str) -> bool:
        """Whether this process holds *model*'s client lock."""
        return model in self._holds

    def hold(self, model: str) -> bool:
        """Take *model*'s client lock shared without blocking; return success.

        Under ``start.lock`` this always succeeds: only a holder of
        ``start.lock`` takes the lock exclusive.
        """
        if model in self._holds:
            return True
        lock = LockFile(model_dir(self.root, model) / "clients.lock")
        if not lock.acquire(shared=True, blocking=False):
            lock.close()
            return False
        self._holds[model] = lock
        return True

    def take_exclusive(self, model: str) -> LockFile | None:
        """Drop this process's hold on *model* and try the lock exclusive.

        Call under ``start.lock``. On failure the hold this process had is
        taken again, so nothing changes.

        Returns:
            The exclusive lock, or ``None`` when another process uses *model*.
        """
        had = self._holds.pop(model, None)
        if had is not None:
            had.close()
        probe = LockFile(model_dir(self.root, model) / "clients.lock")
        if probe.acquire(shared=False, blocking=False):
            return probe
        probe.close()
        if had is not None:
            self.hold(model)
        return None

    def keep(self, model: str, probe: LockFile) -> None:
        """Turn an exclusive *probe* into this process's shared hold (under ``start.lock``)."""
        probe.acquire(shared=True, blocking=False)
        self._holds[model] = probe

    def release(self, model: str) -> None:
        """Drop the hold on *model*, if any."""
        lock = self._holds.pop(model, None)
        if lock is not None:
            lock.close()

    def release_all(self) -> None:
        """Drop every hold (the router lease left)."""
        for model in list(self._holds):
            self.release(model)


def request_lock(root: Path, model: str) -> LockFile:
    """Take *model*'s ``request.lock`` exclusive, waiting as long as it takes.

    The wait has no timeout of its own: each holder ends after one bounded
    request, and the caller's request timeout starts after this returns.
    """
    lock = LockFile(model_dir(root, model) / "request.lock")
    try:
        lock.acquire()
    except BaseException:
        lock.close()
        raise
    return lock
