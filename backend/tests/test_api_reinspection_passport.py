"""Endpoint 12 (reinspection) and endpoint 13 (quality passport)."""
import re
import threading

import pytest

from .helpers import (
    PDF, jpeg_bytes, make_cabinet, make_inspection, make_revision, manual_box, png_bytes, post_observations,
    setup_inspection,
)
from .test_api_contract_and_errors import assert_plain, image_of, snapshot


def run(api, inspection_id):
    assert api.post(f"/api/inspections/{inspection_id}/run").status_code == 202
    return api.get(f"/api/inspections/{inspection_id}").json()


def done_inspection(api, tags=("CB11", "PS11"), read=("CB11",)):
    inspection_id, revision = setup_inspection(api, tags=tags)
    post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box(f"O{i}", t) for i, t in enumerate(read)])
    return inspection_id, revision, run(api, inspection_id)


def reinspect(api, inspection_id, photos=None):
    photos = photos if photos is not None else [png_bytes(50, 40)]
    files = [("photos", (f"r{i}.png", p, "image/png")) for i, p in enumerate(photos)]
    return api.post(f"/api/inspections/{inspection_id}/reinspection", files=files or None)


def review(api, finding_id, decision, reviewer="Archita"):
    return api.post(f"/api/findings/{finding_id}/review", json={"decision": decision, "reviewer": reviewer, "note": "n"})


# ---------- 12 reinspection ----------
def test_reinspection_creates_a_linked_queued_inspection_on_the_same_revision(api):
    first, revision, first_detail = done_inspection(api)
    r = reinspect(api, first)
    assert r.status_code == 202, r.text
    body = r.json()
    assert set(body) == {"inspection_id", "state", "previous_inspection_id"}
    assert body["state"] == "queued" and body["previous_inspection_id"] == first and body["inspection_id"] != first
    new = api.get(f"/api/inspections/{body['inspection_id']}").json()
    assert new["previous_inspection_id"] == first and new["cabinet_id"] == "CAB-001"
    assert new["design_revision_internal_id"] == revision and new["design_revision_id"] == "REV-A"
    assert new["state"] == "queued" and new["findings"] == [] and new["overall_status"] is None
    assert [(i["width"], i["height"]) for i in new["images"]] == [(50, 40)]
    assert new["images"][0]["image_id"] != first_detail["images"][0]["image_id"]  # its own stored photos


def test_the_previous_inspection_findings_and_reviews_are_untouched(api):
    first, _, detail = done_inspection(api)
    unread = next(f for f in detail["findings"] if f["tag"] == "PS11")["finding_id"]
    review(api, unread, "confirmed_by_reviewer")
    before_first = api.get(f"/api/inspections/{first}").json()
    rows_before = snapshot(api)[0]
    second = reinspect(api, first).json()["inspection_id"]
    assert api.get(f"/api/inspections/{first}").json() == before_first
    rows_after = snapshot(api)[0]
    for table in ("findings", "review_events", "observations", "expected_items", "design_revisions", "cabinets"):
        assert rows_after[table] == rows_before[table], table
    assert len(rows_after["inspections"]) == len(rows_before["inspections"]) + 1
    assert second in [row[0] for row in rows_after["inspections"]]


def test_reinspection_never_marks_anything_resolved_by_itself(api):
    first, _, _ = done_inspection(api)
    second = reinspect(api, first).json()["inspection_id"]
    post_observations(api, second, image_of(api, second), [manual_box("A", "CB11"), manual_box("B", "PS11")])
    new = run(api, second)
    assert {f["tag"]: f["status"] for f in new["findings"]} == {"CB11": "verified", "PS11": "verified"}
    old = api.get(f"/api/inspections/{first}").json()
    assert {f["tag"]: f["status"] for f in old["findings"]} == {"CB11": "verified", "PS11": "inconclusive"}
    assert "resolved_after_reinspection" not in str(api.get(f"/api/inspections/{first}").json()["findings"])


def test_a_reinspection_can_be_reinspected_after_it_is_done(api):
    first, _, _ = done_inspection(api)
    second = reinspect(api, first).json()["inspection_id"]
    run(api, second)
    third = reinspect(api, second)
    assert third.status_code == 202 and third.json()["previous_inspection_id"] == second


def test_reinspection_validation_errors(api):
    first, _, _ = done_inspection(api)
    before = snapshot(api)
    assert_plain(reinspect(api, "INS-NOPE"), 404, "Inspection not found")
    assert_plain(reinspect(api, first, []), 400, "between 1 and 10")
    assert_plain(reinspect(api, first, [png_bytes()] * 11), 400, "between 1 and 10")
    assert_plain(reinspect(api, first, [png_bytes(), PDF]), 400, "Photo 2")
    assert_plain(reinspect(api, first, [png_bytes(), png_bytes()[:-9]]), 400, "damaged or truncated")
    assert_plain(reinspect(api, first, [b""]), 400, "empty")
    big = reinspect(api, first, [png_bytes() + b"\x00" * (1024 * 1024)])
    assert_plain(big, 400, "larger")
    assert snapshot(api) == before  # no row, no file


