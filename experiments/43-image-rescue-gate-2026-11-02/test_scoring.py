"""Fake-server tests for the two image arms (tasks 3.2 and 3.5).

    uv run --no-sync pytest experiments/43-image-rescue-gate-2026-11-02 -q
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clients  # noqa: E402
import score_pages  # noqa: E402

STAND_IN = "stand-in-value-for-tests"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake image bytes"
QUESTION = "Does the text match the text written or printed on the page image?"


class FakeServer:
    """Record each request and answer from a queue of (status, body) pairs."""

    def __init__(self, replies: list[tuple[int, dict]]) -> None:
        self.requests: list[dict] = []
        self.replies = replies
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                headers = {k.lower(): v for k, v in self.headers.items()}
                outer.requests.append({"headers": headers, "body": body})
                status, reply = outer.replies.pop(0) if len(outer.replies) > 1 else outer.replies[0]
                data = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()


def noul(p: float, model: str = "jev-1.14.0") -> tuple[int, dict]:
    return 200, {
        "model": model,
        "answers": {"fidelity": {"type": "noul", "noul": p}},
        "usage": {"input_tokens": 1500, "output_tokens": 1},
    }


@pytest.fixture
def fake():
    servers: list[FakeServer] = []

    def make(replies: list[tuple[int, dict]]) -> FakeServer:
        servers.append(FakeServer(replies))
        return servers[-1]

    yield make
    for server in servers:
        server.close()


def test_local_request_holds_image_and_text_head(fake) -> None:
    server = fake([noul(0.9, "/home/someone/models/Clef-Flash-Q8_0.gguf")])
    text = "a" * 1500 + "b" * 1500
    result = clients.LocalClient(server.url, QUESTION).score(text, PNG)
    body = server.requests[0]["body"]
    assert result["p_yes"] == 0.9
    assert result["model"] == "Clef-Flash-Q8_0.gguf"
    assert body["state"]["text"] == text[:2000]
    assert len(body["images"]) == 1
    encoded = body["images"][0].split(",", 1)[-1]
    assert base64.b64decode(encoded) == PNG
    assert body["questions"]["fidelity"] == {"type": "noul", "instructions": QUESTION}


def test_hosted_request_shape_and_header(fake, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    server = fake([noul(0.3)])
    client = clients.HostedClient(QUESTION, "jev-1.14.0", endpoint=server.url + "/v1/systemone")
    image_id = clients.placeholder("bd01", 2)
    result = client.score("x" * 2500, PNG, image_id)
    request = server.requests[0]
    body = request["body"]
    assert request["headers"]["typesafe-danger-zone-images"] == "true"
    assert request["headers"]["authorization"] == f"Bearer {STAND_IN}"
    assert body["model"] == "jev-1.14.0"
    assert body["state"] == {"page_image": image_id, "text": "x" * 2000}
    asset = body["assets"][image_id]
    assert asset["type"] == "image" and asset["format"] == "png"
    assert not asset["data_base64"].startswith("data:")
    assert base64.b64decode(asset["data_base64"]) == PNG
    assert result["model"] == "jev-1.14.0" and result["input_tokens"] == 1500


def test_hosted_error_never_shows_the_key(fake, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    server = fake([(400, {"detail": f"bad token {STAND_IN}"})])
    client = clients.HostedClient(QUESTION, "jev-1.14.0", endpoint=server.url)
    with pytest.raises(RuntimeError) as error:
        client.score("text", PNG, "id")
    assert "HTTP 400" in str(error.value)
    assert STAND_IN not in str(error.value)
    assert STAND_IN not in repr(client)


def test_hosted_error_hides_a_key_that_crosses_the_cut(fake, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    # The JSON body opens with '{"detail": "' (12 characters), so the key starts at 290.
    server = fake([(400, {"detail": "x" * 278 + STAND_IN})])
    client = clients.HostedClient(QUESTION, "jev-1.14.0", endpoint=server.url)
    with pytest.raises(RuntimeError) as error:
        client.score("text", PNG, "id")
    assert STAND_IN[:10] not in str(error.value)


@pytest.mark.parametrize("value", [True, False])
def test_boolean_noul_is_rejected(value) -> None:
    with pytest.raises(ValueError, match="probability bounds"):
        clients.parse_noul({"answers": {"fidelity": {"type": "noul", "noul": value}}})


def test_missing_key_stops(monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="not set"):
        clients.HostedClient(QUESTION, "jev-1.14.0")


def test_server_without_projector_stops_runner() -> None:
    with pytest.raises(SystemExit, match="without the projector"):
        score_pages.check_projector(score_pages.server_command(None), "0" * 64)
    assert "--mmproj" in score_pages.server_command(Path("p.gguf"))


# ---------------------------------------------------------------- runner on fake data


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Two documents: a fit page, a junk page and an empty page, with fake renders."""
    output = tmp_path / "output"
    renders, texts = output / ".renders", output / ".rescue_text"
    rows = []
    for doc_id, pages in (("bd01", ["healthy text one", "healthy text two"]),
                          ("rf06", ["INT , L/ NUI", ""])):  # fmt: skip
        (texts / doc_id).mkdir(parents=True)
        (texts / doc_id / "liteparse.json").write_text(json.dumps(pages))
        (renders / doc_id).mkdir(parents=True)
        for number, text in enumerate(pages, start=1):
            data = PNG + doc_id.encode() + bytes([number])
            (renders / doc_id / f"p{number:03d}.png").write_bytes(data)
            rows.append({
                "doc_id": doc_id, "page": number,
                "class": "healthy" if doc_id == "bd01" else ("junk" if text else "excluded"),
                "scored": bool(text.strip()), "png_sha256": hashlib.sha256(data).hexdigest(),
            })  # fmt: skip
    (output / "inputs.json").write_text(json.dumps({"rows": rows}))
    for name in ("OUTPUT", "RENDERS", "TEXTS"):
        monkeypatch.setattr(score_pages, name, {"OUTPUT": output, "RENDERS": renders,
                                                "TEXTS": texts}[name])  # fmt: skip
    monkeypatch.setattr(score_pages, "check_memory", lambda: None)
    monkeypatch.setattr(score_pages, "git_clean", lambda path: True)
    current = {
        "request": {"question": QUESTION, "text_head_chars": 2000},
        "runtime": {"models": [{"sha256": "f" * 64}]},
        "arms": {"jev_image": {"model": "jev-1.14.0"}},
        "thresholds": {"clef_image": {"value": None}, "jev_image": {"value": 0.5}},
        "decision_register": [{"status": "APPROVED", "date": "2026-11-02", "provider": "TypeSafe",
                               "documents": "all 40, including rf06 and rf07"}],  # fmt: skip
    }
    return output, current


