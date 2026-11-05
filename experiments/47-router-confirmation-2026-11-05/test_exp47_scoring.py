"""Scoring tests: the shipped router path and the run guards (issue #171, points 4 to 10).

Every decision request goes to an ``httpx.MockTransport``. The shipped page
rules, page judge and llama.cpp and TypeSafe adapters run unchanged.

    uv run --no-sync pytest experiments/47-router-confirmation-2026-11-05 -q
"""

from __future__ import annotations

import json

import pytest
from conftest import (
    FakeModel,
    approve_hosted,
    fake_server,
    frozen_labels,
    passing_check,
    prepared,
)

import exp47_io
import score_router
from _lib.run_safety import RunStop, exclusive_lock


@pytest.fixture
def ready(ws, current, shipped_readers):
    """Inputs, frozen labels and a passing check record for the local arm."""
    prepared(ws)
    frozen_labels(ws)
    passing_check(current, "clef_router")
    return current


def run(plan, model, records=None, arm="clef_router", server=fake_server, **kwargs):
    records = records if records is not None else []
    return score_router.run_arm(
        arm,
        plan,
        limit=kwargs.pop("limit", None),
        resume=kwargs.pop("resume", False),
        server=server,
        record=lambda folder, runtime=None: records.append(runtime),
        transport=model.transport,
        scan=kwargs.pop("scan", None),
        clean=lambda path: True,
        corpus=exp47_io.CORPUS,
        memory=lambda: 100,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def _scan_default(ws, monkeypatch):
    monkeypatch.setattr(score_router, "_shipped_scan", lambda: ws.scan)


# ---------------------------------------------------------------- the shipped path


def test_shipped_router_rejects_junk_pages_and_keeps_good_ones(ready) -> None:
    model = FakeModel()
    payload = run(ready, model)
    rows = {(r["doc_id"], r["page"]): r for d in payload["documents"].values() for r in d["rows"]}
    assert {k for k, r in rows.items() if r["rejected"]} == {("jone", 1), ("jone", 2)}
    assert rows[("gone", 1)]["p_yes"] == 0.9
    assert payload["documents"]["jone"]["router_counts"]["status"] == "ok"
    assert all(len(t) <= 2000 for t in model.page_texts)


def test_resume_never_asks_a_scored_page_again(ready, ws) -> None:
    first = FakeModel()
    run(ready, first, limit=1)
    second = FakeModel()
    payload = run(ready, second, resume=True)
    assert sorted(payload["documents"]) == ["gone", "jone"]
    assert second.page_texts == [t for t, _ in ws.texts["gone.pdf"]]


def test_router_that_cannot_run_stops_instead_of_rejecting_nothing(ready) -> None:
    import httpx

    model = FakeModel()
    model.transport = httpx.MockTransport(lambda request: httpx.Response(501, json={}))
    with pytest.raises(RunStop, match="cannot run"):
        run(ready, model)


# ---------------------------------------------------------------- point 4: input hashes


def test_changed_page_text_stops_before_any_page_request(ready, ws) -> None:
    ws.texts["jone.pdf"][0] = ("junk read differently today", False)
    model = FakeModel()
    with pytest.raises(RunStop, match="page text differs from inputs.json"):
        run(ready, model)
    assert model.page_texts == []


def test_changed_page_image_stops(ready, monkeypatch) -> None:
    from omrs.integrations.pdf import page_images

    monkeypatch.setattr(page_images, "render_page", lambda pdf, page: b"another image")
    with pytest.raises(RunStop, match="page image differs"):
        run(ready, FakeModel())


# ---------------------------------------------------------------- point 6: lock before read


def test_held_lock_stops_before_the_checkpoint_is_read(ready, ws) -> None:
    target = ws.OUTPUT / "scores_clef_router.json"
    target.write_text("{ not json: a runner is writing it")
    with exclusive_lock(exp47_io.private_path("locks", "scores_clef_router.lock")):
        with pytest.raises(RunStop, match="another runner"):
            run(ready, FakeModel(), resume=True)


# ---------------------------------------------------------------- point 7: stop rules in code


def test_projected_time_over_the_limit_stops(ready) -> None:
    ready["stop_rules"].update(max_hours=1e-12, warmup_pages=0)
    model = FakeModel()
    with pytest.raises(RunStop, match="projected .* h"):
        run(ready, model)
    assert len(model.page_texts) == 1


def test_projected_cost_over_the_limit_stops_before_any_hosted_request(ready) -> None:
    approve_hosted(ready)
    passing_check(ready, "jev_router")
    ready["stop_rules"]["usd_per_hosted_page"] = 10.0
    model = FakeModel()
    with pytest.raises(RunStop, match="projected cost"):
        run(ready, model, arm="jev_router", server=score_router.hosted_endpoint)
    assert model.requests == 0


def test_too_many_failed_pages_stop(ready) -> None:
    import httpx

    ready["stop_rules"]["max_failed_pages"] = 0
    model = FakeModel()
    inner = model.handle

    def failing_pages(request):
        body = json.loads(request.content)
        if "junk" in body["state"]["text"]:
            return httpx.Response(500, json={})
        return inner(request)

    model.transport = httpx.MockTransport(failing_pages)
    with pytest.raises(RunStop, match="INCONCLUSIVE"):
        run(ready, model)


# ---------------------------------------------------------------- point 8: threshold every run


@pytest.mark.parametrize("threshold", [0.2, 0.17220524482651753])
def test_threshold_other_than_the_frozen_value_stops_every_run(ready, threshold) -> None:
    ready["arms"]["clef_router"]["threshold"] = threshold
    model = FakeModel()
    with pytest.raises(RunStop, match="not the frozen"):
        run(ready, model, limit=1)
    assert model.requests == 0


def test_uncommitted_plan_stops_every_run(ready) -> None:
    model = FakeModel()
    with pytest.raises(RunStop, match="commit plan.json"):
        score_router.run_arm(
            "clef_router",
            ready,
            limit=None,
            resume=False,
            server=fake_server,
            record=lambda *a, **k: None,
            transport=model.transport,
            clean=lambda path: path.name != "plan.json",
        )
    assert model.requests == 0


# ---------------------------------------------------------------- point 9: run record first


def test_run_record_is_written_before_the_first_hosted_request(ready) -> None:
    approve_hosted(ready)
    passing_check(ready, "jev_router")
    records: list = []
    seen: list[int] = []
    model = FakeModel(on_request=lambda request: seen.append(len(records)))
    run(ready, model, records=records, arm="jev_router", server=score_router.hosted_endpoint)
    assert seen and seen[0] == 1
    assert len(records) == 1


def test_hosted_arm_without_approval_sends_nothing_and_records_nothing(ready) -> None:
    for entry in ready["decision_register"]:  # the real plan approves it; take it back here
        if entry.get("scope") == "hosted_reference_arm":
            entry.update(status="NOT REQUESTED", date=None)
    passing_check(ready, "jev_router")
    records: list = []
    model = FakeModel()
    with pytest.raises(RunStop, match="no dated operator approval"):
        run(ready, model, records=records, arm="jev_router", server=score_router.hosted_endpoint)
    assert model.requests == 0 and records == []


def test_hosted_check_records_the_run_before_its_first_request(ready, monkeypatch) -> None:
    approve_hosted(ready)
    records: list = []
    seen: list[int] = []
    model = FakeModel(on_request=lambda request: seen.append(len(records)))
    result = score_router.runtime_check(
        "jev_router",
        ready,
        server=score_router.hosted_endpoint,
        record=lambda f, runtime=None: records.append(runtime),
        transport=model.transport,
        clean=lambda p: True,
    )
    assert result["passed"] and seen[0] == 1


# ---------------------------------------------------------------- point 10: check record first


def test_scoring_refuses_without_a_check_record(ready, ws) -> None:
    (ws.OUTPUT / "runtime_check_clef_router.json").unlink()
    model = FakeModel()
    with pytest.raises(RunStop, match="run --check first"):
        run(ready, model)
    assert model.requests == 0


def test_scoring_refuses_a_failed_no_projector_check(ready) -> None:
    passing_check(
        ready,
        "clef_router",
        checks={"R4_shipped_checks": {"pass": True}, "R5_no_projector": {"pass": False}},
    )
    model = FakeModel()
    with pytest.raises(RunStop, match="R5_no_projector"):
        run(ready, model)
    assert model.requests == 0


def test_scoring_refuses_a_stale_check_record(ready, ws) -> None:
    passing_check(ready, "clef_router")
    ws.INPUTS.write_text(ws.INPUTS.read_text() + " ")
    frozen_labels(ws)
    model = FakeModel()
    with pytest.raises(RunStop, match="another plan, input"):
        run(ready, model)
    assert model.requests == 0


# ---------------------------------------------------------------- labels before scores


def test_scoring_refuses_unfrozen_labels(ready, ws) -> None:
    review = exp47_io.read_json(ws.LABEL_REVIEW)
    review["pages"][0]["verdict"] = None
    exp47_io.atomic_json(ws.LABEL_REVIEW, review)
    with pytest.raises(RunStop, match="labels are not frozen"):
        run(ready, FakeModel())