def test_ten_photos_are_allowed_on_a_reinspection(api):
    first, _, _ = done_inspection(api)
    assert reinspect(api, first, [png_bytes(), jpeg_bytes()] * 5).status_code == 202


@pytest.mark.parametrize("state", ["queued", "running", "failed"])
def test_only_a_completed_inspection_can_be_reinspected(api, monkeypatch, state):
    from backend.app.services import inspections as service

    inspection_id, _ = setup_inspection(api)
    if state == "running":
        monkeypatch.setattr(service, "run_inspection_job", lambda *a, **k: None)
        api.post(f"/api/inspections/{inspection_id}/run")
    elif state == "failed":
        monkeypatch.setattr(service, "compare", lambda *a, **k: (_ for _ in ()).throw(ValueError("nope")))
        run(api, inspection_id)
        monkeypatch.undo()
    before = snapshot(api)
    r = reinspect(api, inspection_id)
    assert_plain(r, 409, f"this one is {state}")
    assert snapshot(api) == before


def test_second_request_while_one_reinspection_is_open_gets_409_and_leaves_no_files(api):
    first, _, _ = done_inspection(api)
    opened = reinspect(api, first)
    assert opened.status_code == 202
    before = snapshot(api)
    again = reinspect(api, first)
    assert assert_plain(again, 409, opened.json()["inspection_id"])
    assert snapshot(api) == before
    run(api, opened.json()["inspection_id"])  # once that one is finished, another may start
    assert reinspect(api, first).status_code == 202


