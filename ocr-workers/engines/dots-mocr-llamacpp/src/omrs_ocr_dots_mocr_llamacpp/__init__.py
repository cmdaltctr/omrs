"""omrs-ocr-dots-mocr-llamacpp: dots.mocr on a llama.cpp server the worker owns.

This package runs inside the engine-owned environment declared by
``ocr-workers/engines/dots-mocr-llamacpp/pyproject.toml``. That environment
holds no PyTorch. The model runs in a pinned ``llama-server`` process that
:mod:`.server` starts and stops.
"""

from __future__ import annotations
