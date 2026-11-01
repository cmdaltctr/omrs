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

from .rules import ModelKind, model_kind

Role = Literal["chat", "embeddings", "ocr"]
Mode = Literal["external", "managed"]
PortPolicy = Literal["fixed", "free"]

#: Runtime ids: a role, or ``ocr-<engine folder name>`` (design D11).
RUNTIME_ID_RE = re.compile(r"^(chat|embeddings|ocr-[A-Za-z0-9._-]+)$")

_PORT_FLAG = "--port"
_HOST_BLOCK = ("--host", "127.0.0.1")


@dataclass(frozen=True)
class DeclaredFile:
    """A model file an OCR runtime declares, with its SHA-256.

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
        id: ``chat``, ``embeddings`` or ``ocr-<engine folder>``.
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
        """The ``-np`` token, or ``0`` when the server picks its slots."""
        try:
            return int(self.argv[self.argv.index("-np") + 1])
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
        )


def _model_flag(model: str, kind: ModelKind | None) -> tuple[str, str]:
    resolved = kind if kind is not None else model_kind(model)
    if resolved is None:
        raise ValueError(f"not an allowed model: {model!r}")
    return ("-m" if resolved == "file" else "-hf"), model


def chat_spec(
    *, mode: Mode, binary: str, model: str, port: int, window: int, kind: ModelKind | None = None
) -> RuntimeSpec:
    """Return the Chat runtime: fixed port of the chat URL, ``-c`` window."""
    flag, model_value = _model_flag(model, kind)
    return RuntimeSpec(
        id="chat",
        role="chat",
        mode=mode,
        binary=binary,
        argv=(binary, flag, model_value, *_HOST_BLOCK, _PORT_FLAG, str(port), "-c", str(window)),
    )


def embeddings_spec(
    *, mode: Mode, binary: str, model: str, port: int, kind: ModelKind | None = None
) -> RuntimeSpec:
    """Return the embeddings runtime: fixed port of the embed URL, ``--embedding``."""
    flag, model_value = _model_flag(model, kind)
    return RuntimeSpec(
        id="embeddings",
        role="embeddings",
        mode=mode,
        binary=binary,
        argv=(binary, flag, model_value, *_HOST_BLOCK, _PORT_FLAG, str(port), "--embedding"),
    )


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
