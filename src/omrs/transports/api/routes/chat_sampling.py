"""Temperature, seed and allowed hosts: the shared read and save rules (pre-exp35 D1, D11).

The Chat and judge settings routes use the helpers here to report and save
``answer.temperature``, ``answer.seed`` and ``answer.allowed_hosts`` (Chat)
and their ``verify_*`` twins (judge). Each value locks on its own variable,
apart from the provider, the model and the reasoning level. A read lists the
values the provider in force sends nothing for.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi.responses import Response
from pydantic import BaseModel, Field

from ....compose_providers import locked_fields
from ....core.answer.settings import SEED_MAX, TEMPERATURE_MAX, HostList
from ....core.providers.llm import registry as llm_registry
from ....core.providers.llm.sampling import SAMPLING_NAMES
from ..errors import error_response

#: Body name -> settings path, per role.
CHAT_SAMPLING = {name: f"answer.{name}" for name in SAMPLING_NAMES}
JUDGE_SAMPLING = {name: f"answer.verify_{name}" for name in SAMPLING_NAMES}

Temperature = Annotated[float, Field(strict=True, ge=0, le=TEMPERATURE_MAX)] | None
Seed = Annotated[int, Field(strict=True, ge=0, le=SEED_MAX)] | None
Hosts = Annotated[HostList, Field(max_length=1100)] | None


class SamplingFields(BaseModel):
    """The three sampling fields a Chat or judge save may carry.

    A field left out keeps the saved value. ``null`` (or ``""`` for the host
    list) removes it. A bad value is a 400 before anything is written.
    """

    temperature: Temperature = None
    seed: Seed = None
    allowed_hosts: Hosts = None


def _variable(path: str) -> str:
    return path.upper().replace(".", "__")


def sent(body: SamplingFields) -> dict[str, Any]:
    """Return the sampling fields the body named, by body name."""
    return {name: getattr(body, name) for name in SAMPLING_NAMES if name in body.model_fields_set}


def _locked(settings: Any, paths: dict[str, str]) -> list[str]:
    held = locked_fields(settings, settings.provider_explicit)
    return [name for name, path in paths.items() if path in held]


def sampling_view(settings: Any, paths: dict[str, str], provider: str) -> dict[str, Any]:
    """Return the sampling fields of a settings ``GET`` body.

    Args:
        settings: Settings in use.
        paths: :data:`CHAT_SAMPLING` or :data:`JUDGE_SAMPLING`.
        provider: The registry provider the values go to.
    """
    locked = _locked(settings, paths)
    ignored = llm_registry.ignored_sampling(provider)
    values = {
        name: getattr(settings.answer, path.removeprefix("answer.")) for name, path in paths.items()
    }
    reason = None
    if locked:
        names = " and ".join(_variable(paths[name]) for name in locked)
        reason = f"Set by {names} in the environment or .env. Remove it to edit here."
    return {
        **values,
        "sampling_locked": locked,
        "sampling_lock_reason": reason,
        "sampling_ignored": [name for name in SAMPLING_NAMES if name in ignored],
    }


def sampling_lock_response(
    settings: Any, paths: dict[str, str], values: dict[str, Any]
) -> Response | None:
    """Return a 409 naming the variables when the body sends a locked value, else ``None``."""
    clash = [name for name in _locked(settings, paths) if name in values]
    if not clash:
        return None
    names = " and ".join(_variable(paths[name]) for name in clash)
    return error_response(
        409, f"Set by {names} in the environment or .env. Remove it to edit here."
    )


def sampling_changes(
    settings: Any, paths: dict[str, str], values: dict[str, Any], clearing: bool
) -> dict[str, Any]:
    """Return the file changes for the sampling values.

    A sent value is written, and ``null`` or ``""`` removes its key. A clear
    of the whole choice also removes every unlocked value. Otherwise the
    saved values stay.
    """
    if values:
        return {
            paths[name]: (None if value in (None, "") else value) for name, value in values.items()
        }
    if not clearing:
        return {}
    locked = set(_locked(settings, paths))
    return {path: None for name, path in paths.items() if name not in locked}
