"""The one model download job on the web runtime (tasks 5.1 to 5.3).

Fake adapters stand in for Hugging Face and Ollama. No test reaches the
network, a real cache or a real Ollama. The stall test uses a fake clock.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

import pytest

pytest.importorskip("fastapi")

from omrs.integrations import huggingface_models, ollama_pull  # noqa: E402
from omrs.transports.api import model_download_job as job_module  # noqa: E402
from omrs.transports.api.model_download_job import (  # noqa: E402
    ADAPTERS,
    DownloadBusy,
    DownloadRequest,
    ModelDownloadJob,
    Progress,
)

HF_VALUE = "hf_test_secret"  # gitleaks:allow
STATUS_KEYS = {
    "state",
    "provider",
    "model",
    "model_value",
    "bytes_done",
    "bytes_total",
    "reason",
    "cache_folder",
}


def request(**overrides: Any) -> DownloadRequest:
    base: dict[str, Any] = {
        "kind": "huggingface-gguf",
        "provider": "llamacpp",
        "display": "org/name:Q4_K_M",
        "model_value": "org/name:Q4_K_M",
        "bytes_total": 1000,
        "cache_folder": "~/.cache/huggingface/hub",
        "repo": "org/name",
        "revision": "a" * 40,
        "files": ("model-Q4_K_M.gguf",),
    }
    return DownloadRequest(**{**base, **overrides})


class Fake:
    """A blocking fake adapter that the test steps with events."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls: list[tuple[DownloadRequest, threading.Event]] = []
        self.steps: list[int] = []
        self.error: BaseException | None = None
        self.obey_cancel = True

    def __call__(self, req: DownloadRequest, progress: Progress, cancel: threading.Event) -> None:
        self.calls.append((req, cancel))
        for step in self.steps:
            progress.add(step)
        self.started.set()
        while not self.release.is_set():
            if cancel.is_set() and self.obey_cancel:
                raise huggingface_models.DownloadCancelled
            time.sleep(0.005)
        if self.error is not None:
            raise self.error


def make_job(fake: Fake, **kwargs: Any) -> ModelDownloadJob:
    adapters = {"huggingface-gguf": fake, "ollama-pull": fake}
    return ModelDownloadJob(adapters=adapters, **kwargs)  # type: ignore[arg-type]


