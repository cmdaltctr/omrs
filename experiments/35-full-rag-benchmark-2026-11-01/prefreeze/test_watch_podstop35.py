"""Checks on the pod stop that mac_watch35.py sends through the RunPod API after a clean end.

After a hash-checked final pull and a verified off-site copy, the Mac stops the pod itself:
``POST https://api.runpod.io/v2/pods/{id}/action`` with ``{"action":"stop"}``, then
``GET /v2/pods/{id}`` every 10 s for up to 3 min until the status is ``EXITED``. A failure
falls back to the old wait for the pod's own stop. No hold case (KEEP_POD) sends a stop.

The end-to-end tests run the watcher with the stubs of test_mac_watch35.py and a driver that
replaces ``urllib.request.urlopen``: the real request code runs, no network host is reached,
and the driver logs only a yes or no for the key, never its value.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest
import r2_testkit35 as r2
import runpod_ssh35
import watch_podstop35
from test_mac_watch35 import HERE, POD, REFUSED, Session, _last, _sha
from test_mac_watch35_p2 import _files_hold
from test_watch_offsite35 import _on
from test_watch_stages35 import TAG, _stage

KEY = "rpa_FAKE_STOP_KEY_7731"
URL = f"https://api.runpod.io/v2/pods/{POD}"
START = "+[00:00:01] == a: start (timeout 600s)"
FINISH = "+[00:00:02] == finish: failed stages: {}; skipped: none; resumed: none"
DRIVER = """
import json, os, sys, urllib.error, urllib.request
sys.path.insert(0, sys.argv[1])
plan, log = json.load(open(sys.argv[2])), sys.argv[3]
class Reply:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def read(self): return json.dumps(self.body).encode()
def urlopen(request, timeout=None):
    entry = {"method": request.get_method(), "url": request.full_url,
             "body": (request.data or b"").decode(),
             "bearer": request.get_header("Authorization") == "Bearer " + plan["key"],
             "pulled": os.path.exists(plan["pulled"])}
    open(log, "a").write(json.dumps(entry) + "\\n")
    if request.get_method() == "POST":
        if plan["post"] != "ok":
            raise urllib.error.HTTPError(request.full_url, plan["post"], "x", None, None)
        return Reply({})
    statuses = plan["get"]
    return Reply({"status": statuses.pop(0) if len(statuses) > 1 else statuses[0]})
