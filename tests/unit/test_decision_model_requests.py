"""Decision model registry and request shapes (document-reading-routers task 2.1).

The shapes follow the Experiment 43 runners: llama-server takes the page image
in an ``images`` list as a data URL; TypeSafe takes it in ``assets`` with the
``TypeSafe-Danger-Zone-Images: true`` header. Only a hosted image request
carries that header. No test contacts a real model.
"""

from __future__ import annotations

import base64
import logging
import math

import pytest

from omrs.core.providers.decision import base, registry

PNG = b"\x89PNG\r\n\x1a\nfake"
HEADER = "TypeSafe-Danger-Zone-Images"


def _request(kind: str, *, address: str, image: bytes | None, key: str | None = None):
    adapter = registry.get(kind)
    return adapter.build_request(
        address=address,
        model="clef-flash",
        question="Does the text match the page?",
        text="page text",
        image=image,
        key=key,
        hosted=not base.is_loopback(address),
    )


def test_four_kinds_are_registered() -> None:
    assert registry.kinds() == ["cloudflare", "llamacpp", "ollama", "typesafe"]


def test_unknown_kind_names_the_registered_kinds() -> None:
    with pytest.raises(KeyError, match="llamacpp"):
        registry.get("foo")


def test_untested_kinds_are_labelled() -> None:
    assert registry.not_yet_tested() == ["cloudflare", "ollama"]
    assert registry.get("cloudflare").NOT_YET_TESTED is True
    assert registry.get("llamacpp").NOT_YET_TESTED is False


def test_llamacpp_request_shape() -> None:
    request = _request("llamacpp", address="http://127.0.0.1:9931/", image=PNG)
    assert request.url == "http://127.0.0.1:9931/v1/systemone"
    assert request.body == {
        "model": "clef-flash",
        "state": {"text": "page text"},
        "images": ["data:image/png;base64," + base64.b64encode(PNG).decode("ascii")],
        "questions": {
            "fidelity": {"type": "noul", "instructions": "Does the text match the page?"}
        },
    }


def test_llamacpp_text_request_has_no_images() -> None:
    request = _request("llamacpp", address="http://127.0.0.1:9931", image=None)
    assert "images" not in request.body
    assert request.body["questions"]["fidelity"]["type"] == "noul"


def test_local_image_request_has_no_hosted_header() -> None:
    request = _request("llamacpp", address="http://localhost:9931", image=PNG)
    assert HEADER not in request.headers


def test_typesafe_image_request_shape_and_header() -> None:
    request = _request("typesafe", address="https://api.typesafe.ai", image=PNG, key="k-1")
    assert request.url == "https://api.typesafe.ai/v1/systemone"
    assert request.headers[HEADER] == "true"
    assert request.headers["Authorization"] == "Bearer k-1"
    state = request.body["state"]
    asset = request.body["assets"][state["page_image"]]
    assert asset == {
        "type": "image",
        "format": "png",
        "data_base64": base64.b64encode(PNG).decode("ascii"),
    }
    assert state["text"] == "page text"
    assert "images" not in request.body


def test_hosted_text_request_has_no_image_header() -> None:
    request = _request("typesafe", address="https://api.typesafe.ai", image=None, key="k")
    assert HEADER not in request.headers
    assert "assets" not in request.body


def test_cloudflare_request_shape() -> None:
    address = "https://api.cloudflare.com/client/v4/accounts/abc"
    request = _request("cloudflare", address=address, image=PNG, key="t")
    assert request.url == address + "/ai/run/@cf/cloudflare/clef-flash"
    assert request.body["images"] == [base64.b64encode(PNG).decode("ascii")]
    assert request.headers[HEADER] == "true"
    assert request.headers["Authorization"] == "Bearer t"


def test_cloudflare_reply_is_unwrapped() -> None:
    reply = {"result": {"answers": {"fidelity": {"noul": 0.25}}}, "success": True}
    assert registry.get("cloudflare").read_reply(reply) == 0.25


def test_ollama_request_shape() -> None:
    request = _request("ollama", address="http://127.0.0.1:11434", image=PNG)
    assert request.url == "http://127.0.0.1:11434/v1/systemone"
    assert request.body["model"] == "clef-flash"
    assert request.body["images"] == [base64.b64encode(PNG).decode("ascii")]
    assert HEADER not in request.headers


def test_request_repr_hides_key_and_body() -> None:
    request = _request("typesafe", address="https://api.typesafe.ai", image=None, key="secret-k")
    assert "secret-k" not in repr(request)
    assert "page text" not in repr(request)


@pytest.mark.parametrize("address", ["http://127.0.0.1:1", "http://localhost", "http://[::1]:8"])
def test_loopback_is_local(address: str) -> None:
    assert base.is_loopback(address)


@pytest.mark.parametrize("address", ["https://api.typesafe.ai", "http://192.168.1.5:8080"])
def test_other_addresses_are_hosted(address: str) -> None:
    assert not base.is_loopback(address)


@pytest.mark.parametrize("value", [0.0, 0.42, 1, 1.0])
def test_p_yes_in_bounds(value: float) -> None:
    assert base.parse_p_yes({"answers": {"fidelity": {"noul": value}}}) == float(value)


@pytest.mark.parametrize(
    "reply",
    [
        {"answers": {"fidelity": {"noul": math.nan}}},
        {"answers": {"fidelity": {"noul": math.inf}}},
        {"answers": {"fidelity": {"noul": -0.01}}},
        {"answers": {"fidelity": {"noul": 1.01}}},
        {"answers": {"fidelity": {"noul": True}}},
        {"answers": {"fidelity": {"noul": "0.5"}}},
        {"answers": {}},
        {"error": "private reply text"},
        "private reply text",
    ],
)
def test_malformed_reply_has_a_fixed_reason(reply, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(base.MalformedReplyError) as error:
        base.parse_p_yes(reply)
    assert str(error.value) == base.MALFORMED_REPLY
    assert "private reply text" not in caplog.text
    assert "private reply text" not in str(error.value)
