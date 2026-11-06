"""``RuntimeSpec``: the identity of one managed runtime (design D1, D2).

A spec is frozen data. Two OMRS processes that build the same spec share one
server; a changed spec (another binary, model, window or fixed port) is
another version of the runtime. The JSON form travels to the test client
process, so every field is JSON-safe.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Literal

Role = Literal["router", "ocr"]
Mode = Literal["external", "managed"]
PortPolicy = Literal["fixed", "free"]

#: Runtime ids: ``router`` (change one-llamacpp-router, design D1) or
#: ``ocr-<engine folder name>`` (design D11). The ``chat``, ``embeddings`` and
#: ``decision-<name>`` ids are retired.
RUNTIME_ID_RE = re.compile(r"^(router|ocr-[A-Za-z0-9._-]+)$")

_PORT_FLAG = "--port"
_HOST_BLOCK = ("--host", "127.0.0.1")


@dataclass(frozen=True)
class DeclaredFile:
    """A model file an OCR or decision runtime declares, with its SHA-256.

    Attributes:
        flag: ``-m`` or ``--mmproj``.
        path: Absolute path of the file at build time.
        sha256: Expected SHA-256, 64 hex characters.
    """

    flag: str
    path: str
    sha256: str


@dataclass(frozen=True)
class RuntimeSpec:
    """One managed runtime as a process wants it.

    Attributes:
        id: ``router`` or ``ocr-<engine folder>``.
        role: The role the runtime serves.
        mode: ``managed`` starts or adopts a server; ``external`` only holds
            a URL.
        binary: Absolute program path (empty for external).
        argv: The complete launch list. A free-port runtime holds ``0`` after
            ``--port``; :meth:`launch_argv` substitutes the real port.
        port_policy: ``fixed`` (the port of the role URL) or ``free`` (the
            manager picks a loopback port at each start).
        url_base: Base URL in external mode, else ``""``.
        build: Required llama.cpp build of an OCR runtime, else ``None``.
        files: Declared model files with SHA-256 (OCR), else empty.
        min_build: Lowest llama.cpp build the router accepts, else ``None``.
    """

    id: str
    role: Role
    mode: Mode
    binary: str
    argv: tuple[str, ...] = ()
    port_policy: PortPolicy = "fixed"
    url_base: str = ""
    build: int | None = None
    files: tuple[DeclaredFile, ...] = field(default=())
    min_build: int | None = None

    def __post_init__(self) -> None:
        if not RUNTIME_ID_RE.fullmatch(self.id):
            raise ValueError(f"not a runtime id: {self.id!r}")
        if "--sleep-idle-seconds" in self.argv:  # llama.cpp issue #29689
            raise ValueError("the idle sleep flag is never allowed")

    # ── Derived values ──────────────────────────────────────────────────

    @property
    def port(self) -> int | None:
        """The port token of ``argv``; ``0`` while a free port is unassigned."""
        try:
            return int(self.argv[self.argv.index(_PORT_FLAG) + 1])
        except (ValueError, IndexError):
            return None

    @property
    def slots(self) -> int:
        """The ``-np`` (or ``--parallel``) token, or ``0`` when the server picks its slots."""
        flag = "-np" if "-np" in self.argv else "--parallel"
        try:
            return int(self.argv[self.argv.index(flag) + 1])
        except (ValueError, IndexError):
            return 0

    @property
    def one_slot(self) -> bool:
        """Whether requests to this runtime must serialise (design D6)."""
        return self.slots == 1

    @property
    def digest(self) -> str:
        """The stable identity of this version of the runtime.

        The port token is normalised: a fixed port is part of the identity,
        a free port is not, so a restarted OCR server keeps its digest and a
        joining process can adopt it.
        """
        normalised = list(self.argv)
        if _PORT_FLAG in normalised:
            position = normalised.index(_PORT_FLAG) + 1
            normalised[position] = str(self.port) if self.port_policy == "fixed" else "*"
        payload = json.dumps([self.binary, normalised], ensure_ascii=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    # ── Builders ────────────────────────────────────────────────────────

    def launch_argv(self, port: int) -> tuple[str, ...]:
        """Return ``argv`` with *port* in the ``--port`` slot."""
        argv = list(self.argv)
        if _PORT_FLAG not in argv:
            argv += [*_HOST_BLOCK, _PORT_FLAG, str(port)]
            return tuple(argv)
        position = argv.index(_PORT_FLAG) + 1
        argv[position] = str(port)
        return tuple(argv)

    def with_launch_port(self, port: int) -> RuntimeSpec:
        """Return the same spec with a concrete free port in ``argv``."""
        return replace(self, argv=self.launch_argv(port))

    def with_url_base(self, url_base: str) -> RuntimeSpec:
        """Return the same spec pointed at an external server."""
        return replace(self, url_base=url_base)

    # ── JSON form (the test client process protocol) ────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the spec."""
        return {
            "id": self.id,
            "role": self.role,
            "mode": self.mode,
            "binary": self.binary,
            "argv": list(self.argv),
            "port_policy": self.port_policy,
            "url_base": self.url_base,
            "build": self.build,
            "files": [{"flag": f.flag, "path": f.path, "sha256": f.sha256} for f in self.files],
            "min_build": self.min_build,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeSpec:
        """Build a spec from :meth:`to_dict` output."""
        return cls(
            id=str(data["id"]),
            role=data["role"],
            mode=data["mode"],
            binary=str(data.get("binary", "")),
            argv=tuple(data.get("argv", ())),
            port_policy=data.get("port_policy", "fixed"),
            url_base=str(data.get("url_base", "")),
            build=data.get("build"),
            files=tuple(
                DeclaredFile(flag=str(f["flag"]), path=str(f["path"]), sha256=str(f["sha256"]))
                for f in data.get("files", ())
            ),
            min_build=data.get("min_build"),
        )


def _retired(name: str) -> ValueError:
    return ValueError(f"the {name} runtime id is retired: build the router with router_spec")


def chat_spec(**_: Any) -> RuntimeSpec:
    """Refuse: the ``chat`` runtime retired (one-llamacpp-router, D1).

    The name stays so callers rewired in task 3.7 still import. Remove it then.

    Raises:
        ValueError: Always.
    """
    raise _retired("chat")


def embeddings_spec(**_: Any) -> RuntimeSpec:
    """Refuse: the ``embeddings`` runtime retired (one-llamacpp-router, D1).

    Raises:
        ValueError: Always.
    """
    raise _retired("embeddings")


def decision_spec(**_: Any) -> RuntimeSpec:
    """Refuse: the ``decision-<name>`` runtimes retired (one-llamacpp-router, D10).

    Raises:
        ValueError: Always.
    """
    raise _retired("decision")


def ocr_spec(
    *,
    engine_folder: str,
    binary: str,
    build: int,
    flags: tuple[str, ...] | list[str],
    files: tuple[DeclaredFile, ...] | list[DeclaredFile],
) -> RuntimeSpec:
    """Return an OCR runtime: free loopback port, declared build and files.

    The engine's flags and file flags come first; the host adds the host and
    port block. The port token is ``0`` until a start picks a port.
    """
    file_flags: list[str] = []
    for declared in files:
        file_flags += [declared.flag, declared.path]
    return RuntimeSpec(
        id=f"ocr-{engine_folder}",
        role="ocr",
        mode="managed",
        binary=binary,
        argv=(binary, *flags, *file_flags, *_HOST_BLOCK, _PORT_FLAG, "0"),
        port_policy="free",
        build=build,
        files=tuple(files),
    )
