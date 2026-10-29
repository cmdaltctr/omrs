"""Tests for ``download_files`` (add-model-search-and-download, task 3.3).

``hf_hub_download`` is replaced on ``huggingface_hub`` itself, because the
adapter imports it inside the function (ADR-024). A fake download calls the
``tqdm_class`` the way the library does. No test uses the network.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from omrs.integrations import huggingface_models as hf
from omrs.integrations.huggingface_models import (
    DownloadCancelled,
    ModelHostError,
    download_files,
)

REPO = "unsloth/Qwen3-4B-GGUF"
SHA = "22c9fc8a8c7700b76a1789366280a6a5a1ad1120"


def _install(monkeypatch: pytest.MonkeyPatch, fake: Callable[..., Any]) -> None:
    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake)


def _install_abort(monkeypatch: pytest.MonkeyPatch, abort: Callable[[], None]) -> None:
    from huggingface_hub.utils import _xet

    monkeypatch.setattr(_xet, "abort_xet_session", abort)


def _call(
    filenames: list[str],
    *,
    on_bytes: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
    token: str | None = None,
) -> str:
    return download_files(
        REPO,
        SHA,
        filenames,
        on_bytes=on_bytes or (lambda n: None),
        cancel=cancel or threading.Event(),
        token=token,
    )


def _hub_http_error(status: int) -> Exception:
    from huggingface_hub.errors import HfHubHTTPError

    response = httpx.Response(status, request=httpx.Request("GET", "https://huggingface.co/x"))
    return HfHubHTTPError("secret detail hf_abc", response=response)


class TestCalls:
    def test_one_call_per_file_in_order_at_the_pinned_revision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []

        def fake(**kwargs: Any) -> str:
            calls.append(kwargs)
            return f"/cache/{kwargs['filename']}"

        _install(monkeypatch, fake)

        path = _call(["a-00001-of-00002.gguf", "a-00002-of-00002.gguf"])

        assert [c["filename"] for c in calls] == ["a-00001-of-00002.gguf", "a-00002-of-00002.gguf"]
        assert all(c["repo_id"] == REPO and c["revision"] == SHA for c in calls)
        assert all(c["tqdm_class"] is not None for c in calls)
        assert not any(c.get("dry_run") for c in calls)
        assert path == "/cache/a-00001-of-00002.gguf"

    def test_token_is_passed_and_none_turns_the_stored_token_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tokens: list[object] = []

        def fake(**kwargs: Any) -> str:
            tokens.append(kwargs["token"])
            return "/p"

        _install(monkeypatch, fake)

        _call(["a.gguf"], token="hf_test_secret")  # noqa: S106
        _call(["a.gguf"], token=None)

        assert tokens == ["hf_test_secret", False]

    def test_byte_updates_reach_on_bytes_as_ints(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(**kwargs: Any) -> str:
            bar = kwargs["tqdm_class"](total=100, unit="B")
            bar.update(40)
            bar.update(2.0)
            bar.update(0)
            bar.update(None)
            bar.update(8)
            bar.close()
            return "/p"

        _install(monkeypatch, fake)
        seen: list[int] = []

        _call(["a.gguf"], on_bytes=seen.append)

        assert seen == [40, 2, 8]
        assert all(type(n) is int for n in seen)


class TestCancel:
    def test_cancel_during_update_raises_download_cancelled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cancel = threading.Event()

        def fake(**kwargs: Any) -> str:
            bar = kwargs["tqdm_class"](total=100, unit="B")
            bar.update(10)
            cancel.set()
            bar.update(10)
            raise AssertionError("update must have raised")

        _install(monkeypatch, fake)

        with pytest.raises(DownloadCancelled):
            _call(["a.gguf"], cancel=cancel)

    def test_cancel_is_checked_between_files(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cancel = threading.Event()
        calls: list[str] = []

        def fake(**kwargs: Any) -> str:
            calls.append(kwargs["filename"])
            cancel.set()
            return "/p"

        _install(monkeypatch, fake)

        with pytest.raises(DownloadCancelled):
            _call(["a.gguf", "b.gguf"], cancel=cancel)

        assert calls == ["a.gguf"]

    def test_cancel_set_before_the_start_calls_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cancel = threading.Event()
        cancel.set()
        calls: list[str] = []
        _install(monkeypatch, lambda **kw: calls.append("x") or "/p")

        with pytest.raises(DownloadCancelled):
            _call(["a.gguf"], cancel=cancel)

        assert calls == []

    def test_cancel_aborts_the_xet_session_and_raises_download_cancelled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A Xet-like call blocks and swallows callback errors; only the abort frees it."""
        cancel = threading.Event()
        aborted = threading.Event()
        blocking = threading.Event()

        def abort() -> None:
            aborted.set()

        def fake(**kwargs: Any) -> str:
            blocking.set()
            assert aborted.wait(5), "the watcher never called the abort"
            raise RuntimeError("xet session aborted")

        _install(monkeypatch, fake)
        _install_abort(monkeypatch, abort)

        def trigger() -> None:
            blocking.wait(5)
            cancel.set()

        threading.Thread(target=trigger, daemon=True).start()

        with pytest.raises(DownloadCancelled):
            _call(["a.gguf"], cancel=cancel)

        assert aborted.is_set()

    def test_watcher_does_not_abort_after_a_normal_finish(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cancel = threading.Event()
        aborts: list[int] = []
        _install(monkeypatch, lambda **kw: "/p")
        _install_abort(monkeypatch, lambda: aborts.append(1))

        _call(["a.gguf"], cancel=cancel)
        cancel.set()  # a later cancel, for a later download
        threading.Event().wait(0.1)

        assert aborts == []

    def test_watcher_thread_ends_with_the_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        before = threading.active_count()
        _install(monkeypatch, lambda **kw: "/p")

        _call(["a.gguf"])
        threading.Event().wait(0.1)

        assert threading.active_count() == before

    def test_missing_abort_function_only_loses_the_fast_stop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from huggingface_hub.utils import _xet

        monkeypatch.delattr(_xet, "abort_xet_session")
        cancel = threading.Event()
        started = threading.Event()

        def fake(**kwargs: Any) -> str:
            started.set()
            bar = kwargs["tqdm_class"](total=1, unit="B")
            cancel.set()
            threading.Event().wait(0.1)  # the watcher runs and finds no abort function
            bar.update(1)
            return "/p"

        _install(monkeypatch, fake)

        with pytest.raises(DownloadCancelled):
            _call(["a.gguf"], cancel=cancel)

    def test_a_failure_after_cancel_is_still_download_cancelled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cancel = threading.Event()

        def fake(**kwargs: Any) -> str:
            cancel.set()
            raise OSError("partial file removed")

        _install(monkeypatch, fake)

        with pytest.raises(DownloadCancelled):
            _call(["a.gguf"], cancel=cancel)


class TestErrors:
    @pytest.mark.parametrize(
        ("status", "reason"),
        [(401, "gated"), (403, "gated"), (404, "not-found"), (500, "network")],
    )
    def test_http_errors_map_to_reasons(
        self, monkeypatch: pytest.MonkeyPatch, status: int, reason: str
    ) -> None:
        def fake(**kwargs: Any) -> str:
            raise _hub_http_error(status)

        _install(monkeypatch, fake)

        with pytest.raises(ModelHostError) as caught:
            _call(["a.gguf"])

        assert caught.value.reason == reason
        assert str(caught.value) == reason

    def test_other_errors_map_to_network_without_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake(**kwargs: Any) -> str:
            raise OSError("/Users/x/secret path")

        _install(monkeypatch, fake)

        with pytest.raises(ModelHostError) as caught:
            _call(["a.gguf"])

        assert str(caught.value) == "network"
        assert caught.value.__suppress_context__ is True


def test_download_cancelled_notes_that_the_partial_file_is_lost() -> None:
    assert "from zero" in (DownloadCancelled.__doc__ or "")


def test_the_xet_abort_function_exists() -> None:
    """Pin the private ``abort_xet_session``.

    ``download_files`` calls it to stop a Xet transfer, because ``hf_xet``
    swallows errors raised from the progress callback. A library upgrade that
    removes it must fail here, so the loss of the fast stop is seen in CI.
    """
    from huggingface_hub.utils import _xet

    assert callable(_xet.abort_xet_session)


def test_adapter_module_still_has_no_top_level_hub_import() -> None:
    assert "huggingface_hub" not in vars(hf)
