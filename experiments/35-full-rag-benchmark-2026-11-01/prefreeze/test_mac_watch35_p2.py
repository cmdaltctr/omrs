"""Checks on mac_watch35.py for the P2 session: the SSH address, the stop grace, the pack.

The stubs of test_mac_watch35.py play the pod. When no --ssh-host is given, a small
driver replaces ``runpod_ssh35.get_pod`` with replies read from a JSON file, so no test
reaches RunPod or any network host. No test creates, stops or deletes a pod.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import mac_watch35
from test_mac_watch35 import HERE, POD, Session, _last

KEY = "rpa_FAKE_API_KEY_0451"
IP, PORT = "81.27.69.179", 22956
SSH = {"ip": IP, "private": 22, "public": PORT, "type": "tcp"}
DRIVER = """
import json, sys, urllib.error
sys.path.insert(0, sys.argv[1])
import runpod_ssh35
replies, keys = json.load(open(sys.argv[2])), open(sys.argv[3], "a")
def get_pod(pod_id, key):
    keys.write(f"{pod_id} {key}\\n"); keys.flush()
    reply = replies.pop(0) if len(replies) > 1 else replies[0]
    if "http" in reply:
        raise urllib.error.HTTPError("https://api.runpod.io", reply["http"], "x", None, None)
    return reply
runpod_ssh35.get_pod = get_pod
import mac_watch35
sys.exit(mac_watch35.main(sys.argv[4:]))
"""


def _pod(status: str, *ports: dict[str, object]) -> dict[str, object]:
    return {"id": POD, "status": status, "runtime": {"ports": list(ports)}}


def _run(s: Session, replies: list[dict[str, object]], *args: str, **env: str):
    driver, answers = s.tmp / "driver.py", s.tmp / "replies.json"
    driver.write_text(DRIVER, encoding="utf-8")
    answers.write_text(json.dumps(replies), encoding="utf-8")
    cmd = [sys.executable, str(driver), str(HERE), str(answers), str(s.tmp / "keys.log")]
    cmd += ["--pod-id", POD, "--commit", s.commit, "--examples", str(s.examples)]
    cmd += ["--ssh-key", str(s.key), "--repo-url", str(s.url), *args]
    return subprocess.run(
        cmd, env=s._env(**env), capture_output=True, text=True, timeout=120, cwd=s.tmp
    )


def _files_hold(root: Path, text: str) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and text.encode() in p.read_bytes()]


def test_without_ssh_host_the_watcher_waits_for_the_public_22_mapping_then_runs(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    replies = [_pod("CREATED"), _pod("RUNNING", {**SSH, "ip": None}), _pod("RUNNING", SSH)]
    result = _run(s, replies, RUNPOD_API_KEY=KEY)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    assert output.count("not ready yet") == 2
    assert f"{IP}:{PORT}" in output
    copies = s.log("scp.log")
    assert copies and all(f"-P {PORT}" in line and f"root@{IP}:" in line for line in copies)
    assert s.log("keys.log") == [f"{POD} {KEY}"] * 3
    assert KEY not in output
    assert _files_hold(s.root, KEY) == [] and _files_hold(s.pod, KEY) == []


def test_no_public_address_in_15_minutes_is_exit_13_with_nothing_copied(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = _run(s, [_pod("RUNNING", {**SSH, "ip": None})], RUNPOD_API_KEY=KEY)
    assert result.returncode == 13, result.stdout + result.stderr
    assert "no public IP" in result.stdout and KEY not in result.stdout + result.stderr
    assert not s.log("ssh.log") and not s.log("scp.log")
    assert len(s.log("keys.log")) == 15 * 60 // 15 + 1  # every 15 s, first try included
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_the_key_falls_back_to_the_runpod_config_file(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    (s.home / ".runpod").mkdir()
    (s.home / ".runpod/config.toml").write_text(f'apikey = "{KEY}"\n', encoding="utf-8")
    result = _run(s, [_pod("RUNNING", SSH)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert s.log("keys.log") == [f"{POD} {KEY}"] and KEY not in result.stdout


def test_no_key_or_half_an_address_is_refused_before_any_step(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    for args, word in (
        ([], "RUNPOD_API_KEY"),
        (["--ssh-host", "203.0.113.7"], "--ssh-port"),
        (["--ssh-port", "40022"], "--ssh-host"),
    ):
        result = _run(s, [_pod("RUNNING", SSH)], *args)
        assert result.returncode == 2, (args, result.stdout + result.stderr)
        assert "REFUSED" in result.stdout and word in result.stdout, args
        assert _last(result) == f"DELETE_POD_NOW {POD}"
    assert not s.log("keys.log") and not s.log("ssh.log") and not s.log("scp.log")


def test_the_dry_run_names_the_lookup_and_makes_no_call(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = _run(s, [_pod("RUNNING", SSH)], "--dry-run", RUNPOD_API_KEY=KEY)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"GET https://api.runpod.io/v2/pods/{POD}" in result.stdout
    assert not s.log("keys.log") and not s.log("ssh.log") and KEY not in result.stdout


def test_the_pod_waits_longer_for_pulled_than_the_watcher_may_spend_pulling() -> None:
    """A slow copy must end before the chain stops the pod (2026-11-24: 35 min at 135 KB/s)."""
    w = mac_watch35
    ssh_s, ok_s = 120, 300  # Pod.ssh and Pod.ok default timeouts
    # Notice the done line, copy the log, ask which tarball, copy it twice, write PULLED.
    pull_s = w.POLL_S + ssh_s + w.LOG_COPY_S + ssh_s + 2 * w.PULL_COPY_S + ok_s
    assert pull_s < w.STOP_GRACE_MIN * 60 <= 3 * 3600  # finite: a dead Mac costs at most 3 h
    assert w.PULL_COPY_S * 135_000 >= 300e6  # one attempt carries 300 MB at 135 KB/s


def test_the_watcher_pack_leaves_out_the_index_stores(tmp_path: Path) -> None:
    s = Session(tmp_path, ["+[00:00:01] == a: start", "dead"])
    out = s.pod / "workspace/exp35-test/out"
    for rel in ("s/stores/e4b-c1024/lancedb/t.lance/data/0.lance", "stores/e8b-c512/x.json"):
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(b"vectors")
    (out / "s/environment.json").write_text("{}\n", encoding="utf-8")
    result = s.run()
    assert result.returncode == 7, result.stdout + result.stderr
    with tarfile.open(s.folder() / "watcher-out.tgz") as tar:
        names = [m.name for m in tar.getmembers() if m.isfile()]
    assert {"out/answer-summary.json", "out/s/environment.json"} <= set(names)
    assert not [n for n in names if "/stores/" in n or "lancedb" in n]
