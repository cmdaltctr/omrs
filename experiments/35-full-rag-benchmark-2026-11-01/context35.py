"""Check the answer model's context length (task 14.1a; pre-registration section 16, P10).

Every answer setup sends one completion call (``answer.max_rounds`` 1). The
largest prompt is about 35,000 tokens, so the answer model must accept at least
65,536 tokens on the host the run uses. This tool reads the OpenRouter endpoints
reply of the answer model, takes ``context_length`` of the endpoint whose
``tag`` is the pinned host (``plan.json`` ``pins.settings.answer.allowed_hosts``,
for example ``deepinfra/fp8``; protocol section 0.5), and refuses a missing
host, a missing length or one below the minimum. The model-level value and the
values of other hosts (``deepinfra/fp8/flex`` is a different endpoint) are not used.

Usage (one live call, by the operator in the test pod session; no key needed)::

    uv run --no-sync python context35.py

It prints one JSON record (model, host, context length, minimum, date, source)
for ``protocol.md`` section 0.5. Tests pass a stub through ``fetch``; they never
call OpenRouter.
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
ENDPOINTS_URL = f"https://openrouter.ai/api/v1/models/{MODEL}/endpoints"
_TIMEOUT_SECONDS = 60.0


class ContextLengthError(RuntimeError):
    """The pinned host or its context length is missing, malformed or below the minimum."""


def load_plan() -> dict[str, Any]:
    """Return the parsed ``plan.json`` of this experiment."""
    return json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))


def pinned_host(plan: Mapping[str, Any]) -> str:
    """Return the one answer host pinned in ``pins.settings.answer.allowed_hosts``.

    Raises:
        ContextLengthError: The value is missing, blank or names more than one host.
    """
    value = ((plan.get("pins") or {}).get("settings") or {}).get("answer", {}).get("allowed_hosts")
    host = value.strip() if isinstance(value, str) else ""
    if not host or "," in host:
        raise ContextLengthError(
            f"plan.json pins.settings.answer.allowed_hosts must name one host (got {value!r})"
        )
    return host


def context_length(reply: Mapping[str, Any], host: str, model: str = MODEL) -> int:
    """Return ``context_length`` of the *host* endpoint of *model* from an endpoints reply.

    Raises:
        ContextLengthError: The reply is not an endpoints list of *model*, lists no
            endpoint tagged *host*, gives no whole-number length, or gives one below
            65,536 tokens.
    """
    data = reply.get("data") if isinstance(reply, Mapping) else None
    endpoints = data.get("endpoints") if isinstance(data, Mapping) else None
    if not isinstance(endpoints, list):
        raise ContextLengthError("the OpenRouter reply has no 'data.endpoints' list")
    if data.get("id") != model:
        raise ContextLengthError(f"the OpenRouter reply is for {data.get('id')!r}, not {model!r}")
    entry = next((e for e in endpoints if isinstance(e, Mapping) and e.get("tag") == host), None)
    if entry is None:
        raise ContextLengthError(f"the OpenRouter reply for {model!r} lists no endpoint {host!r}")
    length = entry.get("context_length")
    if not isinstance(length, int) or isinstance(length, bool):
        raise ContextLengthError(
            f"{model!r} on {host!r} has no whole-number 'context_length' (got {length!r})"
        )
    if length < MIN_CONTEXT_TOKENS:
        raise ContextLengthError(
            f"{model!r} on {host!r} accepts {length} tokens, below the minimum of "
            f"{MIN_CONTEXT_TOKENS:,} that one answer call needs (task 14.1a)"
        )
    return length


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read())


def check(
    *,
    fetch: Callable[[str], Any] = _get_json,
    today: str | None = None,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read the endpoints reply through *fetch* and return the record for ``protocol.md``."""
    host = pinned_host(load_plan() if plan is None else plan)
    length = context_length(fetch(ENDPOINTS_URL), host)
    return {
        "model": MODEL,
        "host": host,
        "context_length": length,
        "minimum": MIN_CONTEXT_TOKENS,
        "checked": today or datetime.now(UTC).date().isoformat(),
        "source": ENDPOINTS_URL,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    fetch: Callable[[str], Any] = _get_json,
    today: str | None = None,
    plan: Mapping[str, Any] | None = None,
) -> int:
    """Print the record; return 0, or 2 when the length is refused or the call fails."""
    del argv  # no options; the model, host and minimum come from this module and plan.json
    try:
        record = check(fetch=fetch, today=today, plan=plan)
    except (ContextLengthError, OSError, ValueError) as error:
        print(f"[error] {error}", flush=True)
        return 2
    print(json.dumps(record, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
