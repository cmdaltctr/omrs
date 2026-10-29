"""Tests for the Ollama pull adapter (add-model-search-and-download, task 4.1).

Every request goes through ``httpx.MockTransport``. No test needs an Ollama
server.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator

import httpx
import pytest

from omrs.integrations.ollama_pull import OllamaPullError, PullCancelled, pull_model

BASE = "http://127.0.0.1:11434"


def _lines(*records: object) -> bytes:
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


class _Stream(httpx.SyncByteStream):
    """A response body that yields one line at a time and records its close."""

    def __init__(self, records: list[object], on_line: Callable[[int], None] | None = None) -> None:
        self._records = records
        self._on_line = on_line
        self.closed = False
        self.yielded = 0

    def __iter__(self) -> Iterator[bytes]:
        for index, record in enumerate(self._records):
            self.yielded += 1
            yield json.dumps(record).encode() + b"\n"
            if self._on_line is not None:
                self._on_line(index)

    def close(self) -> None:
        self.closed = True


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _serving(*records: object) -> httpx.Client:
    return _client(lambda request: httpx.Response(200, content=_lines(*records)))


def _pull(
    client: httpx.Client,
    *,
    progress: list[tuple[int, int | None]] | None = None,
    cancel: threading.Event | None = None,
    name: str = "qwen3:0.6b",
) -> None:
    sink = progress if progress is not None else []
    pull_model(
        BASE,
        name,
        on_progress=lambda done, total: sink.append((done, total)),
        cancel=cancel or threading.Event(),
        client=client,
    )


class TestRequest:
    """One POST with the fixed JSON body."""

    def test_sends_one_post_with_stream_true(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content=_lines({"status": "success"}))

        _pull(_client(handler))

        assert len(seen) == 1
        assert seen[0].method == "POST"
        assert str(seen[0].url) == f"{BASE}/api/pull"
        assert json.loads(seen[0].content) == {"model": "qwen3:0.6b", "stream": True}

    def test_trailing_slash_on_the_base_is_dropped(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, content=_lines({"status": "success"}))

        pull_model(
            BASE + "/",
            "m",
            on_progress=lambda d, t: None,
            cancel=threading.Event(),
            client=_client(handler),
        )

        assert seen == [f"{BASE}/api/pull"]

    def test_hf_name_is_sent_unchanged(self) -> None:
        seen: list[object] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content)["model"])
            return httpx.Response(200, content=_lines({"status": "success"}))

        _pull(_client(handler), name="hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M")

        assert seen == ["hf.co/unsloth/Qwen3-4B-GGUF:Q4_K_M"]

    def test_does_not_follow_redirects(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.host)
            return httpx.Response(302, headers={"location": "http://evil.example/api/pull"})

        with pytest.raises(OllamaPullError) as caught:
            _pull(_client(handler))

        assert caught.value.reason == "failed"
        assert seen == ["127.0.0.1"]


class TestProgress:
    """Progress is summed over the layer digests."""

    def test_sums_completed_over_the_total_of_each_digest(self) -> None:
        client = _serving(
            {"status": "pulling manifest"},
            {"status": "pulling aaa", "digest": "sha256:aaa", "total": 100, "completed": 10},
            {"status": "pulling aaa", "digest": "sha256:aaa", "total": 100, "completed": 60},
            {"status": "pulling bbb", "digest": "sha256:bbb", "total": 50, "completed": 5},
            {"status": "pulling aaa", "digest": "sha256:aaa", "total": 100, "completed": 100},
            {"status": "pulling bbb", "digest": "sha256:bbb", "total": 50, "completed": 50},
            {"status": "success"},
        )
        progress: list[tuple[int, int | None]] = []

        _pull(client, progress=progress)

        assert progress == [
            (10, 100),
            (60, 100),
            (65, 150),
            (105, 150),
            (150, 150),
        ]

    def test_a_layer_with_no_completed_counts_zero(self) -> None:
        client = _serving(
            {"status": "pulling aaa", "digest": "sha256:aaa", "total": 100},
            {"status": "success"},
        )
        progress: list[tuple[int, int | None]] = []

        _pull(client, progress=progress)

        assert progress == [(0, 100)]

    def test_status_only_lines_report_nothing(self) -> None:
        progress: list[tuple[int, int | None]] = []

        _pull(
            _serving({"status": "pulling manifest"}, {"status": "success"}),
            progress=progress,
        )

        assert progress == []

    def test_lines_split_across_chunks_are_joined(self) -> None:
        raw = _lines(
            {"status": "pulling aaa", "digest": "sha256:aaa", "total": 9, "completed": 4},
            {"status": "success"},
        )

        def handler(request: httpx.Request) -> httpx.Response:
            class Split(httpx.SyncByteStream):
                def __iter__(self) -> Iterator[bytes]:
                    yield raw[:17]
                    yield raw[17:]

            return httpx.Response(200, stream=Split())

        progress: list[tuple[int, int | None]] = []

        _pull(_client(handler), progress=progress)

        assert progress == [(4, 9)]


class TestEnd:
    """How a pull ends."""

    def test_success_line_ends_the_pull(self) -> None:
        stream = _Stream([{"status": "success"}, {"status": "after success"}])

        _pull(_client(lambda request: httpx.Response(200, stream=stream)))

        assert stream.yielded == 1
        assert stream.closed is True

    def test_error_line_is_failed(self) -> None:
        client = _serving(
            {"status": "pulling manifest"},
            {"error": "pull model manifest: file does not exist /private/path"},
        )

        with pytest.raises(OllamaPullError) as caught:
            _pull(client)

        assert caught.value.reason == "failed"
        assert "private" not in str(caught.value)
        assert str(caught.value) == "failed"

    def test_error_line_fails_even_when_a_success_line_follows(self) -> None:
        with pytest.raises(OllamaPullError) as caught:
            _pull(_serving({"error": "boom"}, {"status": "success"}))

        assert caught.value.reason == "failed"

    def test_http_error_with_a_success_body_is_still_failed(self) -> None:
        client = _client(lambda request: httpx.Response(500, content=_lines({"status": "success"})))

        with pytest.raises(OllamaPullError) as caught:
            _pull(client)

        assert caught.value.reason == "failed"

    def test_stream_that_ends_without_success_is_failed(self) -> None:
        with pytest.raises(OllamaPullError) as caught:
            _pull(_serving({"status": "pulling manifest"}))

        assert caught.value.reason == "failed"

    @pytest.mark.parametrize("status", [400, 404, 500])
    def test_http_error_is_failed(self, status: int) -> None:
        client = _client(lambda request: httpx.Response(status, json={"error": "x"}))

        with pytest.raises(OllamaPullError) as caught:
            _pull(client)

        assert caught.value.reason == "failed"

    def test_line_that_is_not_json_is_failed(self) -> None:
        client = _client(lambda request: httpx.Response(200, content=b"not json\n"))

        with pytest.raises(OllamaPullError) as caught:
            _pull(client)

        assert caught.value.reason == "failed"

    def test_stream_that_breaks_midway_is_failed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            class Broken(httpx.SyncByteStream):
                def __iter__(self) -> Iterator[bytes]:
                    yield _lines({"status": "pulling manifest"})
                    raise httpx.ReadError("cut", request=request)

            return httpx.Response(200, stream=Broken())

        with pytest.raises(OllamaPullError) as caught:
            _pull(_client(handler))

        assert caught.value.reason == "failed"


class TestUnreachable:
    """A server that cannot be reached."""

    @pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ConnectTimeout])
    def test_refused_connection_is_ollama_unreachable(
        self, error: type[httpx.TransportError]
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise error("refused at 127.0.0.1:11434", request=request)

        with pytest.raises(OllamaPullError) as caught:
            _pull(_client(handler))

        assert caught.value.reason == "ollama-unreachable"
        assert str(caught.value) == "ollama-unreachable"

    def test_default_client_reaches_nothing_on_a_closed_port(self) -> None:
        with pytest.raises(OllamaPullError) as caught:
            pull_model(
                "http://127.0.0.1:9",
                "m",
                on_progress=lambda d, t: None,
                cancel=threading.Event(),
            )

        assert caught.value.reason == "ollama-unreachable"


class TestCancel:
    """A set cancel event closes the stream."""

    def test_cancel_set_during_the_pull_closes_the_stream(self) -> None:
        cancel = threading.Event()
        layer = {"status": "pulling aaa", "digest": "sha256:aaa", "total": 100}
        stream = _Stream(
            [{**layer, "completed": 10}, {**layer, "completed": 20}, {**layer, "completed": 30}]
        )
        progress: list[tuple[int, int | None]] = []

        def on_progress(done: int, total: int | None) -> None:
            progress.append((done, total))
            cancel.set()

        client = _client(lambda request: httpx.Response(200, stream=stream))

        with pytest.raises(PullCancelled):
            pull_model(BASE, "m", on_progress=on_progress, cancel=cancel, client=client)

        assert progress == [(10, 100)]
        assert stream.yielded == 1
        assert stream.closed is True

    def test_cancel_is_checked_on_a_line_with_no_progress(self) -> None:
        cancel = threading.Event()
        stream = _Stream(
            [{"status": "pulling manifest"}, {"status": "success"}],
            on_line=lambda index: cancel.set(),
        )
        client = _client(lambda request: httpx.Response(200, stream=stream))

        with pytest.raises(PullCancelled):
            pull_model(BASE, "m", on_progress=lambda d, t: None, cancel=cancel, client=client)

        assert stream.closed is True

    def test_cancel_set_before_the_start_sends_no_request(self) -> None:
        cancel = threading.Event()
        cancel.set()
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content=_lines({"status": "success"}))

        with pytest.raises(PullCancelled):
            _pull(_client(handler), cancel=cancel)

        assert seen == []

    def test_cancel_wins_over_a_later_error_line(self) -> None:
        cancel = threading.Event()
        stream = _Stream(
            [
                {"status": "pulling aaa", "digest": "sha256:aaa", "total": 10, "completed": 1},
                {"error": "boom"},
            ]
        )

        def on_progress(done: int, total: int | None) -> None:
            cancel.set()

        with pytest.raises(PullCancelled):
            pull_model(
                BASE,
                "m",
                on_progress=on_progress,
                cancel=cancel,
                client=_client(lambda request: httpx.Response(200, stream=stream)),
            )