urllib.request.urlopen = urlopen
import mac_watch35
sys.exit(mac_watch35.main(sys.argv[4:]))
"""


def _run(
    s: Session,
    *args: str,
    post: str | int = "ok",
    get: tuple[str, ...] = ("RUNNING", "EXITED"),
    key: str | None = KEY,
    **env: str,
) -> subprocess.CompletedProcess[str]:
    """Run the watcher with the HTTP layer replaced; the key is in the environment when given."""
    driver, plan = s.tmp / "driver.py", s.tmp / "http-plan.json"
    driver.write_text(DRIVER, encoding="utf-8")
    pulled = str(s.work / "PULLED")
    plan.write_text(
        json.dumps({"post": post, "get": list(get), "key": key or "none", "pulled": pulled}),
        encoding="utf-8",
    )
    cmd = [sys.executable, str(driver), str(HERE), str(plan), str(s.tmp / "http.log")]
    cmd += ["--pod-id", POD, "--ssh-host", "203.0.113.7", "--ssh-port", "40022"]
    cmd += ["--commit", s.commit, "--examples", str(s.examples), "--ssh-key", str(s.key)]
    cmd += ["--repo-url", str(s.url), *s.base_args, *args]
    env = {**({"RUNPOD_API_KEY": key} if key else {}), **env}
    return subprocess.run(
        cmd, env=s._env(**env), capture_output=True, text=True, timeout=120, cwd=s.tmp
    )


def _http(s: Session) -> list[dict[str, object]]:
    return [json.loads(line) for line in s.log("http.log")]


def _posts(s: Session) -> list[dict[str, object]]:
    return [x for x in _http(s) if x["method"] == "POST"]


def test_a_clean_ok_end_stops_the_pod_through_the_api_and_confirms_it(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = _run(s, get=("RUNNING", "RUNNING", "EXITED"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "end=done outputs=ok pulled-marker=written pod-stop=mac-api" in result.stdout
    assert _last(result) == f"DELETE_POD_NOW {POD}"  # stopped, not deleted: the owner deletes
    requests = _http(s)
    posts = _posts(s)
    assert len(posts) == 1 and posts[0]["url"] == f"{URL}/action"
    assert json.loads(str(posts[0]["body"])) == {"action": "stop"}
    assert [x["method"] for x in requests] == ["POST", "GET", "GET", "GET"]  # until EXITED
    assert all(x["url"] == URL for x in requests[1:])
    assert all(x["bearer"] for x in requests)  # the key goes in the Authorization header
    assert posts[0]["pulled"]  # PULLED is written first, as before
    assert (s.work / "PULLED").read_text(encoding="utf-8").strip() == "ok"
    assert _sha(s.folder() / "test-session-out.tgz") == _sha(s.work / "test-session-out.tgz")


def test_a_stop_that_is_never_confirmed_falls_back_to_the_pods_own_stop(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = _run(s, get=("RUNNING",))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pod-stop=sent" in result.stdout and "pod-stop=mac-api" not in result.stdout
    assert len(_posts(s)) == 1
    assert len(_http(s)) == 1 + 3 * 60 // 10 + 1  # one POST, then every 10 s for 3 min
    assert "not confirmed after 3 min" in result.stdout
    assert _last(result) == f"DELETE_POD_NOW {POD}"


@pytest.mark.parametrize("code", [500, 403])
def test_a_failed_post_falls_back_to_waiting_for_the_pods_own_stop(
    tmp_path: Path, code: int
) -> None:
    s = Session(tmp_path, ["done"])
    result = _run(s, post=code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "end=done outputs=ok pulled-marker=written pod-stop=sent" in result.stdout
    assert f"Mac stop failed: HTTP {code}" in result.stdout
    assert [x["method"] for x in _http(s)] == ["POST"]  # nothing to confirm after a failed POST
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_without_an_api_key_the_watcher_skips_the_mac_stop_and_waits_as_before(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    result = _run(s, key=None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pod-stop=sent" in result.stdout and "Mac stop skipped" in result.stdout
    assert not _http(s)


def test_a_failed_post_and_a_failed_self_stop_is_still_exit_3(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    (s.pod / "stop-fails").touch()
    result = _run(s, post=500)
    assert result.returncode == 3, result.stdout + result.stderr
    assert "pod-stop=FAILED" in result.stdout and "POD_STOP_FAILED" in result.stdout
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    assert len(_posts(s)) == 1


def test_keep_pod_on_fail_with_no_failed_stage_is_stopped_by_the_mac(tmp_path: Path) -> None:
    s = Session(tmp_path, [START, FINISH.format("none"), "done"])
    result = _run(s, "--keep-pod-on-fail")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pod-stop=mac-api" in result.stdout and len(_posts(s)) == 1


# Hold cases: the last line is KEEP_POD and the Mac sends no stop.
def _no_stop(s: Session, result: subprocess.CompletedProcess[str]) -> None:
    assert not _posts(s), result.stdout
    assert "pod-stop=mac-api" not in result.stdout
    assert _last(result).startswith(f"KEEP_POD {POD}") and "DELETE_POD_NOW" not in result.stdout


def test_a_detached_watcher_sends_no_stop(tmp_path: Path) -> None:
    s = Session(tmp_path, [START, "detach"])
    result = _run(s)
    assert result.returncode == 15, result.stdout + result.stderr
    _no_stop(s, result)
    assert (s.pod / "alive").exists()  # the chain runs on


def test_an_off_site_copy_that_is_not_verified_sends_no_stop(tmp_path: Path) -> None:
    s = _on(tmp_path, ["done"])
    (tmp_path / "curl.fail-match").write_text("final/", encoding="utf-8")
    result = _run(s, PATH=r2.install(tmp_path))
    assert "!!! OFFSITE_NOT_VERIFIED" in result.stdout
    _no_stop(s, result)


def test_a_final_pull_that_is_not_ok_sends_no_stop(tmp_path: Path) -> None:
    s = Session(tmp_path, ["badsha"])
    result = _run(s)
    assert result.returncode == 11, result.stdout + result.stderr
    assert "outputs=hash-mismatch" in result.stdout
    _no_stop(s, result)


def test_a_kept_pod_after_a_failed_stage_sends_no_stop(tmp_path: Path) -> None:
    s = Session(tmp_path, [START, FINISH.format("a b"), "done"])
    (s.pod / "keeps").touch()  # the chain logs POD_KEPT after PULLED
    result = _run(s, "--keep-pod-on-fail")
    assert result.returncode == 14, result.stdout + result.stderr
    assert "pod-stop=kept" in result.stdout
    _no_stop(s, result)


def test_an_abnormal_end_sends_no_stop(tmp_path: Path) -> None:
    s = Session(tmp_path, ["+[00:00:01] == setup: start"])
    result = _run(s)
    assert result.returncode == 8, result.stdout + result.stderr  # idle
    assert "pod-stop=not-expected" in result.stdout
    assert not _posts(s) and not _http(s)


def test_a_stop_line_end_is_not_a_clean_end_and_sends_no_stop(tmp_path: Path) -> None:
    s = Session(tmp_path, [REFUSED, "done"])  # the chain ends, but with a STOP: line (exit 6)
    result = _run(s)
    assert result.returncode == 6, result.stdout + result.stderr
    assert "end=stop-line outputs=ok" in result.stdout and "pod-stop=sent" in result.stdout
    assert not _posts(s) and not _http(s)


def test_a_stage_tarball_that_only_the_pod_holds_sends_no_stop(tmp_path: Path) -> None:
    s = Session(tmp_path, [START, "done"])
    _stage(s)
    (s.work / "stage-out" / f"{TAG}.tgz.sha256").write_text(f"{'0' * 64}  {TAG}.tgz\n", "utf-8")
    result = _run(s)
    assert "STAGE_NOT_PULLED" in result.stdout
    _no_stop(s, result)


@pytest.mark.parametrize("post", ["ok", 500])
def test_the_api_key_never_reaches_the_output_the_summary_or_a_file(
    tmp_path: Path, post: str | int
) -> None:
    s = Session(tmp_path, ["done"])
    result = _run(s, post=post)
    assert result.returncode == 0, result.stdout + result.stderr
    assert KEY not in result.stdout + result.stderr
    assert len(_posts(s)) == 1  # the stop was tried, so the key was in use
    assert KEY not in (s.folder() / "watch-summary.txt").read_text(encoding="utf-8")
    assert not _files_hold(s.root, KEY) and not _files_hold(s.pod, KEY)
    for name in ("ssh.log", "scp.log", "tmux.log", "http.log"):  # arguments and request log
        assert KEY not in "\n".join(s.log(name)), name
    assert all(x["bearer"] for x in _http(s))


def test_the_dry_run_names_the_stop_and_sends_nothing(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = _run(s, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"POST {URL}/action" in result.stdout and '{"action":"stop"}' in result.stdout
    assert "EXITED" in result.stdout
    assert not _http(s) and not s.log("ssh.log") and KEY not in result.stdout + result.stderr


# Unit checks: a fake clock and fake HTTP calls.
class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def pause(self, seconds: float) -> None:
        self.t += seconds


def _stop(
    monkeypatch: pytest.MonkeyPatch, post: object, get: object
) -> tuple[bool, list[str], Clock]:
    monkeypatch.setenv("RUNPOD_API_KEY", KEY)
    clock, said = Clock(), []
    ok = watch_podstop35.stop_via_api(
        POD, say=said.append, now=clock.now, pause=clock.pause, post=post, get=get
    )
    return ok, said, clock


def _get(*replies: object) -> object:
    queue = list(replies)

    def get(pod_id: str, key: str) -> object:
        assert pod_id == POD and key == KEY
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return {"status": reply}

    return get


def test_a_get_error_while_confirming_is_tolerated_until_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    down = urllib.error.HTTPError(URL, 503, "x", None, None)  # type: ignore[arg-type]
    ok, said, clock = _stop(monkeypatch, lambda *a: None, _get(down, OSError(), "EXITED"))
    assert ok and clock.t == 20  # two waits of 10 s
    assert not any(KEY in line for line in said)


def test_only_the_exited_status_confirms_the_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    ok, said, clock = _stop(monkeypatch, lambda *a: None, _get("RUNNING", "TERMINATED"))
    assert not ok and clock.t == 180 and "last status TERMINATED" in said[-1]


def test_an_error_text_that_holds_the_key_is_never_said(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(pod_id: str, key: str) -> None:
        raise urllib.error.URLError(f"cannot reach host with {key}")

    ok, said, _ = _stop(monkeypatch, post, _get("EXITED"))
    assert not ok and said and not any(KEY in line for line in said)


def test_the_post_sends_stop_and_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    class Reply:
        def __enter__(self) -> Reply:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self) -> bytes:
            return b"{}"

    def opener(request: object, timeout: float) -> Reply:
        seen.append(request)
        return Reply()

    watch_podstop35.post_stop("pod/../x", KEY, opener=opener)
    (request,) = seen
    assert request.get_method() == "POST"  # type: ignore[attr-defined]
    assert request.full_url == f"{runpod_ssh35.API}pod%2F..%2Fx/action"  # type: ignore[attr-defined]
    assert json.loads(request.data) == {"action": "stop"}  # type: ignore[attr-defined]
    assert request.get_header("Authorization") == f"Bearer {KEY}"  # type: ignore[attr-defined]
    assert KEY not in request.full_url + request.data.decode()  # type: ignore[attr-defined]


def test_finish_leaves_the_stop_to_the_pod_when_the_end_is_not_clean() -> None:
    w = SimpleNamespace(
        stop_sent=True, stop_failed=False, kept=False, alive=True, done=True, failed_stages=False
    )
    called: list[str] = []
    verdict = watch_podstop35.finish(
        POD, w, lambda *a: True, clean=False, keep=False, say=print, now=lambda: 0.0,
        pause=lambda s: None, stop=lambda *a, **k: called.append("stop") or True,
    )  # fmt: skip
    assert verdict == "sent" and not called
