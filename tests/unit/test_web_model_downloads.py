"""Model search and download routes (tasks 6.2 to 6.4).

The Hugging Face and Ollama adapters are faked at their modules, and a
sentinel on the real httpx transport records any outside request. No test
reaches the network, a real cache or a real Ollama. The download fake holds
on a gate so a test can read the running state, then lets it finish.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_connection_summary import make_settings  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrs import compose  # noqa: E402
from omrs.integrations import huggingface_models as hf  # noqa: E402
from omrs.integrations import ollama_pull  # noqa: E402
from omrs.transports.api import security  # noqa: E402
from omrs.transports.api.routes import model_downloads as routes  # noqa: E402

REV = "a" * 40
HF_VALUE = "hf_test_secret"  # gitleaks:allow
GB = 1000**3
FILES = (
    ("Qwen3-4B-Q4_K_M.gguf", 2_497_280_000),
    ("Qwen3-4B-Q8_0.gguf", 4_280_000_000),
    ("mmproj-F16.gguf", 600_000),
)
SEARCH = "/v1/model-downloads/search"
LISTING = "/v1/model-downloads/files"
START = "/v1/model-downloads"
CURRENT = "/v1/model-downloads/current"


class Net:
    """The faked adapter surface and the record of what the routes called."""

    def __init__(self, cache: str) -> None:
        self.cache = cache
        self.searches: list[str] = []
        self.listings: list[str] = []
        self.listed_revisions: list[str | None] = []
        self.sizes: list[dict[str, Any]] = []
        self.downloads: list[dict[str, Any]] = []
        self.pulls: list[tuple[str, str]] = []
        self.gate = threading.Event()
        self.started = threading.Event()
        self.hits = [
            hf.RepoSummary("Qwen/Qwen3-4B-GGUF", 900, 12, False, "2026-10-01T00:00:00.000Z"),
            hf.RepoSummary("meta/gated-GGUF", 5, 1, True, None),
        ]
        self.repo_files = hf.RepoFiles("unsloth/Qwen3-4B-GGUF", REV, False, FILES)
        self.search_error: hf.ModelHostError | None = None
        self.list_error: hf.ModelHostError | None = None
        self.size_error: hf.ModelHostError | None = None
        self.needed = 2_497_280_000
        self.free = 100 * GB
        self.pull_error: Exception | None = None
        self.download_error: Exception | None = None

    def calls(self) -> int:
        return len(self.searches) + len(self.listings) + len(self.sizes) + len(self.downloads)

    # fakes ---------------------------------------------------------------

    def search_models(self, query: str, **_: Any) -> list[hf.RepoSummary]:
        self.searches.append(query)
        if self.search_error:
            raise self.search_error
        return self.hits

    def list_repo_files(self, repo: str, *, revision: str | None = None, **_: Any) -> hf.RepoFiles:
        self.listings.append(repo)
        self.listed_revisions.append(revision)
        if self.list_error:
            raise self.list_error
        return self.repo_files

    def bytes_to_download(self, repo: str, revision: str, filenames: Any, *, token: Any) -> int:
        self.sizes.append(
            {"repo": repo, "revision": revision, "files": tuple(filenames), "token": token}
        )
        if self.size_error:
            raise self.size_error
        return self.needed

    def download_files(
        self, repo: str, revision: str, filenames: Any, *, on_bytes: Any, cancel: Any, token: Any
    ) -> str:
        self.downloads.append(
            {"repo": repo, "revision": revision, "files": tuple(filenames), "token": token}
        )
        on_bytes(1000)
        self.started.set()
        while not self.gate.is_set():
            if cancel.is_set():
                raise hf.DownloadCancelled
            time.sleep(0.005)
        if self.download_error:
            raise self.download_error
        return "/cache/model.gguf"

    def pull_model(self, base_url: str, name: str, *, on_progress: Any, cancel: Any) -> None:
        self.pulls.append((base_url, name))
        on_progress(10, 100)
        self.started.set()
        while not self.gate.is_set():
            if cancel.is_set():
                raise ollama_pull.PullCancelled
            time.sleep(0.005)
        if self.pull_error:
            raise self.pull_error


class Harness:
    def __init__(self, client: TestClient, policy: Any, net: Net, sent: list[str], cfg: Path):
        self.client, self.policy, self.net, self.sent, self.cfg = client, policy, net, sent, cfg
        self.job = client.app.state.runtime.model_downloads  # type: ignore[attr-defined]

    def settle(self) -> dict[str, Any]:
        deadline = time.monotonic() + 10
        while True:
            body = self.client.get(CURRENT).json()
            if body["state"] != "running":
                return body
            assert time.monotonic() < deadline, body
            time.sleep(0.01)

    def start(self, **body: Any) -> Any:
        return self.client.post(START, json=body, headers=ORIGIN)

    def llama(self, **overrides: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "provider": "llamacpp",
            "repo": "unsloth/Qwen3-4B-GGUF",
            "revision": REV,
            "label": "Q4_K_M",
        }
        return {**body, **overrides}


@pytest.fixture
def harness(
    tmp_path: Path,
    effective_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Harness]:
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    settings = make_settings()
    monkeypatch.setattr(compose, "get_settings", lambda: settings)
    net = Net(str(Path.home() / ".cache" / "huggingface" / "hub"))
    monkeypatch.setattr(hf, "search_models", net.search_models)
    monkeypatch.setattr(hf, "list_repo_files", net.list_repo_files)
    monkeypatch.setattr(hf, "bytes_to_download", net.bytes_to_download)
    monkeypatch.setattr(hf, "download_files", net.download_files)
    monkeypatch.setattr(hf, "hub_cache_folder", lambda: net.cache)
    monkeypatch.setattr(ollama_pull, "pull_model", net.pull_model)
    monkeypatch.setattr(routes, "_free_bytes", lambda _path: net.free)
    sent: list[str] = []

    def refuse(self: Any, request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        raise AssertionError(f"outside request: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield Harness(client, policy, net, sent, cfg)
        net.gate.set()
    assert sent == [], "a route sent an outside request"


# ── Access (spec "Scopes for search and download") ───────────────────────

ALL_FIVE = [
    ("GET", f"{SEARCH}?provider=llamacpp&q=qwen3", None),
    ("GET", f"{LISTING}?provider=llamacpp&repo=unsloth/Qwen3-4B-GGUF", None),
    ("POST", START, {"provider": "llamacpp", "repo": "a/b", "revision": REV, "label": "Q4_K_M"}),
    ("GET", CURRENT, None),
    ("DELETE", CURRENT, None),
]


def send(h: Harness, method: str, path: str, body: Any, headers: dict[str, str]) -> Any:
    return h.client.request(method, path, json=body, headers={**ORIGIN, **headers})


def test_a_bearer_credential_is_refused_on_all_five_routes(harness: Harness) -> None:
    harness.client.cookies.clear()
    header = bearer(harness.policy, "read", "graph", "run")
    for method, path, body in ALL_FIVE:
        assert send(harness, method, path, body, header).status_code == 403, path
        assert send(harness, method, path, body, {}).status_code == 401, path
    assert harness.net.calls() == 0 and harness.net.pulls == []
    assert harness.job.snapshot()["state"] == "idle"


def test_a_session_without_manage_is_refused_on_all_five_routes(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(security, "SESSION_SCOPES", security.SESSION_SCOPES - {"manage"})
    for method, path, body in ALL_FIVE:
        assert send(harness, method, path, body, {}).status_code == 403, path
    assert harness.net.calls() == 0
    assert harness.job.snapshot()["state"] == "idle"


# ── Search ───────────────────────────────────────────────────────────────


def test_llamacpp_search_returns_the_hugging_face_hits_with_all_keys(harness: Harness) -> None:
    response = harness.client.get(SEARCH, params={"provider": "llamacpp", "q": "qwen3"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert harness.net.searches == ["qwen3"]
    assert (body["status"], body["provider"], body["reason"]) == ("ok", "llamacpp", None)
    assert body["results"][0] == {
        "id": "Qwen/Qwen3-4B-GGUF",
        "source": "huggingface",
        "downloads": 900,
        "likes": 12,
        "gated": False,
        "last_modified": "2026-10-01T00:00:00.000Z",
    }
    assert [r["gated"] for r in body["results"]] == [False, True]
    assert body["results"][1]["last_modified"] is None


def test_ollama_search_puts_the_built_in_names_first_then_hf_ids(harness: Harness) -> None:
    body = harness.client.get(SEARCH, params={"provider": "ollama", "q": "qwen3"}).json()
    ids = [r["id"] for r in body["results"]]
    sources = [r["source"] for r in body["results"]]
    built_in = [i for i, s in zip(ids, sources, strict=True) if s == "ollama-library"]
    assert built_in and all("qwen3" in i for i in built_in)
    assert sources == ["ollama-library"] * len(built_in) + ["huggingface"] * 2
    assert ids[len(built_in) :] == ["hf.co/Qwen/Qwen3-4B-GGUF", "hf.co/meta/gated-GGUF"]
    first = body["results"][0]
    assert (first["downloads"], first["likes"], first["gated"], first["last_modified"]) == (
        None,
        None,
        False,
        None,
    )


def test_a_host_that_does_not_answer_gives_reason_network_and_no_hf_results(
    harness: Harness,
) -> None:
    harness.net.search_error = hf.ModelHostError("network")
    llama = harness.client.get(SEARCH, params={"provider": "llamacpp", "q": "qwen3"}).json()
    assert llama["results"] == [] and llama["reason"] == "network"
    ollama = harness.client.get(SEARCH, params={"provider": "ollama", "q": "qwen3"}).json()
    assert ollama["reason"] == "network"
    assert ollama["results"] and all(r["source"] == "ollama-library" for r in ollama["results"])


@pytest.mark.parametrize(
    "query",
    ["", "x" * 101, "a\x07b", "a\x00b", "a\x7fb"],
    ids=["empty", "too-long", "bell", "nul", "del"],
)
def test_a_bad_query_gives_400_and_sends_no_outside_request(harness: Harness, query: str) -> None:
    response = harness.client.get(SEARCH, params={"provider": "llamacpp", "q": query})
    assert response.status_code == 400, response.text
    assert response.json()["status"] == "error"
    assert harness.net.calls() == 0


@pytest.mark.parametrize("provider", ["openrouter", "anthropic", "nosuch", "Bad Name", "../x"])
def test_a_provider_with_no_model_source_gives_400_on_every_route(
    harness: Harness, provider: str
) -> None:
    assert (
        harness.client.get(SEARCH, params={"provider": provider, "q": "qwen3"}).status_code == 400
    )
    assert (
        harness.client.get(LISTING, params={"provider": provider, "repo": "a/b"}).status_code == 400
    )
    body = harness.llama(provider=provider)
    assert harness.start(**body).status_code == 400
    assert harness.start(provider=provider, name="qwen3").status_code == 400
    assert harness.net.calls() == 0 and harness.net.pulls == []
    assert harness.job.snapshot()["state"] == "idle"


# ── File list ────────────────────────────────────────────────────────────


def test_the_file_list_groups_by_label_and_marks_the_choices(harness: Harness) -> None:
    response = harness.client.get(
        LISTING, params={"provider": "llamacpp", "repo": "unsloth/Qwen3-4B-GGUF"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["repo"], body["revision"], body["gated"], body["reason"]) == (
        "unsloth/Qwen3-4B-GGUF",
        REV,
        False,
        None,
    )
    entries = {e["label"]: e for e in body["entries"]}
    assert set(entries) == {"Q4_K_M", "Q8_0"}
    assert entries["Q4_K_M"] == {
        "label": "Q4_K_M",
        "files": ["Qwen3-4B-Q4_K_M.gguf"],
        "size_bytes": 2_497_280_000,
        "recommended": True,
        "closest_to_full": False,
    }
    assert entries["Q8_0"]["closest_to_full"] is True and entries["Q8_0"]["recommended"] is False
    assert "mmproj" not in response.text


def test_the_file_list_works_for_ollama_with_a_hugging_face_repo(harness: Harness) -> None:
    response = harness.client.get(LISTING, params={"provider": "ollama", "repo": "a/b"})
    assert response.status_code == 200 and harness.net.listings == ["a/b"]


def test_a_repo_with_no_gguf_or_no_known_label_gives_404_not_found(harness: Harness) -> None:
    harness.net.list_error = hf.ModelHostError("not-found")
    response = harness.client.get(LISTING, params={"provider": "llamacpp", "repo": "a/b"})
    assert response.status_code == 404
    assert response.json()["reason"] == "not-found"
    harness.net.list_error = None
    harness.net.repo_files = hf.RepoFiles("a/b", REV, False, (("mmproj-F16.gguf", 5),))
    again = harness.client.get(LISTING, params={"provider": "llamacpp", "repo": "a/b"})
    assert again.status_code == 404 and again.json()["reason"] == "not-found"


def test_an_unreachable_host_gives_200_with_reason_network(harness: Harness) -> None:
    harness.net.list_error = hf.ModelHostError("network")
    body = harness.client.get(LISTING, params={"provider": "llamacpp", "repo": "a/b"}).json()
    assert (body["revision"], body["gated"], body["entries"], body["reason"]) == (
        None,
        False,
        [],
        "network",
    )


@pytest.mark.parametrize("repo", ["../x", "org/", "a b", "--help", "-a/b", "a/../b", "a/b/c", "a"])
def test_a_bad_repo_id_gives_400_and_sends_no_outside_request(harness: Harness, repo: str) -> None:
    response = harness.client.get(LISTING, params={"provider": "llamacpp", "repo": repo})
    assert response.status_code == 400, response.text
    assert harness.net.calls() == 0


# ── Start: llama.cpp ─────────────────────────────────────────────────────


def test_a_good_start_gives_202_and_downloads_the_files_of_the_label(harness: Harness) -> None:
    response = harness.start(**harness.llama())
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["state"] == "running" and body["provider"] == "llamacpp"
    assert body["model"] == "unsloth/Qwen3-4B-GGUF:Q4_K_M"
    assert body["model_value"] is None and body["reason"] is None
    assert body["cache_folder"] == "~/.cache/huggingface/hub"
    assert body["bytes_total"] == harness.net.needed
    assert harness.net.started.wait(5)
    running = harness.client.get(CURRENT).json()
    assert running["state"] == "running" and running["bytes_done"] == 1000
    harness.net.gate.set()
    done = harness.settle()
    assert done["state"] == "succeeded"
    assert done["model_value"] == "unsloth/Qwen3-4B-GGUF:Q4_K_M"
    call = harness.net.downloads[0]
    assert call == {
        "repo": "unsloth/Qwen3-4B-GGUF",
        "revision": REV,
        "files": ("Qwen3-4B-Q4_K_M.gguf",),
        "token": None,
    }
    assert harness.net.sizes[0]["files"] == ("Qwen3-4B-Q4_K_M.gguf",)
    assert not (harness.cfg / "omrs.jsonc").exists(), "a download changed a setting"


def test_a_second_start_gives_409_busy_and_the_first_keeps_running(harness: Harness) -> None:
    assert harness.start(**harness.llama()).status_code == 202
    assert harness.net.started.wait(5)
    second = harness.start(**harness.llama(label="Q8_0"))
    assert second.status_code == 409
    assert set(second.json()) == {"status", "message", "reason"}
    assert second.json()["reason"] == "busy" and second.json()["status"] == "error"
    assert len(harness.net.downloads) == 1
    assert harness.client.get(CURRENT).json()["state"] == "running"
    harness.net.gate.set()
    assert harness.settle()["state"] == "succeeded"


def test_too_little_free_space_gives_409_no_space_naming_both_sizes(harness: Harness) -> None:
    harness.net.needed = 9_700_000_000
    harness.net.free = 5 * GB
    response = harness.start(**harness.llama())
    assert response.status_code == 409
    body = response.json()
    assert set(body) == {"status", "message", "reason"} and body["reason"] == "no-space"
    assert "9.7 GB" in body["message"] and "5.0 GB" in body["message"]
    assert harness.net.downloads == [] and harness.job.snapshot()["state"] == "idle"


def test_the_space_check_keeps_one_gibibyte_spare(harness: Harness) -> None:
    margin = 1024**3
    harness.net.needed = 2 * GB
    harness.net.free = harness.net.needed + margin - 1
    assert harness.start(**harness.llama()).status_code == 409
    harness.net.free = harness.net.needed + margin
    assert harness.start(**harness.llama()).status_code == 202
    harness.net.gate.set()
    harness.settle()


def test_a_fully_cached_set_needs_no_space(harness: Harness) -> None:
    harness.net.needed = 0
    harness.net.free = 0
    harness.net.gate.set()
    assert harness.start(**harness.llama()).status_code == 202
    assert harness.settle()["state"] == "succeeded"


def test_a_gated_repo_without_hf_token_gives_409_gated_before_any_size_request(
    harness: Harness,
) -> None:
    harness.net.repo_files = hf.RepoFiles("meta/x", REV, True, FILES)
    response = harness.start(**harness.llama())
    assert response.status_code == 409
    assert set(response.json()) == {"status", "message", "reason"}
    assert response.json()["reason"] == "gated"
    assert harness.net.sizes == [] and harness.net.downloads == []


def test_a_gated_repo_with_hf_token_starts_and_the_token_stays_out_of_every_body(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("HF_TOKEN", HF_VALUE)
    caplog.set_level(logging.DEBUG)
    harness.net.repo_files = hf.RepoFiles("meta/x", REV, True, FILES)
    started = harness.start(**harness.llama())
    assert started.status_code == 202, started.text
    assert harness.net.started.wait(5)
    texts = [started.text, harness.client.get(CURRENT).text]
    harness.net.gate.set()
    texts.append(str(harness.settle()))
    assert harness.net.downloads[0]["token"] == HF_VALUE
    assert harness.net.sizes[0]["token"] == HF_VALUE
    for text in [*texts, caplog.text]:
        assert HF_VALUE not in text


def test_a_token_that_the_host_refuses_gives_409_gated_without_the_token(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", HF_VALUE)
    harness.net.size_error = hf.ModelHostError("gated")
    response = harness.start(**harness.llama())
    assert response.status_code == 409 and response.json()["reason"] == "gated"
    assert HF_VALUE not in response.text and harness.net.downloads == []


def test_an_unreachable_host_during_the_checks_gives_202_with_a_failed_job(
    harness: Harness,
) -> None:
    harness.net.list_error = hf.ModelHostError("network")
    response = harness.start(**harness.llama())
    assert response.status_code == 202
    body = response.json()
    assert (body["state"], body["reason"]) == ("failed", "network")
    assert harness.client.get(CURRENT).json()["reason"] == "network"
    harness.net.list_error = None
    harness.net.size_error = hf.ModelHostError("network")
    assert harness.start(**harness.llama()).json()["reason"] == "network"
    assert harness.net.downloads == []


def test_the_start_lists_the_files_at_the_revision_the_user_saw(harness: Harness) -> None:
    # The repo may have a newer commit by now; the start still uses the listed revision.
    older = "b" * 40
    harness.net.repo_files = hf.RepoFiles("unsloth/Qwen3-4B-GGUF", older, False, FILES)
    response = harness.start(**harness.llama(revision=older))
    assert response.status_code == 202
    assert harness.net.listed_revisions == [older]
    assert harness.net.sizes[0]["revision"] == older


def test_an_unknown_label_or_a_missing_repo_gives_404(harness: Harness) -> None:
    unknown = harness.start(**harness.llama(label="Q2_K"))
    assert unknown.status_code == 404 and unknown.json()["reason"] == "not-found"
    harness.net.list_error = hf.ModelHostError("not-found")
    missing = harness.start(**harness.llama())
    assert missing.status_code == 404 and missing.json()["reason"] == "not-found"
    harness.net.list_error = None
    harness.net.size_error = hf.ModelHostError("not-found")
    assert harness.start(**harness.llama()).status_code == 404
    assert harness.net.downloads == []


BAD_LLAMA = [
    {"repo": "../x"},
    {"repo": "org/"},
    {"repo": "a b"},
    {"repo": "--help"},
    {"repo": "-a/b"},
    {"label": "-x"},
    {"label": "a b"},
    {"label": "Q4;K"},
    {"label": "../Q4"},
    {"revision": "main"},
    {"revision": "A" * 40},
    {"revision": "a" * 39},
    {"revision": "g" * 40},
    {"repo": None},
    {"revision": None},
    {"label": None},
    {"name": "qwen3"},
    {"unknown_field": 1},
    {"label": "x" * 65},
    {"repo": "a/" + "b" * 200},
]


@pytest.mark.parametrize("change", BAD_LLAMA, ids=[str(c)[:40] for c in BAD_LLAMA])
def test_a_bad_llamacpp_start_gives_400_and_sends_no_outside_request(
    harness: Harness, change: dict[str, Any]
) -> None:
    response = harness.start(**harness.llama(**change))
    assert response.status_code == 400, response.text
    assert response.json()["status"] == "error"
    assert harness.net.calls() == 0 and harness.job.snapshot()["state"] == "idle"


def test_the_body_must_be_json_with_a_provider(harness: Harness) -> None:
    assert harness.start(repo="a/b").status_code == 400
    assert harness.client.post(START, headers=ORIGIN).status_code == 400
    assert harness.net.calls() == 0


# ── Start: Ollama ────────────────────────────────────────────────────────


def test_an_ollama_library_name_pulls_through_the_address_in_use(harness: Harness) -> None:
    response = harness.start(provider="ollama", name="qwen3:4b")
    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["provider"], body["model"], body["cache_folder"]) == ("ollama", "qwen3:4b", None)
    assert harness.net.started.wait(5)
    running = harness.client.get(CURRENT).json()
    assert (running["bytes_done"], running["bytes_total"]) == (10, 100)
    harness.net.gate.set()
    done = harness.settle()
    assert (done["state"], done["model_value"]) == ("succeeded", "qwen3:4b")
    assert harness.net.pulls == [("http://ollama.test:11434", "qwen3:4b")]
    assert harness.net.calls() == 0, "an Ollama pull must not contact Hugging Face"


def test_an_ollama_hugging_face_file_pulls_the_hf_co_name_and_ignores_the_revision(
    harness: Harness,
) -> None:
    harness.net.gate.set()
    response = harness.start(provider="ollama", repo="Qwen/Qwen3-4B-GGUF", label="Q4_K_M")
    assert response.status_code == 202, response.text
    assert harness.settle()["model_value"] == "hf.co/Qwen/Qwen3-4B-GGUF:Q4_K_M"
    again = harness.start(provider="ollama", repo="a/b", label="Q8_0", revision=REV)
    assert again.status_code == 202
    harness.settle()
    assert [name for _, name in harness.net.pulls] == [
        "hf.co/Qwen/Qwen3-4B-GGUF:Q4_K_M",
        "hf.co/a/b:Q8_0",
    ]


def test_an_ollama_pull_failure_maps_to_a_fixed_reason(harness: Harness) -> None:
    harness.net.gate.set()
    harness.net.pull_error = ollama_pull.OllamaPullError("ollama-unreachable")
    assert harness.start(provider="ollama", name="qwen3").status_code == 202
    done = harness.settle()
    assert (done["state"], done["reason"]) == ("failed", "ollama-unreachable")


BAD_OLLAMA = [
    {"name": "bad name"},
    {"name": "a;b"},
    {"name": "-x"},
    {"name": "../x"},
    {"name": "qwen3", "repo": "a/b"},
    {"name": "qwen3", "label": "Q4_K_M"},
    {"name": "qwen3", "revision": REV},
    {"repo": "a/b"},
    {"label": "Q4_K_M"},
    {"repo": "a/b", "label": "Q4_K_M", "name": "x"},
    {"repo": "../x", "label": "Q4_K_M"},
    {"repo": "a/b", "label": "-x"},
    {"repo": "a/b", "label": "Q4_K_M", "revision": "main"},
    {},
    {"name": "x" * 201},
]


@pytest.mark.parametrize("change", BAD_OLLAMA, ids=[str(c)[:40] for c in BAD_OLLAMA])
def test_a_bad_ollama_start_gives_400_and_sends_no_request(
    harness: Harness, change: dict[str, Any]
) -> None:
    response = harness.start(provider="ollama", **change)
    assert response.status_code == 400, response.text
    assert harness.net.pulls == [] and harness.net.calls() == 0
    assert harness.job.snapshot()["state"] == "idle"


def test_a_busy_ollama_start_does_not_contact_hugging_face(harness: Harness) -> None:
    assert harness.start(provider="ollama", name="qwen3").status_code == 202
    assert harness.net.started.wait(5)
    again = harness.start(**harness.llama())
    assert again.status_code == 409 and again.json()["reason"] == "busy"
    assert harness.net.calls() == 0
    harness.net.gate.set()
    harness.settle()


# ── Status and cancel ────────────────────────────────────────────────────


def test_the_status_of_a_new_server_is_idle_with_every_key(harness: Harness) -> None:
    body = harness.client.get(CURRENT).json()
    assert body == {
        "status": "ok",
        "state": "idle",
        "provider": None,
        "model": None,
        "model_value": None,
        "bytes_done": 0,
        "bytes_total": None,
        "reason": None,
        "cache_folder": None,
    }


def test_cancel_stops_the_running_download_and_answers_with_the_status(harness: Harness) -> None:
    assert harness.start(**harness.llama()).status_code == 202
    assert harness.net.started.wait(5)
    began = time.monotonic()
    response = harness.client.delete(CURRENT, headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert time.monotonic() - began < 5
    body = response.json()
    assert (body["state"], body["reason"], body["model_value"]) == ("cancelled", None, None)
    assert harness.client.get(CURRENT).json()["state"] == "cancelled"


def test_cancel_with_no_running_download_gives_409_and_changes_nothing(harness: Harness) -> None:
    response = harness.client.delete(CURRENT, headers=ORIGIN)
    assert response.status_code == 409
    assert response.json() == {"status": "error", "message": "No model download is running."}
    harness.net.gate.set()
    harness.start(**harness.llama())
    done = harness.settle()
    assert done["state"] == "succeeded"
    assert harness.client.delete(CURRENT, headers=ORIGIN).status_code == 409
    assert harness.client.get(CURRENT).json()["state"] == "succeeded"


# ── Start-up (task 6.4) and the contract ─────────────────────────────────


def test_start_up_and_the_connections_read_send_no_request_to_hugging_face(
    harness: Harness,
) -> None:
    response = harness.client.get("/v1/connections")
    assert response.status_code == 200
    sources = {c["provider"]: c["model_source"] for c in response.json()["connections"]}
    assert sources["llamacpp"] == "huggingface-gguf" and sources["ollama"] == "ollama-pull"
    assert sources["openrouter"] is None
    assert harness.client.get(CURRENT).status_code == 200
    assert harness.net.calls() == 0 and harness.net.pulls == []
    assert harness.sent == []


def test_model_download_responses_conform(harness: Harness) -> None:
    check = ContractChecker()
    c = harness.client
    check.check(c.get(SEARCH, params={"provider": "llamacpp", "q": "qwen3"}), 200)
    check.check(c.get(SEARCH, params={"provider": "ollama", "q": "qwen3"}), 200)
    check.check(c.get(SEARCH, params={"provider": "llamacpp", "q": ""}), 400)
    check.check(c.get(LISTING, params={"provider": "llamacpp", "repo": "a/b"}), 200)
    harness.net.list_error = hf.ModelHostError("not-found")
    check.check(c.get(LISTING, params={"provider": "llamacpp", "repo": "a/b"}), 404)
    harness.net.list_error = None
    check.check(c.get(CURRENT), 200)
    check.check(c.delete(CURRENT, headers=ORIGIN), 409)
    check.check(harness.start(**harness.llama(label="Q2_K")), 404)
    check.check(harness.start(**harness.llama(repo="../x")), 400)
    check.check(harness.start(**harness.llama()), 202)
    assert harness.net.started.wait(5)
    check.check(harness.start(**harness.llama()), 409)
    check.check(c.get(CURRENT), 200)
    check.check(c.delete(CURRENT, headers=ORIGIN), 200)
    harness.net.needed, harness.net.free = 9 * GB, 1 * GB
    check.check(harness.start(**harness.llama()), 409)
    harness.net.free = 100 * GB
    harness.net.repo_files = hf.RepoFiles("meta/x", REV, True, FILES)
    check.check(harness.start(**harness.llama()), 409)
    c.cookies.clear()
    read = bearer(harness.policy, "read")
    check.check(c.get(CURRENT, headers=read), 403)
    check.check(c.get(CURRENT), 401)
    assert check.operations >= FAMILIES["model_downloads"]
