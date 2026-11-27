"""Off-site copy of the Exp 35 results in a private Cloudflare R2 bucket (Mac side).

The chain (offsite35.sh) uploads each stage tarball and the final outputs. The watcher
writes ``OFFSITE_REQUIRED`` and ``R2_PREFIX`` into ``session.env``, and at the end checks
that the objects are there: for each stage tarball and the final tarball that the Mac
holds, it reads the ``.sha256`` object from the bucket (``curl --aws-sigv4``) and compares
it with the local ``.sha256`` file. The key pair comes from ``~/.config/omrs/secrets/
r2-exp35.env`` (mode 600) and goes to curl on standard input: never in an argument, a log
or the output. ``--no-offsite`` turns the copy and the check off.
"""

from __future__ import annotations

import stat
import subprocess
from collections.abc import Callable
from pathlib import Path

BUCKET = "omrs-exp35-results"  # also the default of R2_BUCKET in offsite35.sh
NAMES = ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT")
FINAL = "test-session-out.tgz.sha256"  # the final tarball's hash file, as in the bucket
GET_S = 120


def key_file() -> Path:
    """Return the path of the owner's key file."""
    return Path.home() / ".config" / "omrs" / "secrets" / "r2-exp35.env"


def read_keys(path: Path) -> dict[str, str]:
    """Return the NAME=value lines of the key file that name an R2 value."""
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, _, value = line.strip().partition("=")
        if name in NAMES and value.strip().strip("'\""):
            found[name] = value.strip().strip("'\"")
    return found


def problems(offsite: bool) -> list[str]:
    """Name each problem of the key file; never print a value."""
    path = key_file()
    if not offsite:
        return []
    if not path.is_file():
        return [f"R2 key file {path} not found (mode 600; {', '.join(NAMES)})"]
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        return [f"R2 key file {path} must be mode 600"]
    missing = [n for n in NAMES if n not in read_keys(path)]
    return [f"R2 key file {path} has no value for {', '.join(missing)}"] if missing else []


def prefix(plan: object) -> str:
    """Return ``<results folder name>/<pod id>``: the folder of this session in the bucket."""
    return f"{plan.folder.name}/{plan.pod_id}"  # type: ignore[attr-defined]


def session_values(plan: object) -> list[str]:
    """Return the session.env lines of the off-site settings."""
    if not plan.offsite:  # type: ignore[attr-defined]
        return ["OFFSITE_REQUIRED=0"]
    return ["OFFSITE_REQUIRED=1", f"R2_PREFIX={prefix(plan)}"]


def dry_lines(plan: object) -> list[str]:
    """Return the dry-run lines of the off-site check."""
    if not plan.offsite:  # type: ignore[attr-defined]
        return ["off-site: OFF (--no-offsite): no upload on the pod, no check on the Mac"]
    return [
        f"off-site: at the end, read each .sha256 object of the stage and final tarballs from "
        f"r2://{BUCKET}/<results folder>/{plan.pod_id}/ (curl --aws-sigv4, key file "  # type: ignore[attr-defined]
        f"{key_file()}, secret on standard input) and compare it with the local file"
    ]


def _get(keys: dict[str, str], key: str) -> bytes | None:
    """Read one object; ``None`` when curl fails. The key pair goes in on standard input."""
    config = f'user = "{keys["R2_ACCESS_KEY_ID"]}:{keys["R2_SECRET_ACCESS_KEY"]}"\n'
    url = f"{keys['R2_ENDPOINT']}/{BUCKET}/{key}"
    cmd = ["curl", "-fsS", "--aws-sigv4", "aws:amz:auto:s3", "-K", "-", url]
    try:
        found = subprocess.run(  # noqa: S603 - a fixed argument list
            cmd, input=config.encode("utf-8"), capture_output=True, timeout=GET_S, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return found.stdout if found.returncode == 0 else None


def report(plan: object, folder: Path, say: Callable[[str], None]) -> str:
    """Check the objects, say the result; return why the pod must stay, or ``""``."""
    if not plan.offsite:  # type: ignore[attr-defined]
        say("off-site: OFF (--no-offsite): results are on the pod disk, the spare and the Mac only")
        return ""
    where = f"r2://{BUCKET}/{prefix(plan)}"
    try:
        keys = read_keys(key_file())
    except OSError:
        keys = {}
    if any(n not in keys for n in NAMES):
        say(f"!!! OFFSITE_NOT_VERIFIED: no usable R2 key file {key_file()}")
        return "off-site copy not verified: the R2 key file cannot be read"
    stage = sorted((folder / "stage-out").glob("*.tgz.sha256"))
    final = [folder / FINAL] if (folder / FINAL).is_file() else []
    bad = []
    for record, dir_ in [*((p, "stage-out") for p in stage), *((p, "final") for p in final)]:
        remote = _get(keys, f"{prefix(plan)}/{dir_}/{record.name}")
        if remote is None or remote.decode("utf-8", "replace").split() != (
            record.read_text(encoding="utf-8").split()
        ):
            bad.append(record.name.removesuffix(".sha256"))
    if not bad:
        say(f"off-site: {len(stage)} stage, {len(final)} final verified in {where}")
        return ""
    say(f"off-site: not every object matches in {where}")
    say(f"!!! OFFSITE_NOT_VERIFIED: {', '.join(bad)}")
    return f"off-site copy not verified for {', '.join(bad)}; the pod may hold the only copy"
