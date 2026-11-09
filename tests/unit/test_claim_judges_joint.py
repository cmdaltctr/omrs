"""Both typed judges on one claim set (task 8.5a; spec ``claim-judge-strategies``).

One claim set goes through ``clef_flash`` and then ``granite_guardian`` on the
same verify call path, against a fake router that serves both models with
only one loaded at a time (as the 24 GB pod will). No model is downloaded:
the real-model check is task 10.6.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.fixtures.decision.gguf import header_with_type

from omrs import compose_judges
from omrs.core.answer.verify import run_verification_stage
from omrs.core.settings import EffectiveSettings
from omrs.integrations.llamacpp_runtime import ModelUnavailable

_ANSWER = "Water boils at 100 C [1]. The moon is made of cheese [2]. Ice is cold [3]."
_EVIDENCE = [
    {"ordinal": 1, "text": "At sea level water boils at 100 C."},
    {"ordinal": 2, "text": "The moon is rock and dust."},
    {"ordinal": 3, "text": "Ice is frozen water and feels cold."},
]
#: Per claim (by a word in it): Clef-Flash P(yes) and the Granite score.
_TRUTH = {"boils": (0.91, "no"), "cheese": (0.08, "yes"), "cold": (0.77, "no")}


class SwappingRouter:
    """A fake router lease: one model loaded at a time, a swap logged on each change.

    ``down`` names models it cannot serve (``ModelUnavailable``, nothing sent).
    """

    def __init__(self, down: frozenset[str] = frozenset()) -> None:
        self.loaded: str | None = None
        self.swaps: list[str] = []
        self.requests: list[tuple[str, str]] = []
        self.down = down

    def request_model(self, model: str, send: Callable[[str], Any]) -> Any:
        if model in self.down:
            raise ModelUnavailable(model, "model-not-listed")
        if self.loaded != model:
            self.loaded = model
            self.swaps.append(model)
        return send("http://127.0.0.1:9/v1")

    def transport(self) -> httpx.MockTransport:
        def respond(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == self.loaded, "a request reached a model that is not loaded"
            self.requests.append((body["model"], request.url.path))
            text = body["state"]["text"] if "state" in body else body["prompt"]
            p_yes, score = next(v for k, v in _TRUTH.items() if k in text)
            if request.url.path == "/v1/systemone":
                return httpx.Response(200, json={"answers": {"fidelity": {"noul": p_yes}}})
            return httpx.Response(200, json={"choices": [{"text": f"<score> {score} </score>"}]})

        return httpx.MockTransport(respond)


def _settings(tmp_path: Path) -> EffectiveSettings:
    files = {}
    for name in ("clef-flash", "granite-guardian"):
        path = tmp_path / f"{name}.gguf"
        path.write_bytes(header_with_type("Q8_0"))
        files[name] = {"model": name, "file": str(path)}
    base = EffectiveSettings()
    answer = base.answer.model_copy(update={"verify_claims": True})
    return base.model_copy(update={"answer": answer, "llamacpp_models": files})


def _panel(settings: EffectiveSettings, router: SwappingRouter, monkeypatch: Any) -> list[Any]:
    """Build one judge per strategy from copies of the answer block (design D10)."""
    monkeypatch.setattr("omrs.compose_runtimes.router_lease_for", lambda _s: router)
    judges = []
    for strategy, model in (("clef_flash", "clef-flash"), ("granite_guardian", "granite-guardian")):
        block = settings.answer.model_copy(update={"verify_judge": strategy, "verify_model": model})
        judges.append(
            compose_judges.build_judge_target(settings, block, transport=router.transport())
        )
    return judges


def _run_panel(judges: list[Any]) -> list[Any]:
    async def run() -> list[Any]:
        return [
            await run_verification_stage(
                _ANSWER, _EVIDENCE, verify_complete=j, unavailable_reason=None, error_detail=str
            )
            for j in judges
        ]

    return asyncio.run(run())


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMRS_STATE_DIR", str(tmp_path / "state"))


def test_both_verdicts_are_recorded_for_every_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    router = SwappingRouter()
    clef, granite = _run_panel(_panel(_settings(tmp_path), router, monkeypatch))

    assert [c["strategy"] for c in clef.judge_calls] == ["clef_flash"] * 3
    assert [c["strategy"] for c in granite.judge_calls] == ["granite_guardian"] * 3
    assert [c["p_yes"] for c in clef.judge_calls] == [0.91, 0.08, 0.77]
    assert [f["verdict"] for f in clef.failing] == ["unsupported"]
    assert [f["verdict"] for f in granite.failing] == ["unsupported"]
    assert clef.failing[0]["claim"] == granite.failing[0]["claim"] == "The moon is made of cheese."


def test_the_swap_between_judges_keeps_the_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    router = SwappingRouter()
    _run_panel(_panel(_settings(tmp_path), router, monkeypatch))
    assert router.swaps == ["clef-flash", "granite-guardian"]
    assert (
        router.requests
        == [("clef-flash", "/v1/systemone")] * 3 + [("granite-guardian", "/v1/completions")] * 3
    )


def test_an_unreachable_second_model_keeps_the_first_verdicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    router = SwappingRouter(down=frozenset({"granite-guardian"}))
    clef, granite = _run_panel(_panel(_settings(tmp_path), router, monkeypatch))

    assert [c["p_yes"] for c in clef.judge_calls] == [0.91, 0.08, 0.77]
    assert clef.skipped_reason is None and len(clef.failing) == 1
    assert [c["error"] for c in granite.judge_calls] == ["model-not-listed"] * 3
    assert granite.skipped_reason == "claim judge granite_guardian could not run: model-not-listed"
    assert router.swaps == ["clef-flash"]