def test_concurrent_reinspection_requests_create_exactly_one_inspection(api):
    first, _, _ = done_inspection(api)
    before_rows, before_files = snapshot(api)
    barrier = threading.Barrier(6)
    statuses = []

    def start():
        barrier.wait()
        statuses.append(reinspect(api, first).status_code)

    threads = [threading.Thread(target=start) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(statuses) == [202, 409, 409, 409, 409, 409], statuses
    rows, files = snapshot(api)
    assert len(rows["inspections"]) == len(before_rows["inspections"]) + 1
    assert len(rows["images"]) == len(before_rows["images"]) + 1
    assert len(files) == len(before_files) + 1  # the five rejected requests left no photo behind


def test_failure_while_saving_a_reinspection_photo_leaves_nothing(api, monkeypatch):
    import backend.app.api.inspections as routes
    from fastapi.testclient import TestClient

    from backend.app.main import app

    first, _, _ = done_inspection(api)
    before = snapshot(api)
    real, calls = routes.save_upload, []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(*args, **kwargs)

    monkeypatch.setattr(routes, "save_upload", flaky)
    r = TestClient(app, raise_server_exceptions=False).post(
        f"/api/inspections/{first}/reinspection",
        files=[("photos", ("a.png", png_bytes(), "image/png")), ("photos", ("b.png", png_bytes(), "image/png"))])
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error."}
    assert snapshot(api) == before
    monkeypatch.undo()
    assert reinspect(api, first).status_code == 202  # the slot was released by the rollback


# ---------- 13 quality passport ----------
def passport(api, cabinet="CAB-001"):
    return api.get(f"/api/cabinets/{cabinet}/quality-passport")


def test_passport_of_a_cabinet_without_inspections_is_empty_not_an_error(api):
    make_cabinet(api)
    r = passport(api)
    assert r.status_code == 200 and r.json() == {"cabinet_id": "CAB-001", "name": "Line 3 panel", "inspections": []}


def test_passport_for_an_unknown_cabinet_is_404(api):
    assert_plain(passport(api, "NOPE"), 404, "Cabinet not found")


def test_passport_lists_inspections_oldest_first_with_the_fields_the_frontend_reads(api):
    first, _, _ = done_inspection(api)
    second = reinspect(api, first).json()["inspection_id"]
    run(api, second)
    third = reinspect(api, second).json()["inspection_id"]
    body = passport(api).json()
    assert [i["inspection_id"] for i in body["inspections"]] == [first, second, third]
    for entry in body["inspections"]:  # frontend/src/pages/CabinetHistory.jsx reads these three
        assert {"inspection_id", "overall_status", "created_at"} <= set(entry)
    stamps = [i["created_at"] for i in body["inspections"]]
    assert stamps == sorted(stamps) and all(s.endswith("Z") for s in stamps)
    assert [i["previous_inspection_id"] for i in body["inspections"]] == [None, first, second]
    assert [i["state"] for i in body["inspections"]] == ["done", "done", "queued"]


def test_passport_entry_has_exactly_the_documented_fields(api):
    done_inspection(api)
    entry = passport(api).json()["inspections"][0]
    assert set(entry) == {"inspection_id", "state", "error", "created_at", "design_revision_id",
                          "design_revision_internal_id", "previous_inspection_id", "overall_status",
                          "engine_overall_status", "images", "findings", "review_events"}
    assert entry["design_revision_id"] == "REV-A" and entry["design_revision_internal_id"].startswith("DREV-")
    assert set(entry["images"][0]) == {"image_id", "sha256", "width", "height", "quality_flags"}
    assert re.fullmatch(r"[0-9a-f]{64}", entry["images"][0]["sha256"])
    assert set(entry["findings"][0]) == {"finding_id", "type", "tag", "original_status", "current_status", "reason"}


def test_passport_agrees_with_the_inspection_endpoint_and_keeps_original_statuses(api):
    first, _, detail = done_inspection(api)
    unread = next(f for f in detail["findings"] if f["tag"] == "PS11")["finding_id"]
    review(api, unread, "rejected_by_reviewer")
    review(api, unread, "confirmed_by_reviewer", reviewer="Bo")
    entry = passport(api).json()["inspections"][0]
    live = api.get(f"/api/inspections/{first}").json()
    assert entry["overall_status"] == live["overall_status"] == "mismatch_detected"
    assert entry["engine_overall_status"] == "review_required"  # what the engine stored stays visible
    ps = next(f for f in entry["findings"] if f["tag"] == "PS11")
    assert (ps["original_status"], ps["current_status"]) == ("inconclusive", "confirmed_by_reviewer")
    assert {f["finding_id"]: f["current_status"] for f in entry["findings"]} == {
        f["finding_id"]: f["status"] for f in live["findings"]}


def test_passport_returns_every_review_event_in_order(api):
    first, _, detail = done_inspection(api)
    ids = {f["tag"]: f["finding_id"] for f in detail["findings"]}
    review(api, ids["PS11"], "rejected_by_reviewer", reviewer="A")
    review(api, ids["CB11"], "confirmed_by_reviewer", reviewer="B")
    review(api, ids["PS11"], "confirmed_by_reviewer", reviewer="C")
    events = passport(api).json()["inspections"][0]["review_events"]
    assert [(e["finding_id"], e["decision"], e["reviewer"]) for e in events] == [
        (ids["PS11"], "rejected_by_reviewer", "A"), (ids["CB11"], "confirmed_by_reviewer", "B"),
        (ids["PS11"], "confirmed_by_reviewer", "C")]
    assert set(events[0]) == {"finding_id", "decision", "reviewer", "note", "created_at"}


def test_passport_shows_incomplete_and_failed_inspections_without_inventing_results(api, monkeypatch):
    from backend.app.services import inspections as service

    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    queued = make_inspection(api, "CAB-001", rid).json()["inspection_id"]
    failing = make_inspection(api, "CAB-001", rid).json()["inspection_id"]
    monkeypatch.setattr(service, "compare", lambda *a, **k: (_ for _ in ()).throw(ValueError("no engine")))
    run(api, failing)
    entries = {e["inspection_id"]: e for e in passport(api).json()["inspections"]}
    assert (entries[queued]["state"], entries[queued]["overall_status"], entries[queued]["findings"]) == ("queued", None, [])
    assert entries[failing]["state"] == "failed" and entries[failing]["error"] == "no engine"
    assert entries[failing]["overall_status"] is None and entries[failing]["engine_overall_status"] is None
    assert entries[failing]["findings"] == [] and entries[failing]["review_events"] == []


def test_passport_never_says_compliant_or_approved(api):
    inspection_id, _ = setup_inspection(api, tags=("CB11",))
    post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("O", "CB11")])
    run(api, inspection_id)
    text = passport(api).text.lower()
    for word in ("compliant", "approved", "certified", "safe"):
        assert word not in text
    assert passport(api).json()["inspections"][0]["overall_status"] == "pass"  # the contract's own term


def test_passport_only_lists_the_requested_cabinet_and_does_not_change_anything(api):
    first, _, _ = done_inspection(api)
    make_cabinet(api, "CAB-002", "Other")
    other_rev = make_revision(api, "CAB-002").json()["design_revision_id"]
    other = make_inspection(api, "CAB-002", other_rev).json()["inspection_id"]
    before = snapshot(api)
    assert [i["inspection_id"] for i in passport(api).json()["inspections"]] == [first]
    assert [i["inspection_id"] for i in passport(api, "CAB-002").json()["inspections"]] == [other]
    assert snapshot(api) == before


def test_cabinet_list_latest_inspection_follows_reinspections(api):
    first, _, _ = done_inspection(api)
    second = reinspect(api, first).json()["inspection_id"]
    row = api.get("/api/cabinets").json()[0]
    assert (row["latest_inspection_id"], row["latest_inspection_state"]) == (second, "queued")