async def until(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not met"
        await asyncio.sleep(0.005)


async def settle(job: ModelDownloadJob) -> dict[str, Any]:
    await job.wait(timeout=5.0)
    return job.snapshot()


# ── State and table ──────────────────────────────────────────────────────


def test_a_new_job_is_idle_with_every_key() -> None:
    snapshot = ModelDownloadJob().snapshot()
    assert set(snapshot) == STATUS_KEYS
    assert snapshot["state"] == "idle"
    assert snapshot["bytes_done"] == 0
    assert snapshot["bytes_total"] is None
    assert snapshot["provider"] is None and snapshot["model"] is None
    assert snapshot["reason"] is None and snapshot["cache_folder"] is None


def test_a_new_runtime_has_its_own_idle_job() -> None:
    from omrs.transports.api.lifespan import WebRuntime

    first = WebRuntime.__dataclass_fields__["model_downloads"].default_factory()
    second = WebRuntime.__dataclass_fields__["model_downloads"].default_factory()
    assert first is not second
    assert first.snapshot()["state"] == "idle"


def test_the_adapter_table_has_one_entry_for_each_source_kind() -> None:
    assert set(ADAPTERS) == {"huggingface-gguf", "ollama-pull"}


# ── Run, progress, busy ──────────────────────────────────────────────────


async def test_status_snapshots_show_growing_bytes_then_success() -> None:
    fake = Fake()
    fake.steps = [100]
    job = make_job(fake)
    job.start(request())
    await until(fake.started.is_set)
    first = job.snapshot()
    assert first["state"] == "running"
    assert first["bytes_done"] == 100 and first["bytes_total"] == 1000
    assert first["model"] == "org/name:Q4_K_M" and first["provider"] == "llamacpp"
    assert first["model_value"] is None and first["reason"] is None
    assert first["cache_folder"] == "~/.cache/huggingface/hub"
    fake.release.set()
    done = await settle(job)
    assert done["state"] == "succeeded"
    assert done["model_value"] == "org/name:Q4_K_M"
    assert done["reason"] is None


async def test_bytes_grow_between_reads_while_the_job_runs() -> None:
    gate = threading.Event()
    seen = threading.Event()

    def adapter(req: DownloadRequest, progress: Progress, cancel: threading.Event) -> None:
        progress.add(10)
        seen.set()
        gate.wait(5)
        progress.add(90)

    job = ModelDownloadJob(adapters={"huggingface-gguf": adapter, "ollama-pull": adapter})
    job.start(request())
    await until(seen.is_set)
    before = job.snapshot()["bytes_done"]
    gate.set()
    await job.wait(timeout=5.0)
    assert (before, job.snapshot()["bytes_done"]) == (10, 100)


async def test_a_second_start_is_busy_and_the_first_keeps_running() -> None:
    fake = Fake()
    job = make_job(fake)
    job.start(request())
    await until(fake.started.is_set)
    with pytest.raises(DownloadBusy):
        job.start(request(display="other/model:Q8_0"))
    assert job.running
    assert job.snapshot()["model"] == "org/name:Q4_K_M"
    assert len(fake.calls) == 1
    fake.release.set()
    assert (await settle(job))["state"] == "succeeded"


async def test_a_new_job_can_start_after_the_last_one_ended() -> None:
    fake = Fake()
    fake.release.set()
    job = make_job(fake)
    job.start(request())
    await settle(job)
    job.start(request(display="again/model:Q8_0", model_value="again/model:Q8_0"))
    done = await settle(job)
    assert done["model"] == "again/model:Q8_0" and done["state"] == "succeeded"


async def test_the_ollama_progress_sets_done_and_the_total_when_known() -> None:
    def adapter(req: DownloadRequest, progress: Progress, cancel: threading.Event) -> None:
        progress.update(5, None)
        assert job.snapshot()["bytes_total"] is None
        progress.update(50, 200)

    job = ModelDownloadJob(adapters={"huggingface-gguf": adapter, "ollama-pull": adapter})
    job.start(request(kind="ollama-pull", provider="ollama", bytes_total=None, cache_folder=None))
    done = await settle(job)
    assert (done["bytes_done"], done["bytes_total"]) == (50, 200)
    assert done["cache_folder"] is None


# ── Cancel ───────────────────────────────────────────────────────────────


async def test_cancel_sets_the_event_and_ends_cancelled_within_five_seconds() -> None:
    fake = Fake()
    job = make_job(fake)
    job.start(request())
    await until(fake.started.is_set)
    began = time.monotonic()
    assert job.cancel() is True
    assert fake.calls[0][1].is_set()
    done = await settle(job)
    assert time.monotonic() - began < 5
    assert done["state"] == "cancelled" and done["reason"] is None
    assert done["model_value"] is None


async def test_cancel_with_no_running_job_changes_nothing() -> None:
    job = ModelDownloadJob()
    assert job.cancel() is False
    assert job.snapshot()["state"] == "idle"


async def test_cancel_after_the_job_ended_returns_false() -> None:
    fake = Fake()
    fake.release.set()
    job = make_job(fake)
    job.start(request())
    await settle(job)
    assert job.cancel() is False
    assert job.snapshot()["state"] == "succeeded"


async def test_a_worker_that_ignores_cancel_still_ends_cancelled_after_the_grace() -> None:
    fake = Fake()
    fake.obey_cancel = False
    job = make_job(fake, cancel_grace=0.05)
    job.start(request())
    await until(fake.started.is_set)
    job.cancel()
    done = await settle(job)
    assert done["state"] == "cancelled"
    fake.release.set()  # let the lingering thread end


async def test_the_lingering_thread_of_a_cancelled_job_does_not_change_the_next_one() -> None:
    old = Fake()
    old.obey_cancel = False
    job = make_job(old, cancel_grace=0.05)
    job.start(request())
    await until(old.started.is_set)
    job.cancel()
    await settle(job)
    new = Fake()
    new.release.set()
    job.adapters = {"huggingface-gguf": new, "ollama-pull": new}  # type: ignore[assignment]
    job.start(request(display="next/model:Q8_0", model_value="next/model:Q8_0"))
    await settle(job)
    old.release.set()
    await asyncio.sleep(0.05)
    done = job.snapshot()
    assert done["state"] == "succeeded" and done["model"] == "next/model:Q8_0"


async def test_stop_cancels_a_running_job_and_waits() -> None:
    fake = Fake()
    job = make_job(fake)
    job.start(request())
    await until(fake.started.is_set)
    await job.stop(timeout=5.0)
    assert job.snapshot()["state"] == "cancelled"
    assert not job.running


async def test_stop_on_an_idle_job_returns_at_once() -> None:
    await asyncio.wait_for(ModelDownloadJob().stop(timeout=5.0), 1)


# ── Shutdown (task 5.2) ──────────────────────────────────────────────────


def bare_runtime(job: ModelDownloadJob) -> Any:
    from types import SimpleNamespace

    from omrs.transports.api.lifespan import WebRuntime

    engine = SimpleNamespace(close=lambda: None)
    return WebRuntime(
        config=None,  # type: ignore[arg-type]
        engine=engine,
        grants=None,  # type: ignore[arg-type]
        uploads=None,  # type: ignore[arg-type]
        model_downloads=job,
    )


async def test_shutdown_stops_a_running_download_before_it_returns() -> None:
    from omrs.transports.api.lifespan import shutdown_runtime

    fake = Fake()
    job = make_job(fake)
    job.start(request())
    await until(fake.started.is_set)
    try:
        await asyncio.wait_for(shutdown_runtime(bare_runtime(job)), 6)
        assert fake.calls[0][1].is_set()
        assert job.snapshot()["state"] == "cancelled"
    finally:
        fake.release.set()


async def test_shutdown_does_not_wait_longer_than_five_seconds_for_a_stuck_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omrs.transports.api.lifespan import shutdown_runtime

    fake = Fake()
    fake.obey_cancel = False
    job = make_job(fake, cancel_grace=30.0)
    job.start(request())
    await until(fake.started.is_set)
    real_stop = job.stop
    asked: list[float] = []

    async def stop(timeout: float = 5.0) -> None:
        asked.append(timeout)
        await real_stop(timeout=0.05)

    monkeypatch.setattr(job, "stop", stop)
    try:
        await shutdown_runtime(bare_runtime(job))
        assert asked == [5.0]
    finally:
        fake.release.set()


# ── Stall ────────────────────────────────────────────────────────────────


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_sixty_seconds_without_a_byte_fails_the_job_as_stalled() -> None:
    fake = Fake()
    clock = Clock()
    job = make_job(fake, clock=clock, watch_interval=0.005)
    job.start(request())
    await until(fake.started.is_set)
    clock.now += 59.0
    await asyncio.sleep(0.05)
    assert job.snapshot()["state"] == "running"
    clock.now += 2.0
    done = await settle(job)
    assert done["state"] == "failed" and done["reason"] == "stalled"
    assert fake.calls[0][1].is_set()


async def test_a_byte_resets_the_stall_clock() -> None:
    fake = Fake()
    clock = Clock()
    holder: dict[str, Progress] = {}

    def adapter(req: DownloadRequest, progress: Progress, cancel: threading.Event) -> None:
        holder["progress"] = progress
        fake(req, progress, cancel)

    job = ModelDownloadJob(
        adapters={"huggingface-gguf": adapter, "ollama-pull": adapter},
        clock=clock,
        watch_interval=0.005,
    )
    job.start(request())
    await until(fake.started.is_set)
    clock.now += 50.0
    holder["progress"].add(1)
    clock.now += 50.0
    await asyncio.sleep(0.05)
    assert job.snapshot()["state"] == "running"
    fake.release.set()
    assert (await settle(job))["state"] == "succeeded"


# ── Errors map to fixed reasons ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (huggingface_models.ModelHostError("network"), "network"),
        (huggingface_models.ModelHostError("not-found"), "not-found"),
        (huggingface_models.ModelHostError("gated"), "gated"),
        (ollama_pull.OllamaPullError("ollama-unreachable"), "ollama-unreachable"),
        (ollama_pull.OllamaPullError("failed"), "failed"),
        (RuntimeError("anything else"), "failed"),
        (OSError(28, "No space left on device"), "failed"),
    ],
)
async def test_adapter_errors_map_to_the_fixed_reasons(error: BaseException, reason: str) -> None:
    fake = Fake()
    fake.error = error
    fake.release.set()
    job = make_job(fake)
    job.start(request())
    done = await settle(job)
    assert done["state"] == "failed" and done["reason"] == reason
    assert done["model_value"] is None