def hosted_scorer(server: FakeServer, current: dict):
    current["arms"]["jev_image"]["endpoint"] = server.url
    client = clients.HostedClient(QUESTION, "jev-1.14.0", endpoint=server.url)
    return lambda row, text, png: client.score(text, png, clients.placeholder(row["doc_id"], row["page"]))


def test_fit_phase_scores_only_healthy_pages_and_resume_does_not_rescore(
    fake, workspace, monkeypatch
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    output, current = workspace
    server = fake([noul(0.8)])
    score = hosted_scorer(server, current)
    score_pages.run_pages("jev_image", "fit", score, current, limit=1, resume=False)
    score_pages.run_pages("jev_image", "fit", score, current, limit=None, resume=True)
    saved = json.loads((output / "scores_jev_image.json").read_text())
    assert [(r["doc_id"], r["page"]) for r in saved["rows"]] == [("bd01", 1), ("bd01", 2)]
    assert len(server.requests) == 2
    assert all(r["model"] == "jev-1.14.0" for r in saved["rows"])
    assert STAND_IN not in (output / "scores_jev_image.json").read_text()


def test_rest_phase_needs_committed_threshold(workspace) -> None:
    _, current = workspace
    with pytest.raises(SystemExit, match="threshold"):
        score_pages.run_pages("clef_image", "rest", lambda *a: {}, current, None, False)


def test_rest_phase_skips_empty_pages(fake, workspace, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    output, current = workspace
    server = fake([noul(0.1)])
    score_pages.run_pages("jev_image", "rest", hosted_scorer(server, current), current, None, False)
    saved = json.loads((output / "scores_jev_image.json").read_text())
    assert [(r["doc_id"], r["page"]) for r in saved["rows"]] == [("rf06", 1)]


def test_model_id_change_stops_the_run(fake, workspace, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    output, current = workspace
    server = fake([noul(0.8, "jev-1.14.0"), noul(0.8, "jev-1.15.0")])
    with pytest.raises(SystemExit, match="model id changed"):
        score_pages.run_pages("jev_image", "fit", hosted_scorer(server, current), current, None, False)
    saved = json.loads((output / "scores_jev_image.json").read_text())
    assert len(saved["rows"]) == 1


def test_hosted_refusal_stops_the_run(fake, workspace, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    _, current = workspace
    server = fake([(403, {"detail": "images not allowed"})])
    with pytest.raises(SystemExit, match="refused"):
        score_pages.run_pages("jev_image", "fit", hosted_scorer(server, current), current, None, False)


def test_failed_page_is_retried_on_resume_and_stops_counting(fake, workspace, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    monkeypatch.setattr(clients.time, "sleep", lambda s: None)
    monkeypatch.setattr(score_pages, "MAX_FAILURES", 0)
    output, current = workspace
    overloaded = (503, {"detail": "Image processing is unavailable."})
    server = fake([overloaded, overloaded, overloaded, noul(0.8)])
    with pytest.raises(SystemExit, match="failed pages"):
        score_pages.run_pages("jev_image", "fit", hosted_scorer(server, current), current, None, False)
    score_pages.run_pages("jev_image", "fit", hosted_scorer(server, current), current, None, True)
    saved = json.loads((output / "scores_jev_image.json").read_text())
    assert [(r["doc_id"], r["page"]) for r in saved["rows"]] == [("bd01", 1), ("bd01", 2)]
    assert len(saved["failures"]) == 1
    assert score_pages.unscored_failures(saved) == set()


def test_hosted_arm_needs_approval(workspace, monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", STAND_IN)
    _, current = workspace
    current["decision_register"] = [{"status": "APPROVED", "date": "2026-11-02"}]
    with pytest.raises(SystemExit, match="approval"):
        score_pages.make_scorer("jev_image", current)
