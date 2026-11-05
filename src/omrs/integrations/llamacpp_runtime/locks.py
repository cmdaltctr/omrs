"""``flock`` helpers for the runtime lock files (design D4).

Each :class:`LockFile` opens its own descriptor, so one process can hold a
shared ``clients.lock`` on one descriptor while another descriptor of the
same process probes the same file exclusively. Kernel ``flock`` locks free
themselves when the owning process dies, which is what makes the lease safe
against SIGKILL without any cleanup code.

Python opens descriptors as non-inheritable (PEP 446), so a started server
never keeps a lock descriptor alive.

On Windows ``flock`` does not exist: acquiring raises
:class:`LockNotSupportedError` and managed mode fails with the reason
``not-supported`` (design D2).
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # POSIX only; the module still imports on Windows for the error type.
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

#: Whether kernel file locks exist on this platform.
LOCKS_SUPPORTED = fcntl is not None and os.name != "nt"


class LockNotSupportedError(RuntimeError):
    """Raised when a lock is acquired on a platform without ``flock``."""


class LockFile:
    """One open descriptor of a lock file.

    Args:
        path: The lock file; created with mode 0600 when missing.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)

    def acquire(self, *, shared: bool = False, blocking: bool = True) -> bool:
        """Take the lock on this descriptor.

        Args:
            shared: ``True`` for a shared lock, ``False`` for exclusive.
            blocking: ``False`` to fail at once instead of waiting.

        Returns:
            ``True`` when the lock is held. A non-blocking attempt that would
            wait returns ``False``.

        Raises:
            LockNotSupportedError: On a platform without ``flock``.
        """
        if not LOCKS_SUPPORTED:
            raise LockNotSupportedError("file locks need a POSIX platform")
        flags = (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(self._fd, flags)
        except BlockingIOError:
            return False
        return True

    def release(self) -> None:
        """Drop the lock but keep the descriptor open for the next acquire."""
        if not LOCKS_SUPPORTED:  # pragma: no cover - Windows
            return
        fcntl.flock(self._fd, fcntl.LOCK_UN)

    def close(self) -> None:
        """Drop any held lock, then close the descriptor.

        A fork in another thread copies this descriptor until its child runs
        exec, and ``flock`` belongs to the open file, so a plain close would
        keep the lock alive in that copy. Unlocking first drops it at once.
        """
        if self._fd >= 0:
            if LOCKS_SUPPORTED:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> LockFile:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
