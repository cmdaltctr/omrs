"""Keep the OCR worker packages from leaking between tests.

The worker core and the engines are imported from source by several
test modules, each with its own ``sys.path``. A half-restored
``sys.modules`` would mix two generations of the same classes (an
``isinstance`` check against a class from the other generation fails).
Each test that imports them starts and ends with none loaded.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

_PREFIX = "omrs_ocr_"


@contextmanager
def isolated_worker_modules() -> Iterator[None]:
    """Unload every ``omrs_ocr_*`` module on entry; restore the originals on exit.

    Bytecode writes are off meanwhile: a ``__pycache__`` written into an engine
    folder changes the folder that the smoke test's plan-only check snapshots in
    another worker.
    """
    saved = {name: mod for name, mod in sys.modules.items() if name.startswith(_PREFIX)}
    for name in saved:
        del sys.modules[name]
    saved_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = saved_flag
        for name in [name for name in sys.modules if name.startswith(_PREFIX)]:
            del sys.modules[name]
        sys.modules.update(saved)
