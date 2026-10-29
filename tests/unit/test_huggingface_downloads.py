"""Tests for the Hugging Face download helpers (add-model-search-and-download, task 3.4).

``hf_hub_download`` is replaced on ``huggingface_hub`` itself, because the
adapter imports it inside the function (ADR-024). No test uses the network.
"""

from __future__ import annotations

import httpx
import pytest

from omrs.integrations import huggingface_models as hf
from omrs.integrations.huggingface_models import ModelHostError

REPO = "unsloth/Qwen3-4B-GGUF"
SHA = "22c9fc8a8c7700b76a1789366280a6a5a1ad1120"


def _dry(size: int, *, will_download: bool) -> object:
    from huggingface_hub import DryRunFileInfo

    return DryRunFileInfo(
        commit_hash=SHA,
        file_size=size,
        filename="x.gguf",
        local_path="/scratch/x.gguf",
        is_cached=not will_download,
        will_download=will_download,
    )


class TestBytesToDownload:
    """Task 3.4: the size still to download, from ``hf_hub_download(dry_run=True)``."""

    def test_sums_the_sizes_of_files_that_will_download(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import huggingface_hub

        calls: list[dict[str, object]] = []
        sizes = {"a-00001-of-00002.gguf": 30, "a-00002-of-00002.gguf": 70}

        def fake(**kwargs: object) -> object:
            calls.append(kwargs)
            return _dry(sizes[str(kwargs["filename"])], will_download=True)

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake)

        total = hf.bytes_to_download(REPO, SHA, list(sizes), token=None)

        assert total == 100
        assert [c["filename"] for c in calls] == list(sizes)
        assert all(c["repo_id"] == REPO for c in calls)
        assert all(c["revision"] == SHA for c in calls)
        assert all(c["dry_run"] is True for c in calls)

    def test_cached_files_count_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import huggingface_hub

        states = {"a.gguf": True, "b.gguf": False}
        monkeypatch.setattr(
            huggingface_hub,
            "hf_hub_download",
            lambda **kw: _dry(50, will_download=states[str(kw["filename"])]),
        )

        assert hf.bytes_to_download(REPO, SHA, ["a.gguf", "b.gguf"], token=None) == 50

    def test_all_cached_is_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import huggingface_hub

        monkeypatch.setattr(
            huggingface_hub, "hf_hub_download", lambda **kw: _dry(99, will_download=False)
        )

        assert hf.bytes_to_download(REPO, SHA, ["a.gguf"], token="hf_x") == 0  # noqa: S106

    def test_token_is_passed_and_a_missing_token_disables_the_stored_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import huggingface_hub

        tokens: list[object] = []

        def fake(**kwargs: object) -> object:
            tokens.append(kwargs["token"])
            return _dry(1, will_download=True)

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake)

        hf.bytes_to_download(REPO, SHA, ["a.gguf"], token="hf_test_secret")  # noqa: S106
        hf.bytes_to_download(REPO, SHA, ["a.gguf"], token=None)

        assert tokens == ["hf_test_secret", False]

    @pytest.mark.parametrize(
        ("status", "reason"),
        [(401, "gated"), (403, "gated"), (404, "not-found"), (500, "network")],
    )
    def test_http_errors_map_to_reasons(
        self, monkeypatch: pytest.MonkeyPatch, status: int, reason: str
    ) -> None:
        import huggingface_hub
        from huggingface_hub.errors import HfHubHTTPError

        def fake(**kwargs: object) -> object:
            response = httpx.Response(
                status, request=httpx.Request("GET", "https://huggingface.co/x")
            )
            raise HfHubHTTPError("secret detail hf_abc", response=response)

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake)

        with pytest.raises(ModelHostError) as caught:
            hf.bytes_to_download(REPO, SHA, ["a.gguf"], token=None)

        assert caught.value.reason == reason
        assert str(caught.value) == reason

    def test_gated_repo_error_is_gated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import huggingface_hub
        from huggingface_hub.errors import GatedRepoError

        def fake(**kwargs: object) -> object:
            response = httpx.Response(403, request=httpx.Request("GET", "https://huggingface.co/x"))
            raise GatedRepoError("gated", response=response)

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake)

        with pytest.raises(ModelHostError) as caught:
            hf.bytes_to_download(REPO, SHA, ["a.gguf"], token=None)

        assert caught.value.reason == "gated"

    @pytest.mark.parametrize("error", [OSError("disk"), ConnectionError("down"), RuntimeError("x")])
    def test_other_errors_map_to_network(
        self, monkeypatch: pytest.MonkeyPatch, error: Exception
    ) -> None:
        import huggingface_hub

        def fake(**kwargs: object) -> object:
            raise error

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake)

        with pytest.raises(ModelHostError) as caught:
            hf.bytes_to_download(REPO, SHA, ["a.gguf"], token=None)

        assert caught.value.reason == "network"
        assert str(caught.value) == "network"


class TestHasRoom:
    """The free-space rule (spec "Free space is checked first")."""

    GIB = 1024**3

    def test_margin_is_one_gibibyte(self) -> None:
        assert hf.SPACE_MARGIN_BYTES == self.GIB

    def test_refuses_when_free_is_below_size_plus_margin(self) -> None:
        assert hf.has_room(9_700_000_000, 5_000_000_000) is False
        assert hf.has_room(100, 100 + self.GIB - 1) is False

    def test_accepts_when_free_equals_size_plus_margin(self) -> None:
        assert hf.has_room(100, 100 + self.GIB) is True

    def test_nothing_to_download_needs_no_space(self) -> None:
        assert hf.has_room(0, 0) is True
