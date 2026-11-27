"""Print the RunPod create request for the Experiment 35 test pod (task 9.1, gaps G10, G11).

Run it on the Mac from the experiment folder:

    uv run --no-sync python prefreeze/create_pod35.py            # print the request
    uv run --no-sync python prefreeze/create_pod35.py --check FILE  # check a saved request

The request comes from ``plan.json``: the pod image is ``pins.environment.image``
(pinned by digest), and the same value goes into ``EXP35_POD_IMAGE``. The pod is
one RTX 4090 on secure cloud, host CUDA 13.0 or newer, SSH on port 22, a 120 GB
container disk and a persistent 40 GB volume at ``/workspace``. All work runs on the
container disk, which is local on every host (the volume is network storage on some).
The chain packs each finished stage into a tarball and the Mac pulls it (G10). The
volume only keeps a spare copy of those tarballs: a stopped pod that is started again
can restore them for a resume. A pod that is deleted loses the volume with it.
The keys are RunPod secret references; RunPod fills them in at create time, so
no key value is ever in the request or the output.

The script calls no RunPod API. A dry run (the default, and the only mode) prints
the request. ``--check`` refuses a saved request that differs from it, so a
watcher kept outside the repository can be checked before it creates the pod.
Exit code 0 means the request was printed; 2 means it was refused.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PLAN = Path(__file__).resolve().parent.parent / "plan.json"
NAME = "omrs-exp35-test-session"
GPU = {"id": "NVIDIA GeForce RTX 4090", "count": 1, "minCudaVersion": "13.0"}
CLOUD = "SECURE"
#: Container disk: the work folder (inputs, passages, outputs, stage tarballs), GGUF files,
#: reference weights, venvs and caches. Lost on a stop; the Mac pulls each finished stage.
CONTAINER_DISK_GB = 120
#: Persistent volume: the optional spare copy of the stage tarballs (index stores included),
#: kept so that a resume can restore a done stage after a stop. The largest store is the
#: full FreshStack e8b-c512 index of the P2 session, so 40 GB holds it with margin.
VOLUME_GB = 40
VOLUME_PATH = "/workspace"
PORTS = ["22/tcp"]
IMAGE_VARIABLE = "EXP35_POD_IMAGE"
#: Environment variable -> RunPod secret name (account secrets, set 2026-11-10).
SECRETS = {
    "OPENROUTER_API_KEY": "openrouter",
    "OMRS_EXP35_ZAI_KEY": "z-ai-glm",
    # Off-site copy of the results in a private Cloudflare R2 bucket (offsite35.sh).
    "R2_ACCESS_KEY_ID": "r2-exp35-key-id",
    "R2_SECRET_ACCESS_KEY": "r2-exp35-secret",
    "R2_ENDPOINT": "r2-exp35-endpoint",
}
_DIGEST = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")


class CreateRefused(ValueError):
    """The request differs from the plan, or the plan pin is not an image digest."""


def secret_reference(name: str) -> str:
    """Return the RunPod reference to the account secret *name*."""
    return "{{ RUNPOD_SECRET_" + name + " }}"


def pinned_image(plan: Mapping[str, Any]) -> str:
    """Return ``pins.environment.image``; refuse a missing pin or one without a digest."""
    image = (plan.get("pins") or {}).get("environment", {}).get("image")
    if not isinstance(image, str) or not _DIGEST.match(image):
        raise CreateRefused(
            f"plan.json pins.environment.image is {image!r}, not an image pinned by "
            "@sha256: digest (task 9.1)"
        )
    return image


def build_request(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the create request: the pinned image is the pod image and ``EXP35_POD_IMAGE``."""
    image = pinned_image(plan)
    env = {variable: secret_reference(name) for variable, name in SECRETS.items()}
    env[IMAGE_VARIABLE] = image
    return {
        "name": NAME,
        "image": image,
        "cloud": CLOUD,
        "gpu": dict(GPU),
        "disk": CONTAINER_DISK_GB,
        "mounts": {"persistent": {"size": VOLUME_GB, "path": VOLUME_PATH}},
        "ports": list(PORTS),
        "startSsh": True,
        "env": env,
    }


def _first_difference(found: Any, want: Any, path: str) -> str | None:
    if isinstance(want, dict) and isinstance(found, dict):
        for key in sorted(set(want) | set(found)):
            where = f"{path}.{key}" if path else key
            if key not in found or key not in want:
                return where
            if (inner := _first_difference(found[key], want[key], where)) is not None:
                return inner
        return None
    return None if found == want else path


def check_request(request: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    """Refuse *request* unless it equals the request built from *plan*.

    Raises:
        CreateRefused: The message names the first field that differs. It never
            shows the value of a key variable.
    """
    want = build_request(plan)
    if request.get("image") != want["image"]:
        raise CreateRefused(
            f"image {request.get('image')!r} is not plan.json pins.environment.image "
            f"{want['image']!r}"
        )
    env = request.get("env") or {}
    if env.get(IMAGE_VARIABLE) != request["image"]:
        found = env.get(IMAGE_VARIABLE)
        raise CreateRefused(f"{IMAGE_VARIABLE} {found!r} is not the pod image {request['image']!r}")
    for variable, name in SECRETS.items():
        if env.get(variable) != secret_reference(name):
            raise CreateRefused(
                f"env {variable} is not the RunPod secret reference {secret_reference(name)}"
            )
    if (field := _first_difference(dict(request), want, "")) is not None:
        raise CreateRefused(f"field {field} differs from the request built from plan.json")


def main(argv: Sequence[str] | None = None) -> int:
    """Print the checked request; return 0, or 2 when it is refused."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="print the request (the default; no API call)"
    )
    parser.add_argument("--check", type=Path, help="check this saved request instead of building")
    args = parser.parse_args(argv)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    try:
        request = (
            json.loads(args.check.read_text(encoding="utf-8"))
            if args.check
            else build_request(plan)
        )
        check_request(request, plan)
    except (CreateRefused, OSError, json.JSONDecodeError) as error:
        print(f"create_pod35: REFUSED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(request, indent=2))
    print(
        f"create_pod35: dry run, no RunPod call. Image and {IMAGE_VARIABLE}: "
        f"{request['image']}. One RTX 4090, host CUDA 13.0 or newer, {CLOUD} cloud, "
        f"{CONTAINER_DISK_GB} GB container disk, {VOLUME_GB} GB volume at {VOLUME_PATH}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
