"""Per-stage pull and resume helpers for mac_watch35.py (Exp 35 pod disk layout).

The chain (pod_test_session.sh) packs each finished stage into
``$WORK/stage-out/<tag>.tgz`` and writes ``<tag>.tgz.sha256`` last, so that file is the
"ready" signal. :class:`StagePull` lists those files once per poll, copies each new
tarball to ``<results folder>/stage-out/`` and checks its SHA-256. A stage tarball that
the Mac holds survives a lost pod, so a failed stage is re-run from the next stage
(``--resume``). The watcher never unpacks them: the final tarball holds the same files.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from watch_inputs35 import sha256

SPARE_DIR = "/workspace/exp35-stage-out"  # the chain's optional spare copy (launch35.sh)
KEPT = "POD_KEPT:"  # the chain's line when it leaves the pod running (KEEP_POD_ON_FAIL=1)
LIST_S, COPY_S = 120, 45 * 60  # one listing; one stage copy (the build stage holds the stores)
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.tgz")  # also what the shell and scp accept
_ASIDE = ("test-session.log", "test-session-out.tgz", "test-session-out.tgz.sha256",
          "watcher-out.tgz", "watcher-out.tgz.sha256", "watch-summary.txt")  # fmt: skip


def list_cmd(stage_dir: str) -> str:
    """Return the one ssh command that lists each ready stage.

    A line is ``<name>.tgz.sha256 <hash> [commit]``: the last word is there when the stage
    also has a ``<name>.tgz.commit`` file (the commit the chain ran from).
    """
    return (
        f"cd {shlex.quote(stage_dir)} 2>/dev/null && for f in *.tgz.sha256; do "
        f'[ -f "$f" ] && printf \'%s %s %s\\n\' "$f" "$(cut -d\' \' -f1 "$f")" '
        f'"$([ -f "${{f%.sha256}}.commit" ] && echo commit)"; done; true'
    )


def flag_values(plan: Any) -> list[str]:
    """Return the session.env lines of the keep, resume (or seed) and resume-from-commit flags."""
    values = ["KEEP_POD_ON_FAIL=1"] * plan.keep + ["RESUME=1"] * (
        plan.resume or bool(plan.seed_from)
    )
    return values + [f"RESUME_FROM_COMMIT={plan.resume_from}"] * bool(plan.resume_from)


def dry_lines(work: str, stage_dir: str) -> list[str]:
    """Return the dry-run lines for the work folder, the spare copy and the per-stage pull."""
    return [
        f"work folder {work} (the pod's own disk; inputs, repository and outputs live there)",
        f"spare copy {SPARE_DIR} (optional: the chain writes it only when /workspace is a mount)",
        f"6b per-stage pull: every poll, ssh {shlex.quote(list_cmd(stage_dir))}; "
        f"list {stage_dir}/*.tgz.sha256, scp each new tarball into <results>/stage-out/, "
        "check its SHA-256 (one more copy on a mismatch, then STAGE_HASH_MISMATCH)",
    ]


def aside(folder: Path) -> list[str]:
    """Move the files of an earlier try to ``<name>.attempt<k>``; never overwrite one."""
    moved = []
    for name in _ASIDE:
        path = folder / name
        if path.exists():
            k = next(n for n in range(1, 1000) if not (folder / f"{name}.attempt{n}").exists())
            path.rename(folder / f"{name}.attempt{k}")
            moved.append(f"{name}.attempt{k}")
    return moved


def inputs_match_cmd(inputs: str, shas: Mapping[str, str]) -> str:
    """Return the pod command that is true when the inputs folder holds these exact files."""
    pairs = " ".join(f"{sha} {shlex.quote(name)}" for name, sha in shas.items())
    return (
        f"cd {shlex.quote(inputs)} && printf '%s  %s\\n' {pairs} | sha256sum -c - >/dev/null 2>&1"
    )


def stale_cmd(paths: Sequence[str]) -> str:
    """Return the pod command that clears the files of the earlier try (a resume launch)."""
    return "rm -f " + " ".join(shlex.quote(p) for p in paths)


class StagePull:
    """Copy each new stage tarball from the pod and check it; never raise, never end the watch."""

    def __init__(
        self, pod: Any, work: str, folder: Path, say: Callable[[str], None], copy_s: float = COPY_S
    ) -> None:
        self.pod, self.say, self.copy_s = pod, say, copy_s
        self.remote_dir, self.folder = f"{work}/stage-out", folder
        self.done: dict[str, str] = {}  # tarball name -> hash the Mac holds
        self.bad: dict[str, str] = {}  # tarball name -> hash that failed twice
        self.listed: set[str] = set()  # the ready tarballs of the last good listing
        self.with_commit: set[str] = set()  # the ready tarballs that have a .commit file
        for record in sorted(folder.glob("*.tgz.sha256")):  # an earlier try of this session
            tgz = folder / record.name.removesuffix(".sha256")
            want = record.read_text(encoding="utf-8").split()[:1]
            if tgz.is_file() and want == [sha256(tgz)]:
                self.done[tgz.name] = want[0]

    def _listing(self) -> dict[str, str]:
        found = self.pod.ssh(list_cmd(self.remote_dir), LIST_S)
        if found is None or found.returncode != 0:
            return {}
        ready = {}
        for line in found.stdout.decode("utf-8", "replace").splitlines():
            name, _, rest = line.partition(" ")
            if name.endswith(".sha256") and _NAME.fullmatch(name.removesuffix(".sha256")):
                tgz, words = name.removesuffix(".sha256"), rest.split()
                ready[tgz] = words[0] if words else ""
                (self.with_commit.add if words[1:] == ["commit"] else self.with_commit.discard)(tgz)
        return ready

    def _fetch(self, name: str) -> str | None:
        """Copy and check one tarball once: its hash when it matches, else ``""`` or ``None``."""
        staging = self.folder / ".incoming"
        staging.mkdir(parents=True, exist_ok=True)
        names = [name, *([f"{name}.commit"] if name in self.with_commit else []), f"{name}.sha256"]
        files = [self.pod.remote(f"{self.remote_dir}/{n}") for n in names]
        if not self.pod.copy(files, str(staging), self.copy_s):
            return None  # a failed copy: try again on the next poll
        want = (staging / f"{name}.sha256").read_text(encoding="utf-8").split()[:1]
        found = sha256(staging / name)
        if want != [found]:
            return ""
        for n in names:  # the .sha256 file last: it is the ready signal
            (staging / n).replace(self.folder / n)
        return found

    def pull_new(self) -> None:
        """List the ready stage tarballs once; copy each one the Mac does not hold yet."""
        ready = self._listing()
        self.listed |= set(ready)
        for name, digest in sorted(ready.items()):
            if self.done.get(name) == digest or self.bad.get(name) == digest:
                continue
            found = self._fetch(name)
            if found == "":  # wrong hash: one more copy (ssh checks bytes, so this is rare)
                found = self._fetch(name)
            if found:
                self.done[name] = found
                self.say(f"  stage tarball {name} pulled, SHA-256 {found}")
            elif found == "":
                self.bad[name] = digest
                self.say(
                    f"!!! STAGE_HASH_MISMATCH: {name} differs from the pod's .sha256 after two"
                    " copies; the final tarball still holds its files. Report it."
                )

    def unresolved(self) -> list[str]:
        """Name the ready stage tarballs the Mac does not hold (a bad hash or a failed copy)."""
        return sorted(self.listed - set(self.done) | set(self.bad))

    def summary(self) -> str:
        """Return the count and the names of the stage tarballs the Mac holds."""
        names, lost = sorted(self.done), self.unresolved()
        text = f"stage tarballs pulled: {len(names)} ({', '.join(names) if names else 'none'})"
        return text + (f"; not pulled: {', '.join(lost)}" if lost else "")