async def test_an_error_after_cancel_still_reports_cancelled() -> None:
    fake = Fake()
    fake.obey_cancel = False
    fake.error = huggingface_models.ModelHostError("network")
    job = make_job(fake)
    job.start(request())
    await until(fake.started.is_set)
    job.cancel()
    fake.release.set()
    assert (await settle(job))["state"] == "cancelled"


# ── The real adapters call the integration modules ───────────────────────


async def test_the_hugging_face_adapter_passes_the_pinned_files_and_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def download_files(repo: str, revision: str, filenames: Any, **kwargs: Any) -> str:
        calls.append({"repo": repo, "revision": revision, "files": tuple(filenames), **kwargs})
        kwargs["on_bytes"](7)
        return "/cache/x"

    monkeypatch.setattr(huggingface_models, "download_files", download_files)
    job = ModelDownloadJob()
    job.start(request(token=HF_VALUE, files=("a-00001-of-00002.gguf", "a-00002-of-00002.gguf")))
    done = await settle(job)
    assert done["state"] == "succeeded" and done["bytes_done"] == 7
    assert calls[0]["repo"] == "org/name" and calls[0]["revision"] == "a" * 40
    assert calls[0]["files"] == ("a-00001-of-00002.gguf", "a-00002-of-00002.gguf")
    assert calls[0]["token"] == HF_VALUE
    assert isinstance(calls[0]["cancel"], threading.Event)


