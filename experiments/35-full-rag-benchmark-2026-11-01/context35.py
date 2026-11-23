"""Check the answer model's context length (task 14.1a; pre-registration section 16, P10).

Every answer setup sends one completion call (``answer.max_rounds`` 1). The
largest prompt is about 35,000 tokens, so the answer model must accept at least
65,536 tokens. This tool reads ``context_length`` of the answer model from an
OpenRouter models reply and refuses a smaller value or a missing one.

Usage (one live call, by the operator in the test pod session; no key needed)::

    uv run --no-sync python context35.py

It prints one JSON record (model, context length, minimum, date, source) for
``protocol.md`` section 0.5. Tests pass a stub through ``fetch``; they never call
OpenRouter.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import arms  # noqa: E402

MODEL = arms.ANSWER_MODEL
MIN_CONTEXT_TOKENS = 65_536
MODELS_URL = "https://openrouter.ai/api/v1/models"
_TIMEOUT_SECONDS = 60.0


class ContextLengthError(RuntimeError):
    """The answer model's context length is missing, malformed or below the minimum."""


def context_length(reply: Mapping[str, Any], model: str = MODEL) -> int:
    """Return ``context_length`` of *model* from an OpenRouter models reply.

    Raises:
        ContextLengthError: The reply is not a models list, lists no such model,
            gives no whole-number length, or gives one below 65,536 tokens.
    """
    models = reply.get("data") if isinstance(reply, Mapping) else None
    if not isinstance(models, list):
        raise ContextLengthError("the OpenRouter reply has no 'data' list of models")
    entry = next((m for m in models if isinstance(m, Mapping) and m.get("id") == model), None)
    if entry is None:
        raise ContextLengthError(f"the OpenRouter reply lists no model {model!r}")
    length = entry.get("context_length")
    if not isinstance(length, int) or isinstance(length, bool):
        raise ContextLengthError(
            f"{model!r} has no whole-number 'context_length' in the reply (got {length!r})"
        )
    if length < MIN_CONTEXT_TOKENS:
        raise ContextLengthError(
            f"{model!r} accepts {length} tokens, below the minimum of "
            f"{MIN_CONTEXT_TOKENS:,} that one answer call needs (task 14.1a)"
        )
    return length


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read())


def check(*, fetch: Callable[[str], Any] = _get_json, today: str | None = None) -> dict[str, Any]:
    """Read the models reply through *fetch* and return the record for ``protocol.md``."""
    length = context_length(fetch(MODELS_URL))
    return {
        "model": MODEL,
        "context_length": length,
        "minimum": MIN_CONTEXT_TOKENS,
        "checked": today or datetime.now(UTC).date().isoformat(),
        "source": MODELS_URL,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: Callable[[str], Any] = _get_json,
    today: str | None = None,
) -> int:
    """Print the record; return 0, or 2 when the length is refused or the call fails."""
    del argv  # no options; the model and the minimum are pinned in this module
    try:
        record = check(fetch=fetch, today=today)
    except (ContextLengthError, OSError, ValueError) as error:
        print(f"[error] {error}", flush=True)
        return 2
    print(json.dumps(record, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
