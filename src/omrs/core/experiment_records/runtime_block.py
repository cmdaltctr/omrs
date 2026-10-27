"""The ``runtime`` block of ``plan.json`` (reproducible-experiment-runtime, design D4).

The block pins each local model of an experiment: the Hugging Face
repository, the GGUF file, its SHA-256, the llama.cpp build and the server
arguments that change output. It also names hosted reference arms and the
reproduction tolerance.

One model validates the block. The checker (``check.py``) and the
live-server check (``experiments/_lib/llamacpp_runtime.py``) both use it, so
they cannot disagree about what a valid block is.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .record import RecordError, describe_validation_error

LLAMA_CPP = "llama.cpp"
"""The only runtime allowed for a local model unless the runtime is under test."""

_ZERO_SHA256 = "0" * 64

RUNTIME_KEY = "runtime"
"""The key of the block inside ``plan.json``."""

_FROZEN = ConfigDict(extra="forbid", frozen=True)

ServerArg = str | int | float | bool


class LocalModel(BaseModel):
    """One local model the experiment runs."""

    model_config = _FROZEN

    role: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    file: str = Field(min_length=1, pattern=r"^[^/\\]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime: str = Field(min_length=1)
    # The plan template ships build 0 and an all-zero hash. Both are refused,
    # so a plan that was never filled in fails the checker.
    build: int | None = Field(default=None, ge=1)
    version: str | None = Field(default=None, min_length=1)
    server_args: dict[str, ServerArg] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _runtime_facts(self) -> LocalModel:
        if self.sha256 == _ZERO_SHA256:
            raise ValueError("sha256 is the template placeholder; give the file's real SHA-256")
        if self.runtime == LLAMA_CPP and self.build is None:
            raise ValueError(f"a {LLAMA_CPP} model needs its build number in build")
        if self.runtime != LLAMA_CPP and self.version is None:
            raise ValueError(f"a {self.runtime} model needs its runtime version in version")
        return self


class ReferenceModel(BaseModel):
    """One hosted model that runs as a named reference arm."""

    model_config = _FROZEN

    role: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class Tolerance(BaseModel):
    """The largest change in one metric or per-item score that still counts as reproduced."""

    model_config = _FROZEN

    metric: str | None = Field(default=None, min_length=1)
    item_score: str | None = Field(default=None, min_length=1)
    max_abs_change: float = Field(ge=0)

    @model_validator(mode="after")
    def _one_target(self) -> Tolerance:
        if (self.metric is None) == (self.item_score is None):
            raise ValueError("a tolerance names exactly one of metric or item_score")
        return self


class RuntimeBlock(BaseModel):
    """The ``runtime`` block of ``plan.json``."""

    model_config = _FROZEN

    runtime_under_test: bool = False
    models: list[LocalModel]
    references: list[ReferenceModel] = Field(default_factory=list)
    tolerance: list[Tolerance] = Field(min_length=1)

    @model_validator(mode="after")
    def _llamacpp_only(self) -> RuntimeBlock:
        if self.runtime_under_test:
            return self
        others = sorted({m.runtime for m in self.models if m.runtime != LLAMA_CPP})
        if others:
            raise ValueError(
                f"local models must run through {LLAMA_CPP}, not {', '.join(others)}; "
                "set runtime_under_test to true only when the runtime is the variable"
            )
        return self


def load_runtime_block(plan: Mapping[str, Any]) -> RuntimeBlock:
    """Validate the ``runtime`` block of a decoded ``plan.json``.

    Args:
        plan: The decoded plan object.

    Returns:
        The block.

    Raises:
        RecordError: The plan has no ``runtime`` block, or the block breaks a
            rule. The message names the key.
    """
    if RUNTIME_KEY not in plan:
        raise RecordError(f"{RUNTIME_KEY}: plan.json has no {RUNTIME_KEY} block")
    try:
        return RuntimeBlock.model_validate(plan[RUNTIME_KEY])
    except ValidationError as exc:
        message = describe_validation_error(exc)
        raise RecordError(f"{RUNTIME_KEY}: {message}") from None
