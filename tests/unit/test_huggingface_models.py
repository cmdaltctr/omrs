"""Tests for the Hugging Face read adapter (add-model-search-and-download, tasks 3.1 and 3.2).

Every request goes through ``httpx.MockTransport``. No test contacts the
network. The fixtures under ``tests/fixtures/huggingface_models/`` are
trimmed copies of the real ``unsloth/Qwen3-4B-GGUF`` responses.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from omrs.integrations import huggingface_models as hf
from omrs.integrations.huggingface_models import (
    MAX_TREE_PAGES,
    ModelHostError,
    RepoFiles,
    hub_cache_folder,
    list_repo_files,
    search_models,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "huggingface_models"
REPO = "unsloth/Qwen3-4B-GGUF"
SHA = "22c9fc8a8c7700b76a1789366280a6a5a1ad1120"
SEARCH_URL = (
    "https://huggingface.co/api/models?search=qwen3&filter=gguf&sort=downloads"
    "&direction=-1&limit=20&expand[]=downloads&expand[]=likes&expand[]=gated"
    "&expand[]=lastModified"
)
INFO_URL = f"https://huggingface.co/api/models/{REPO}?expand[]=sha&expand[]=gated"
TREE_URL = f"https://huggingface.co/api/models/{REPO}/tree/{SHA}?recursive=true"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload)


class TestSearchModels:
    """Task 3.1: the search read."""

    def test_sends_the_exact_query_url(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok(_fixture("search_qwen3_4b.json"))

        search_models("qwen3", client=_client(handler))

        assert [str(r.url) for r in seen] == [SEARCH_URL]
        assert seen[0].method == "GET"

    def test_query_text_is_percent_encoded(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok([])

        search_models("qwen3 4b&x=1", client=_client(handler))

        assert str(seen[0].url).startswith(
            "https://huggingface.co/api/models?search=qwen3%204b%26x%3D1&filter=gguf"
        )

    def test_parses_the_real_response(self) -> None:
        results = search_models(
            "qwen3", client=_client(lambda r: _ok(_fixture("search_qwen3_4b.json")))
        )

        assert len(results) == 5
        first = results[0]
        assert first.id == "unsloth/Qwen3.5-4B-GGUF"
        assert first.downloads == 1278241
        assert first.likes == 523
        assert first.gated is False
        assert first.last_modified == "2026-03-02T14:08:17.000Z"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(False, False), (True, True), ("auto", True), ("manual", True)],
    )
    def test_gated_is_normalised_to_a_bool(self, raw: object, expected: bool) -> None:
        payload = [{"id": "a/b", "gated": raw, "downloads": 1, "likes": 2}]

        results = search_models("a", client=_client(lambda r: _ok(payload)))

        assert results[0].gated is expected
        assert isinstance(results[0].gated, bool)

    def test_missing_counts_default_to_zero_and_no_date(self) -> None:
        results = search_models("a", client=_client(lambda r: _ok([{"id": "a/b"}])))

        assert results[0].downloads == 0
        assert results[0].likes == 0
        assert results[0].gated is False
        assert results[0].last_modified is None

    def test_empty_result_is_an_empty_list(self) -> None:
        assert search_models("zzz", client=_client(lambda r: _ok([]))) == []

    def test_sends_no_authorization_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_TOKEN", "hf_test_secret")
        monkeypatch.setenv("HUGGING_FACE_HUB_TOKEN", "hf_test_secret")
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return _ok([])

        search_models("qwen3", client=_client(handler))

        assert "authorization" not in {k.lower() for k in seen[0].headers}
        assert "hf_test_secret" not in str(seen[0].headers)

    def test_default_client_sends_no_authorization_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The client the adapter builds itself carries no credentials either."""
        monkeypatch.setenv("HF_TOKEN", "hf_test_secret")
        seen: list[httpx.Request] = []
        real_client = httpx.Client

        def build(**kwargs: object) -> httpx.Client:
            kwargs["transport"] = httpx.MockTransport(
                lambda request: (seen.append(request), _ok([]))[1]
            )
            return real_client(**kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(hf.httpx, "Client", build)

        search_models("qwen3")

        assert len(seen) == 1
        assert "authorization" not in {k.lower() for k in seen[0].headers}

    def test_request_timeout_is_ten_seconds(self) -> None:
        seen: list[dict[str, float | None]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.extensions["timeout"])
            return _ok([])

        search_models("qwen3", client=_client(handler))

        assert seen == [{"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0}]

    def test_timeout_maps_to_network(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(ModelHostError) as caught:
            search_models("qwen3", client=_client(handler))

        assert caught.value.reason == "network"

    def test_connection_error_maps_to_network(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(ModelHostError) as caught:
            search_models("qwen3", client=_client(handler))

        assert caught.value.reason == "network"

    @pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
    def test_http_error_maps_to_network(self, status: int) -> None:
        with pytest.raises(ModelHostError) as caught:
            search_models("qwen3", client=_client(lambda r: httpx.Response(status, text="no")))

        assert caught.value.reason == "network"

    @pytest.mark.parametrize(
        "payload",
        [{"models": []}, "text", 5, [1, 2], [{"downloads": 3}], [{"id": 7}]],
    )
    def test_unexpected_shape_maps_to_network(self, payload: object) -> None:
        with pytest.raises(ModelHostError) as caught:
            search_models("qwen3", client=_client(lambda r: _ok(payload)))

        assert caught.value.reason == "network"

    def test_non_json_body_maps_to_network(self) -> None:
        with pytest.raises(ModelHostError) as caught:
            search_models("q", client=_client(lambda r: httpx.Response(200, text="<html>")))

        assert caught.value.reason == "network"

    def test_oversized_body_maps_to_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(hf, "BODY_LIMIT", 1000)
        body = b"[" + b" " * 1500 + b"]"

        with pytest.raises(ModelHostError) as caught:
            search_models("q", client=_client(lambda r: httpx.Response(200, content=body)))

        assert caught.value.reason == "network"

    def test_body_at_the_limit_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(hf, "BODY_LIMIT", 1000)
        body = b"[" + b" " * 990 + b"]"

        assert search_models("q", client=_client(lambda r: httpx.Response(200, content=body))) == []

    def test_error_message_holds_only_the_reason(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("secret detail hf_abc", request=request)

        with pytest.raises(ModelHostError) as caught:
            search_models("q", client=_client(handler))

        assert str(caught.value) == "network"
        assert caught.value.__suppress_context__ is True


class TestRedirects:
    """A redirect to another host is refused (design D3)."""

    def test_redirect_to_another_host_is_refused(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            if request.url.host == "huggingface.co":
                return httpx.Response(302, headers={"location": "https://evil.example/x"})
            return _ok([])

        with pytest.raises(ModelHostError) as caught:
            search_models("q", client=_client(handler))

        assert caught.value.reason == "network"
        assert all("evil.example" not in url for url in seen)

    def test_redirect_to_plain_http_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.scheme == "https":
                return httpx.Response(302, headers={"location": "http://huggingface.co/x"})
            return _ok([])

        with pytest.raises(ModelHostError):
            search_models("q", client=_client(handler))

    def test_redirect_on_the_same_host_is_followed(self) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.path)
            if request.url.path == "/api/models":
                return httpx.Response(307, headers={"location": "/api/models/moved"})
            return _ok([{"id": "a/b"}])

        results = search_models("q", client=_client(handler))

        assert [r.id for r in results] == ["a/b"]
        assert seen == ["/api/models", "/api/models/moved"]

    def test_redirect_loop_is_cut_off(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": str(request.url)})

        with pytest.raises(ModelHostError) as caught:
            search_models("q", client=_client(handler))

        assert caught.value.reason == "network"


def _repo_handler(
    seen: list[str] | None = None,
    *,
    info: object | None = None,
    tree: object | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        url = str(request.url)
        if url == INFO_URL:
            return _ok(
                info if info is not None else _fixture("model_info_unsloth_Qwen3-4B-GGUF.json")
            )
        if url == TREE_URL:
            return _ok(tree if tree is not None else _fixture("tree_unsloth_Qwen3-4B-GGUF.json"))
        return httpx.Response(404, json={"error": "Repository not found"})

    return handler


class TestListRepoFiles:
    """Task 3.2: the file list."""

    def test_reads_the_model_then_the_tree_at_its_revision(self) -> None:
        seen: list[str] = []

        list_repo_files(REPO, client=_client(_repo_handler(seen)))

        assert seen == [INFO_URL, TREE_URL]

    def test_returns_only_gguf_files_with_tree_sizes(self) -> None:
        result = list_repo_files(REPO, client=_client(_repo_handler()))

        assert isinstance(result, RepoFiles)
        assert result.repo == REPO
        assert result.revision == SHA
        assert result.gated is False
        sizes = dict(result.files)
        assert len(sizes) == 26
        assert all(path.endswith(".gguf") for path in sizes)
        assert sizes["Qwen3-4B-Q4_K_M.gguf"] == 2497281312
        assert "README.md" not in sizes
        assert "config.json" not in sizes

    def test_gated_comes_from_the_model_read(self) -> None:
        info = {"id": REPO, "sha": SHA, "gated": "manual"}

        result = list_repo_files(REPO, client=_client(_repo_handler(info=info)))

        assert result.gated is True

    def test_directory_entries_and_nested_gguf_paths(self) -> None:
        tree = [
            {"type": "directory", "path": "BF16", "oid": "x", "size": 0},
            {"type": "file", "path": "BF16/m-BF16-00001-of-00002.gguf", "size": 10},
            {"type": "file", "path": "BF16/m-BF16-00002-of-00002.gguf", "size": 20},
            {"type": "directory", "path": "dir.gguf", "size": 0},
        ]

        result = list_repo_files(REPO, client=_client(_repo_handler(tree=tree)))

        assert result.files == (
            ("BF16/m-BF16-00001-of-00002.gguf", 10),
            ("BF16/m-BF16-00002-of-00002.gguf", 20),
        )

    def test_reads_the_tree_at_a_given_revision(self) -> None:
        older = "a" * 40
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            if str(request.url) == INFO_URL:
                return _ok({"id": REPO, "sha": SHA, "gated": "auto"})
            return _ok([{"type": "file", "path": "m-Q4_K_M.gguf", "size": 1}])

        result = list_repo_files(REPO, revision=older, client=_client(handler))

        assert seen[-1] == f"https://huggingface.co/api/models/{REPO}/tree/{older}?recursive=true"
        assert (result.revision, result.gated) == (older, True)

    def test_follows_the_tree_link_header_to_the_last_page(self) -> None:
        # The tree endpoint pages its entries and names the next page in a Link header.
        page2 = f"https://huggingface.co/api/models/{REPO}/tree/{SHA}?recursive=true&cursor=abc"
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            seen.append(url)
            if url == INFO_URL:
                return _ok({"id": REPO, "sha": SHA})
            if url == TREE_URL:
                link = {"Link": f'<{page2}>; rel="next"'}
                entry = {"type": "file", "path": "m-Q4_K_M.gguf", "size": 1}
                return httpx.Response(200, json=[entry], headers=link)
            if url == page2:
                return _ok([{"type": "file", "path": "m-Q8_0.gguf", "size": 2}])
            return httpx.Response(404, json={})

        result = list_repo_files(REPO, client=_client(handler))

        assert seen == [INFO_URL, TREE_URL, page2]
        assert result.files == (("m-Q4_K_M.gguf", 1), ("m-Q8_0.gguf", 2))

    def test_a_next_page_on_another_host_is_network(self) -> None:
        hosts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hosts.append(request.url.host)
            if str(request.url) == INFO_URL:
                return _ok({"id": REPO, "sha": SHA})
            link = {"Link": '<https://evil.example/next>; rel="next"'}
            entry = {"type": "file", "path": "m-Q4_K_M.gguf", "size": 1}
            return httpx.Response(200, json=[entry], headers=link)

        with pytest.raises(ModelHostError) as caught:
            list_repo_files(REPO, client=_client(handler))

        assert caught.value.reason == "network"
        assert hosts == ["huggingface.co", "huggingface.co"]

    def test_endless_tree_pages_stop_with_network(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if len(calls) > 50:
                raise AssertionError("the tree read did not stop")
            if str(request.url) == INFO_URL:
                return _ok({"id": REPO, "sha": SHA})
            link = {"Link": f'<{TREE_URL}&cursor=again>; rel="next"'}
            entry = {"type": "file", "path": "m-Q4_K_M.gguf", "size": 1}
            return httpx.Response(200, json=[entry], headers=link)

        with pytest.raises(ModelHostError) as caught:
            list_repo_files(REPO, client=_client(handler))

        assert caught.value.reason == "network"
        assert len(calls) == 1 + MAX_TREE_PAGES

    def test_model_404_is_not_found(self) -> None:
        with pytest.raises(ModelHostError) as caught:
            list_repo_files("nobody/none", client=_client(lambda r: httpx.Response(404, json={})))

        assert caught.value.reason == "not-found"

    def test_tree_404_is_not_found(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == INFO_URL:
                return _ok(_fixture("model_info_unsloth_Qwen3-4B-GGUF.json"))
            return httpx.Response(404, json={})

        with pytest.raises(ModelHostError) as caught:
            list_repo_files(REPO, client=_client(handler))

        assert caught.value.reason == "not-found"

    def test_no_gguf_file_is_not_found(self) -> None:
        tree = [{"type": "file", "path": "README.md", "size": 5}]

        with pytest.raises(ModelHostError) as caught:
            list_repo_files(REPO, client=_client(_repo_handler(tree=tree)))

        assert caught.value.reason == "not-found"

    @pytest.mark.parametrize("status", [401, 403, 500])
    def test_other_http_errors_are_network(self, status: int) -> None:
        with pytest.raises(ModelHostError) as caught:
            list_repo_files(REPO, client=_client(lambda r: httpx.Response(status)))

        assert caught.value.reason == "network"

    @pytest.mark.parametrize(
        ("info", "tree"),
        [
            ({"id": REPO}, None),
            ({"id": REPO, "sha": 5}, None),
            (["x"], None),
            (None, {"files": []}),
            (None, [{"type": "file", "path": "a.gguf"}]),
            (None, [{"type": "file", "path": "a.gguf", "size": "big"}]),
        ],
    )
    def test_unexpected_shape_is_network(self, info: object, tree: object) -> None:
        with pytest.raises(ModelHostError) as caught:
            list_repo_files(REPO, client=_client(_repo_handler(info=info, tree=tree)))

        assert caught.value.reason == "network"

    def test_timeout_is_network(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("slow", request=request)

        with pytest.raises(ModelHostError) as caught:
            list_repo_files(REPO, client=_client(handler))

        assert caught.value.reason == "network"

    def test_sends_no_authorization_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_TOKEN", "hf_test_secret")
        headers: list[httpx.Headers] = []

        def handler(request: httpx.Request) -> httpx.Response:
            headers.append(request.headers)
            return _repo_handler()(request)

        list_repo_files(REPO, client=_client(handler))

        assert len(headers) == 2
        assert all("authorization" not in {k.lower() for k in h} for h in headers)

    def test_oversized_tree_is_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(hf, "BODY_LIMIT", 2000)
        tree = [{"type": "file", "path": f"f{i}.gguf", "size": 1} for i in range(200)]

        with pytest.raises(ModelHostError) as caught:
            list_repo_files(REPO, client=_client(_repo_handler(tree=tree)))

        assert caught.value.reason == "network"


class TestHubCacheFolder:
    """The folder the download writes to."""

    def test_returns_the_hub_cache_constant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from huggingface_hub import constants

        monkeypatch.setattr(constants, "HF_HUB_CACHE", "/scratch/hub")

        assert hub_cache_folder() == "/scratch/hub"

    def test_returns_a_string(self) -> None:
        assert isinstance(hub_cache_folder(), str)
        assert hub_cache_folder().endswith("hub")


def test_importing_the_module_does_not_import_huggingface_hub() -> None:
    """Integrations rule 1: the library is imported inside functions only."""
    code = (
        "import sys, omrs.integrations.huggingface_models;"
        "sys.exit(1 if 'huggingface_hub' in sys.modules else 0)"
    )

    result = subprocess.run([sys.executable, "-I", "-c", code], check=False)

    assert result.returncode == 0
