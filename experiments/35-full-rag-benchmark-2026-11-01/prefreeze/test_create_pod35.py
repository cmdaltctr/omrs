"""Checks on create_pod35.py, the Mac-side RunPod create request (task 9.1, gaps G10, G11).

The script only prints the request. No test calls RunPod or any other network host.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import create_pod35
import pytest

PLAN = json.loads((Path(__file__).parent.parent / "plan.json").read_text(encoding="utf-8"))
PIN = PLAN["pins"]["environment"]["image"]
LITERAL_KEY = "sk-or-v1-LITERAL-KEY-VALUE-0451"


def _dry_run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = create_pod35.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_dry_run_prints_the_pinned_image_as_the_image_and_the_variable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = _dry_run(capsys, "--dry-run")
    request = json.loads(out)
    assert code == 0
    assert request["image"] == request["env"]["EXP35_POD_IMAGE"] == PIN
    assert out.count(PIN) == 2
    assert request["env"]["OPENROUTER_API_KEY"] == "{{ RUNPOD_SECRET_openrouter }}"
    assert request["env"]["OMRS_EXP35_ZAI_KEY"] == "{{ RUNPOD_SECRET_z-ai-glm }}"
    assert request["env"]["R2_ACCESS_KEY_ID"] == "{{ RUNPOD_SECRET_r2-exp35-key-id }}"
    secret = request["env"]["R2_SECRET_ACCESS_KEY"]
    assert secret == "{{ RUNPOD_SECRET_r2-exp35-secret }}"  # noqa: S105 - a reference, no value
    assert request["env"]["R2_ENDPOINT"] == "{{ RUNPOD_SECRET_r2-exp35-endpoint }}"
    assert set(request["env"]) == {
        "OPENROUTER_API_KEY",
        "OMRS_EXP35_ZAI_KEY",
        "EXP35_POD_IMAGE",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT",
    }


def test_the_request_asks_for_one_rtx_4090_only_on_secure_cloud_with_a_volume(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = _dry_run(capsys)
    request = json.loads(out)
    assert code == 0
    assert request["gpu"] == {"id": "NVIDIA GeForce RTX 4090", "count": 1, "minCudaVersion": "13.0"}
    assert request["cloud"] == "SECURE"
    assert request["mounts"] == {"persistent": {"size": 40, "path": "/workspace"}}
    assert request["ports"] == ["22/tcp"]


def _changed(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    request = copy.deepcopy(create_pod35.build_request(PLAN))
    node = request
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    return request


@pytest.mark.parametrize(
    ("path", "value", "named"),
    [
        (("image",), "runpod/base@sha256:" + "2" * 64, "pins.environment.image"),
        (("image",), "runpod/base:1.6.0-cuda1281-ubuntu2404", "pins.environment.image"),
        (("env", "EXP35_POD_IMAGE"), "runpod/base@sha256:" + "2" * 64, "EXP35_POD_IMAGE"),
        (("gpu", "id"), "NVIDIA RTX A6000", "gpu.id"),
        (("gpu", "count"), 2, "gpu.count"),
        (("gpu", "minCudaVersion"), "12.4", "gpu.minCudaVersion"),
        (("cloud",), "COMMUNITY", "cloud"),
        (("mounts", "persistent", "path"), "/root", "mounts.persistent.path"),
        (("mounts", "persistent", "size"), 10, "mounts.persistent.size"),
        (("disk",), 60, "disk"),
    ],
)
def test_a_saved_request_that_differs_from_the_plan_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    path: tuple[str, ...],
    value: Any,
    named: str,
) -> None:
    saved = tmp_path / "body.json"
    saved.write_text(json.dumps(_changed(path, value)), encoding="utf-8")
    code, out, err = _dry_run(capsys, "--check", str(saved))
    assert code == 2
    assert out == ""
    assert named in err


def test_a_literal_key_in_a_saved_request_is_refused_and_never_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "body.json"
    saved.write_text(json.dumps(_changed(("env", "OPENROUTER_API_KEY"), LITERAL_KEY)), "utf-8")
    code, out, err = _dry_run(capsys, "--check", str(saved))
    assert code == 2
    assert "OPENROUTER_API_KEY" in err
    assert LITERAL_KEY not in out + err


def test_a_saved_request_equal_to_the_plan_is_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = tmp_path / "body.json"
    saved.write_text(json.dumps(create_pod35.build_request(PLAN)), encoding="utf-8")
    code, out, _ = _dry_run(capsys, "--check", str(saved))
    assert code == 0
    assert json.loads(out)["image"] == PIN


def test_a_plan_pin_without_a_digest_is_refused() -> None:
    plan = copy.deepcopy(PLAN)
    plan["pins"]["environment"]["image"] = "runpod/base:1.6.0-cuda1281-ubuntu2404"
    with pytest.raises(create_pod35.CreateRefused, match="digest"):
        create_pod35.build_request(plan)


def test_the_container_disk_holds_the_work_and_the_volume_is_the_spare_copy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """All work runs on the 120 GB container disk. The 40 GB volume only keeps spare tarballs."""
    request = json.loads(_dry_run(capsys)[1])
    assert request["disk"] == create_pod35.CONTAINER_DISK_GB == 120
    assert request["mounts"]["persistent"] == {"size": create_pod35.VOLUME_GB, "path": "/workspace"}
    assert create_pod35.VOLUME_GB == 40
    assert request["mounts"]["persistent"]["size"] < request["disk"]


@pytest.mark.parametrize("name", ["R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT"])
def test_a_literal_r2_value_in_a_saved_request_is_refused_without_showing_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    saved = tmp_path / "request.json"
    saved.write_text(json.dumps(_changed(("env", name), LITERAL_KEY)), "utf-8")
    code, _, err = _dry_run(capsys, "--check", str(saved))
    assert code == 2 and name in err and LITERAL_KEY not in err
