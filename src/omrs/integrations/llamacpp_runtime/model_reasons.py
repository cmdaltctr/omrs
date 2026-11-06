"""Fixed states and reasons of one router model (spec ``llamacpp-server``, "Lifecycle states").

A router model is ``not-downloaded``, ``unloaded``, ``loading``, ``loaded`` or
``failed``. A failed model carries one fixed reason; the plain-English line
comes from this table and never holds server output.
"""

from __future__ import annotations

#: Every state a listed model can be in.
MODEL_STATES = ("not-downloaded", "unloaded", "loading", "loaded", "failed")

#: The fixed reasons of a failed model, with their plain-English lines.
_MODEL_REASON_TEXTS = {
    "model-invalid": "The model file is missing or breaks the file rule: {name}.",
    "file-changed": "A model file changed: {name}.",
    "preset-invalid": "The preset breaks a rule: {name}.",
    "model-load-failed": "The router could not load the model.",
    "model-not-listed": "The model is not in the llama.cpp model list.",
    "role-mismatch": "This model cannot serve the role.",
    "version-busy": "Another OMRS process still uses this model with other settings.",
}

#: The fixed reasons, in table order.
MODEL_REASONS = tuple(_MODEL_REASON_TEXTS)


class ModelUnavailable(RuntimeError):
    """One router model cannot serve; nothing was sent to it.

    Other models of the router are not affected.

    Attributes:
        model: The model name.
        reason: One of :data:`MODEL_REASONS`.
        reason_text: The plain-English line.
    """

    def __init__(self, model: str, reason: str, text: str | None = None) -> None:
        self.model = model
        self.reason = reason
        self.reason_text = text or model_reason_text(reason)
        super().__init__(f"{model}: {self.reason_text}")


def model_reason_text(reason: str, detail: str = "") -> str:
    """Return the fixed line of *reason*; *detail* (a file name or rule) fills ``{name}``.

    Raises:
        ValueError: *reason* is not a fixed model reason.
    """
    if reason not in _MODEL_REASON_TEXTS:
        raise ValueError(f"not a model reason: {reason!r}")
    template = _MODEL_REASON_TEXTS[reason]
    if "{name}" not in template:
        return template
    return template.format(name=detail or "unknown")
