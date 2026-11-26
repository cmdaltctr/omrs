"""The GLM-5.3 endpoint (Z.ai API) of Exp 35 stays out of every file (owner, 2026-11-26).

Rules under test: the base URL comes from ``OMRS_EXP35_ZAI_BASE_URL`` or the owner's file
outside the repository; a missing value stops the stage and the message names the
variable, never a value; a value whose SHA-256 differs from ``plan.json``
``pins.glm_judge.base_url_sha256`` is refused; a judge stage run with a fake URL writes
the URL to no file; no tracked Experiment 35 file holds the Z.ai host.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import ROOT, fake_plan, load
from tests.test_experiment35_run_arms import env as env  # noqa: F401 - the shared fixture
from tests.test_experiment35_run_stages import RERANK, RunStub, _run, _sealed

arms = load("arms")
run_arms = load("run_arms")
zai35 = load("zai35")

FAKE = "https://fake-zai.example.invalid/api/v9-LEAKCHECK"
FOLDER = "experiments/35-full-rag-benchmark-2026-11-01"


def _plan(url: str = FAKE) -> dict[str, Any]:
    plan = fake_plan()
    plan["pins"]["glm_judge"] = {"base_url_sha256": zai35.url_sha256(url)}
    return plan


@pytest.fixture
def no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "none" / zai35.FILE_NAME
    monkeypatch.setattr(zai35, "base_url_file", lambda: path)
    return path


def test_a_missing_base_url_names_the_variable(no_file: Path) -> None:
    with pytest.raises(zai35.EndpointError, match=zai35.BASE_URL_ENV) as error:
        zai35.base_url(_plan(), environ={})
    assert "http" not in str(error.value)


def test_a_url_with_another_hash_is_refused_and_not_printed(no_file: Path) -> None:
    other = "https://other.example.invalid/v4"
    with pytest.raises(zai35.EndpointError, match="base_url_sha256") as error:
        zai35.base_url(_plan(), environ={zai35.BASE_URL_ENV: other})
    assert other not in str(error.value) and FAKE not in str(error.value)


def test_the_pinned_url_is_returned_from_the_environment_or_the_file(no_file: Path) -> None:
    assert zai35.base_url(_plan(), environ={zai35.BASE_URL_ENV: FAKE}) == FAKE
    no_file.parent.mkdir(parents=True)
    no_file.write_text(FAKE + "\n", encoding="utf-8")
    assert zai35.base_url(_plan(), environ={}) == FAKE


def test_a_plan_without_the_pin_is_refused(no_file: Path) -> None:
    plan = fake_plan()
    del plan["pins"]["glm_judge"]
    with pytest.raises(zai35.EndpointError, match="base_url_sha256"):
        zai35.base_url(plan, environ={zai35.BASE_URL_ENV: FAKE})


def test_the_scratch_settings_hold_no_base_url(gguf: Path) -> None:
    values = arms.settings_values(
        arms.parse_setup("e4b-c512-roff-hoff"), _plan(), gguf, answer_host="", judges=("chat",)
    )
    assert "openai_compatible_base_url" not in values
    assert values["openai_compatible_api_key"] == f"env://{arms.GLM_KEY_ENV}"


@pytest.fixture
def gguf(tmp_path: Path) -> Path:
    from tests._exp35_fixtures import make_gguf

    return make_gguf(tmp_path / "gguf")


def test_a_judge_stage_with_a_fake_url_writes_it_to_no_file(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    async def capture(ctx: Any) -> int:
        seen.append(ctx.settings.openai_compatible_base_url)
        return 0

    monkeypatch.setitem(run_arms.STAGE_TABLE, "judge", capture)
    monkeypatch.setenv(zai35.BASE_URL_ENV, FAKE)
    monkeypatch.setenv(arms.GLM_KEY_ENV, "zai-test-key")
    stub = RunStub()
    stub.plan()["pins"]["glm_judge"] = {"base_url_sha256": zai35.url_sha256(FAKE)}
    stub.router = lambda entry: entry  # type: ignore[attr-defined]
    stub.runtime_check = lambda entry, url: {}  # type: ignore[attr-defined]
    out = env / "out"
    _sealed(env, stub, out)
    args = ("--setup", RERANK, "--stage", "judge", "--judges", "chat", "--prefreeze")
    assert _run(stub, out, *args) == 0
    assert seen == [FAKE]  # OMRS got the URL through the process environment
    written = [p for p in env.rglob("*") if p.is_file()]
    assert any(p.name == "omrs.jsonc" for p in written)  # the scratch settings were checked
    leaks = [str(p) for p in written if FAKE.encode() in p.read_bytes()]
    assert leaks == []


def test_no_tracked_experiment_35_file_holds_the_zai_host() -> None:
    found = subprocess.run(
        ["git", "-C", str(ROOT), "grep", "-l", "-F", "api.z.ai", "--", FOLDER],
        capture_output=True,
        text=True,
        check=False,
    )
    assert found.returncode == 1, found.stdout  # 1: no match