async def test_the_ollama_adapter_passes_the_address_and_the_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def pull_model(base_url: str, name: str, *, on_progress: Any, cancel: Any) -> None:
        calls.append((base_url, name))
        on_progress(30, 60)

    monkeypatch.setattr(ollama_pull, "pull_model", pull_model)
    job = ModelDownloadJob()
    job.start(
        request(
            kind="ollama-pull",
            provider="ollama",
            display="qwen3:4b",
            model_value="qwen3:4b",
            name="qwen3:4b",
            base_url="http://127.0.0.1:11434",
            cache_folder=None,
            bytes_total=None,
        )
    )
    done = await settle(job)
    assert calls == [("http://127.0.0.1:11434", "qwen3:4b")]
    assert (done["state"], done["bytes_done"], done["bytes_total"]) == ("succeeded", 30, 60)


async def test_the_cancel_exceptions_of_both_adapters_end_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def hf(*args: Any, **kwargs: Any) -> str:
        raise huggingface_models.DownloadCancelled

    def pull(*args: Any, **kwargs: Any) -> None:
        raise ollama_pull.PullCancelled

    monkeypatch.setattr(huggingface_models, "download_files", hf)
    monkeypatch.setattr(ollama_pull, "pull_model", pull)
    job = ModelDownloadJob()
    job.start(request())
    assert (await settle(job))["state"] == "cancelled"
    job.start(request(kind="ollama-pull", provider="ollama", name="x", base_url="http://h"))
    assert (await settle(job))["state"] == "cancelled"


# ── Secrets and exception text (task 5.3) ────────────────────────────────


async def test_no_status_or_log_line_holds_the_token_or_the_exception_text(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", HF_VALUE)
    text = f"boom path=/Users/someone/secret token={HF_VALUE} Authorization: Bearer {HF_VALUE}"

    def download_files(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError(text)

    monkeypatch.setattr(huggingface_models, "download_files", download_files)
    caplog.set_level(logging.INFO)
    job = ModelDownloadJob()
    job.start(request(token=HF_VALUE))
    done = await settle(job)
    assert done["state"] == "failed" and done["reason"] == "failed"
    everything = repr(done) + caplog.text
    assert HF_VALUE not in everything
    assert "boom" not in everything and "/Users/someone" not in everything


async def test_the_token_and_the_error_text_stay_out_of_a_debug_log_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def adapter(req: DownloadRequest, progress: Progress, cancel: threading.Event) -> None:
        raise huggingface_models.ModelHostError(f"detail {HF_VALUE}")

    caplog.set_level(logging.DEBUG)
    job = ModelDownloadJob(adapters={"huggingface-gguf": adapter, "ollama-pull": adapter})
    job.start(request(token=HF_VALUE))
    await settle(job)
    assert HF_VALUE not in caplog.text


async def test_a_logged_name_goes_through_redact(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    real = job_module.redact

    def spy(text: str, extra: Any = ()) -> str:
        seen.append(text)
        return real(text, extra)

    monkeypatch.setattr(job_module, "redact", spy)
    fake = Fake()
    fake.release.set()
    caplog.set_level(logging.INFO)
    job = make_job(fake)
    job.start(request())
    await settle(job)
    assert seen, "log text did not pass through redact"


async def test_the_token_is_removed_from_a_logged_name(caplog: pytest.LogCaptureFixture) -> None:
    fake = Fake()
    fake.release.set()
    caplog.set_level(logging.INFO)
    job = make_job(fake)
    job.start(request(display=f"org/{HF_VALUE}:Q4_K_M", token=HF_VALUE))
    await settle(job)
    assert "Model download of" in caplog.text
    assert HF_VALUE not in caplog.text


# ── A check that fails before the transfer ───────────────────────────────


async def test_fail_records_a_failed_job_and_runs_no_adapter() -> None:
    fake = Fake()
    job = make_job(fake)
    job.fail(request(), "network")
    done = job.snapshot()
    assert done["state"] == "failed" and done["reason"] == "network"
    assert done["model"] == "org/name:Q4_K_M" and done["model_value"] is None
    assert not job.running and fake.calls == []
    fake.release.set()
    job.start(request())
    assert (await settle(job))["state"] == "succeeded"


async def test_fail_is_busy_while_a_download_runs() -> None:
    fake = Fake()
    job = make_job(fake)
    job.start(request())
    await until(fake.started.is_set)
    with pytest.raises(DownloadBusy):
        job.fail(request(), "network")
    assert job.snapshot()["state"] == "running"
    fake.release.set()
    await settle(job)
