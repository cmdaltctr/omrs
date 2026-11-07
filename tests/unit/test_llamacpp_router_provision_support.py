"""Helpers for the llama.cpp provisioning tests (change one-llamacpp-router, task 6.2).

A local archive server (``http.server`` in a thread) serves small fake
``tar.gz`` archives. Their ``llama-server`` is a tiny shell script that
prints a version line and, for the CUDA flavour, a device line. The pins are
patched to the fakes, in tests only. No test here uses the network or a real
``llama-server``. This module holds no tests.
"""

from __future__ import annotations

import hashlib
import http.server
import io
import tarfile
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import pytest

from omrs.integrations.llamacpp_runtime import pins, provision

BUILD_LINE = "version: 0.7.0-dev (build {build}, commit 19ff817fb)"
TOP_FOLDER = "llama-b11941"
CUDART_FOLDER = "cudart-llama-b11941-bin-ubuntu-cuda-12.8-x64"
CUDA_DEVICE_LINE = "  CUDA0: Fake GPU (1024 MiB, 1000 MiB free)"
LOADER_MESSAGE = "llama-server: error while loading shared libraries: libgomp.so.1: cannot open"


def server_script(
    *, build: int = 11941, devices: str | None = None, loader_failure: bool = False
) -> str:
    """Return a fake ``llama-server`` that answers ``--version`` and ``--list-devices``.

    Args:
        build: The build number ``--version`` prints.
        devices: Text ``--list-devices`` prints after ``Available devices:``;
            ``None`` prints ``(none)``.
        loader_failure: When true, every call prints a loader message and exits 127.
    """
    if loader_failure:
        return f"#!/bin/sh\necho '{LOADER_MESSAGE}' >&2\nexit 127\n"
    listed = devices if devices is not None else "  (none)"
    return (
        "#!/bin/sh\n"
        'case "$1" in\n'
        f"  --version) echo '{BUILD_LINE.format(build=build)}' >&2 ;;\n"
        f"  --list-devices) echo 'Available devices:'; echo '{listed}' ;;\n"
        "esac\n"
        "exit 0\n"
    )


def make_archive(top: str, files: dict[str, str], *, link: bool = True) -> bytes:
    """Return a ``tar.gz`` whose members sit in the folder *top*.

    A file whose name is ``llama-server`` gets mode 0755. With *link*, the
    archive also holds a relative symlink inside the folder, like the release.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            info.mode = 0o755 if name == "llama-server" else 0o644
            tar.addfile(info, io.BytesIO(data))
        if link:
            symlink = tarfile.TarInfo(f"{top}/libfake.so.0")
            symlink.type = tarfile.SYMTYPE
            symlink.linkname = "libfake.so"
            tar.addfile(symlink)
    return buffer.getvalue()


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serve one folder and record the paths asked for."""

    requests: list[str]

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Record the request path instead of logging it."""
        self.requests.append(self.path)


@dataclass
class ArchiveServer:
    """A running archive server and the pins that point at it."""

    root: Path
    base_url: str
    monkeypatch: pytest.MonkeyPatch
    requests: list[str] = field(default_factory=list)

    def publish(
        self,
        flavour: str,
        *,
        build: int = 11941,
        devices: str | None = None,
        loader_failure: bool = False,
        tamper: bool = False,
        unsafe: bool = False,
        system: str = "linux",
        machine: str = "x86_64",
    ) -> pins.PinnedBuild:
        """Serve fake archives for *flavour* and pin them.

        Args:
            flavour: ``metal``, ``cpu`` or ``cuda``. ``cuda`` adds a runtime archive.
            build: The build number the fake ``llama-server`` reports.
            devices: Text the fake ``--list-devices`` prints.
            loader_failure: Make the fake ``llama-server`` fail like a missing library.
            tamper: Pin a hash that does not match the served archive.
            unsafe: Put a member that escapes the folder into the server archive.
            system: Platform the pin belongs to.
            machine: Machine the pin belongs to.
        """
        script = server_script(build=build, devices=devices, loader_failure=loader_failure)
        server = make_archive(
            TOP_FOLDER, {"llama-server": script, "libfake.so": "lib", "LICENSE": "MIT"}
        )
        if unsafe:
            server = _with_escape(server)
        served = {f"llama-b11941-{flavour}.tar.gz": server}
        if flavour == "cuda":
            cudart = make_archive(
                CUDART_FOLDER,
                {"libcudart.so.12": "cudart", "libcublas.so.12": "cublas"},
                link=False,
            )
            served[f"cudart-llama-b11941-{flavour}.tar.gz"] = cudart
        archives = []
        for name, data in served.items():
            (self.root / "rel").mkdir(exist_ok=True)
            (self.root / "rel" / name).write_bytes(data)
            digest = hashlib.sha256(b"not the archive" if tamper else data).hexdigest()
            archives.append(pins.PinnedArchive(name, digest))
        built = pins.PinnedBuild(flavour, tuple(archives))  # type: ignore[arg-type]
        self.monkeypatch.setitem(pins._BUILDS, (system, machine, flavour), built)
        return built


def _with_escape(archive: bytes) -> bytes:
    """Return *archive* plus a member named ``../escape.txt``."""
    buffer = io.BytesIO()
    with (
        tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source,
        tarfile.open(fileobj=buffer, mode="w:gz") as out,
    ):
        for member in source.getmembers():
            out.addfile(member, source.extractfile(member) if member.isfile() else None)
        data = b"escaped"
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(data)
        out.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.fixture(name="archive_server")
def _archive_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ArchiveServer]:
    """Serve fake archives, point the release URL at them and fix the host to Linux x86-64.

    The data folder is ``<tmp>/data`` (via ``XDG_DATA_HOME``). The NVIDIA driver
    marker points at a file that does not exist, so detection gives CPU until a
    test creates ``archive_server.root / "nvidia-version"``.
    """
    root = tmp_path / "served"
    root.mkdir()
    requests: list[str] = []
    handler = type("Handler", (_Handler,), {"requests": requests})
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(handler, directory=str(root))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/rel"
    monkeypatch.setattr(pins, "LLAMA_RELEASE_URL", base)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(provision, "host_platform", lambda: ("linux", "x86_64"))
    monkeypatch.setattr(provision, "NVIDIA_VERSION_FILE", root / "nvidia-version")
    try:
        yield ArchiveServer(root=root, base_url=base, monkeypatch=monkeypatch, requests=requests)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def data_folder(tmp_path: Path) -> Path:
    """Return the llama.cpp data folder the fixture's ``XDG_DATA_HOME`` gives."""
    return tmp_path / "data" / "omrs" / "llamacpp"
