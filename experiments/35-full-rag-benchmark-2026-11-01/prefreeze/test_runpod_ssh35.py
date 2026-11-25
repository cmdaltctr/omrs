"""Checks on runpod_ssh35.py: the direct SSH address of a pod, read from the RunPod API.

Every reply is a fake: no test reaches RunPod or any other network host, and no test
creates, stops or deletes a pod. The record shape is the ``getPod`` reply of the RunPod
REST API v2 (https://api.runpod.io/v2/openapi.json, read 2026-11-24).
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest
import runpod_ssh35

KEY = "rpa_FAKE_KEY_VALUE_0451"
IP, PORT = "81.27.69.179", 22956
SSH = {"ip": IP, "private": 22, "public": PORT, "type": "tcp"}


def _pod(status: str = "RUNNING", *ports: dict[str, Any]) -> dict[str, Any]:
    return {"id": "pod123", "status": status, "runtime": {"uptime": 60, "ports": list(ports)}}


@pytest.mark.parametrize(
    ("pod", "want"),
    [
        (_pod("RUNNING", SSH), (IP, PORT)),
        (_pod("RUNNING", {**SSH, "private": 8888, "type": "http"}, SSH), (IP, PORT)),
        (_pod("RUNNING"), None),  # no mapping yet
        (_pod("RUNNING", {**SSH, "public": None}), None),
        (_pod("RUNNING", {**SSH, "ip": None}), None),
        (_pod("RUNNING", {**SSH, "ip": "10.0.4.7"}), None),  # a private address: no scp
        (_pod("RUNNING", {**SSH, "ip": "100.65.0.2"}), None),  # carrier-grade NAT
        (_pod("RUNNING", {**SSH, "type": "udp"}), None),
        (_pod("RUNNING", {**SSH, "private": 2222}), None),
        (_pod("CREATED", SSH), None),  # the record may keep a mapping while not running
        ({"id": "pod123", "status": "RUNNING", "runtime": None}, None),
    ],
)
def test_only_a_running_pod_with_a_public_22_tcp_mapping_gives_an_address(
    pod: dict[str, Any], want: tuple[str, int] | None
) -> None:
    assert runpod_ssh35.direct_address(pod) == want


def test_the_key_comes_from_the_environment_first(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('apikey = "rpa_FROM_FILE"\napiurl = "https://api.runpod.io/graphql"\n')
    assert runpod_ssh35.api_key({"RUNPOD_API_KEY": KEY}, config) == KEY
    assert runpod_ssh35.api_key({"RUNPOD_API_KEY": " "}, config) == "rpa_FROM_FILE"
    assert runpod_ssh35.api_key({}, config) == "rpa_FROM_FILE"


@pytest.mark.parametrize("text", [None, 'apiurl = "https://api.runpod.io"\n', "apikey = \n"])
def test_no_key_anywhere_is_refused_by_name_and_shows_no_value(
    tmp_path: Path, text: str | None
) -> None:
    config = tmp_path / "config.toml"
    if text is not None:
        config.write_text(text, encoding="utf-8")
    with pytest.raises(runpod_ssh35.AddressError) as error:
        runpod_ssh35.api_key({}, config)
    assert "RUNPOD_API_KEY" in str(error.value) and "apikey" in str(error.value)


class _Reply(io.BytesIO):
    def __enter__(self) -> _Reply:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def test_the_lookup_is_one_get_of_the_v2_pod_record_with_the_key_in_the_header() -> None:
    seen: list[tuple[Any, float]] = []

    def opener(request: Any, timeout: float) -> _Reply:
        seen.append((request, timeout))
        return _Reply(json.dumps(_pod("RUNNING", SSH)).encode())

    assert runpod_ssh35.get_pod("pod123", KEY, opener=opener) == _pod("RUNNING", SSH)
    ((request, timeout),) = seen
    assert request.full_url == "https://api.runpod.io/v2/pods/pod123"
    assert request.get_method() == "GET" and request.data is None
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    assert KEY not in request.full_url and 0 < timeout <= 60


def test_the_module_reads_only() -> None:
    source = (Path(__file__).parent / "runpod_ssh35.py").read_text(encoding="utf-8")
    for word in ("method=", "/action", "/stop", "data=", "open("):
        assert word not in source, word


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.said: list[str] = []

    def now(self) -> float:
        return self.t

    def pause(self, seconds: float) -> None:
        self.t += seconds


def _wait(replies: list[Any], clock: _Clock) -> tuple[str, int]:
    calls: list[str] = []

    def get(pod_id: str, key: str) -> dict[str, Any]:
        calls.append(key)
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    try:
        return runpod_ssh35.wait_for_address(
            "pod123", KEY, get=get, now=clock.now, pause=clock.pause, say=clock.said.append
        )
    finally:
        assert set(calls) <= {KEY}


def _http(code: int) -> urllib.error.HTTPError:
    url = "https://api.runpod.io/v2/pods/pod123"
    return urllib.error.HTTPError(url, code, "x", None, None)  # type: ignore[arg-type]


def test_the_wait_reports_each_not_ready_reply_then_returns_the_address() -> None:
    clock = _Clock()
    replies = [_pod("CREATED"), _http(503), urllib.error.URLError("down"), _pod("RUNNING", SSH)]
    assert _wait(replies, clock) == (IP, PORT)
    assert clock.t == 3 * runpod_ssh35.POLL_S == 45
    assert len(clock.said) == 3 and all("not ready yet" in line for line in clock.said)
    assert "status CREATED" in clock.said[0] and "HTTP 503" in clock.said[1]
    assert not any(KEY in line for line in clock.said)


def test_no_public_address_in_15_minutes_stops_with_a_clear_message() -> None:
    clock = _Clock()
    proxy_only = _pod("RUNNING", {**SSH, "ip": None})
    with pytest.raises(runpod_ssh35.AddressError) as error:
        _wait([proxy_only], clock)
    assert clock.t == runpod_ssh35.WAIT_S == 15 * 60
    assert len(clock.said) == 15 * 60 // 15  # one report per 15 s wait
    assert "no public IP" in str(error.value) and "15 min" in str(error.value)
    assert "scp" in str(error.value) and KEY not in str(error.value)


@pytest.mark.parametrize("code", [401, 403, 404])
def test_a_refused_key_or_an_unknown_pod_stops_at_once(code: int) -> None:
    clock = _Clock()
    with pytest.raises(runpod_ssh35.AddressError) as error:
        _wait([_http(code)], clock)
    assert clock.t == 0 and f"HTTP {code}" in str(error.value)
    assert KEY not in str(error.value)
