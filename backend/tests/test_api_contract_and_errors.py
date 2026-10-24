"""Response shapes (docs/contracts.md, docs/team/backend.md, the frontend mock), the plain-message
error format, photo validation, state handling, and "a rejected request changes nothing"."""
import json
import re
import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.api.errors import register_error_handlers, validation_message
from backend.app.main import app
from backend.app.models import AppendOnlyError  # noqa: F401  (documents the ORM guard used elsewhere)
from backend.app.schemas import InspectionResult
from backend.app.services import inspections as service

from .helpers import (
    JPEG_SIZE, PDF, jpeg_bytes, make_cabinet, make_inspection, make_revision, manual_box, png_bytes,
    post_observations, setup_inspection,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLES = ("cabinets", "design_revisions", "expected_items", "inspections", "images", "observations",
          "findings", "review_events")


def snapshot(api):
    """Every row of every table, plus the stored upload files."""
    con = sqlite3.connect(api.settings.database_url.removeprefix("sqlite:///"))
    rows = {t: con.execute(f"select * from {t} order by rowid").fetchall() for t in TABLES}
    con.close()
    d = api.settings.upload_dir
    return rows, sorted(p.name for p in d.iterdir()) if d.exists() else []


def image_of(api, inspection_id):
    return api.get(f"/api/inspections/{inspection_id}").json()["images"][0]


def run(api, inspection_id):
    assert api.post(f"/api/inspections/{inspection_id}/run").status_code == 202
    return api.get(f"/api/inspections/{inspection_id}").json()


def assert_plain(response, status, contains=None):
    assert response.status_code == status, response.text
    body = response.json()
    assert list(body) == ["detail"] and isinstance(body["detail"], str) and body["detail"], body
    text = body["detail"]
    assert "Traceback" not in text and "File \"" not in text and "sqlite" not in text.lower()
    assert not re.search(r"[A-Za-z]:\\|/home/|/tmp/", text), text
    if contains:
        assert contains in text, text
    return text


# ---------- A. error bodies ----------
def test_malformed_json_gets_a_plain_message(api):
    r = api.post("/api/cabinets", content="{not json", headers={"content-type": "application/json"})
    assert assert_plain(r, 422, "not valid JSON")
    assert assert_plain(api.post("/api/cabinets"), 422, "request body is required")


def test_missing_fields_and_wrong_types_name_the_field(api):
    assert_plain(api.post("/api/cabinets", json={"name": "x"}), 422, "cabinet_id: Field required")
    assert_plain(api.post("/api/cabinets", json={"cabinet_id": 5, "name": ["x"]}), 422, "name:")
    assert_plain(api.post("/api/cabinets", json=["not", "an", "object"]), 422, "request body")
    assert_plain(api.post("/api/cabinets", json={"cabinet_id": "a/b", "name": "x"}), 422, "cabinet_id")
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    url = f"/api/design-revisions/{rid}/expected-items"
    assert_plain(api.post(url, json={"items": "nope"}), 422, "items")
    assert_plain(api.post(url, json={"items": [{"quantity": 1}]}), 422, "items.0.tag")
    assert_plain(api.post(url, json={"items": [{"tag": "A", "quantity": "many"}]}), 422, "quantity")
    assert_plain(api.post(url, json={}), 422, "items: Field required")


def test_validation_message_never_echoes_the_submitted_value(api):
    secret = "SuperSecretValue123"
    r = api.post("/api/cabinets", json={"cabinet_id": secret + "/", "name": secret})
    assert secret not in assert_plain(r, 422)


def test_invalid_multipart_requests(api):
    make_cabinet(api)
    assert_plain(api.post("/api/cabinets/CAB-001/design-revisions", json={"label": "REV-A"}), 422, "drawing")
    broken = api.post("/api/cabinets/CAB-001/design-revisions", content=b"--x\r\nbroken",
                      headers={"content-type": "multipart/form-data; boundary=x"})
    assert broken.status_code in (400, 422)
    assert_plain(broken, broken.status_code)
    rid = make_revision(api).json()["design_revision_id"]
    assert_plain(api.post("/api/cabinets/CAB-001/inspections", data={}), 422, "design_revision_id")
    assert_plain(api.post("/api/cabinets/CAB-001/inspections", data={"design_revision_id": rid}), 400, "between 1 and 10")


def test_not_found_conflict_and_application_errors_are_plain(api):
    assert_plain(api.get("/api/cabinets/NOPE"), 404, "Cabinet not found")
    assert_plain(api.get("/api/inspections/INS-NOPE"), 404, "Inspection not found")
    assert_plain(api.get("/api/images/IMG-NOPE"), 404)
    assert_plain(api.get("/api/design-revisions/DREV-NOPE/expected-items"), 404, "Design revision not found")
    assert_plain(api.post("/api/findings/F-NOPE/review", json={"decision": "confirmed_by_reviewer", "reviewer": "A"}),
                 404, "Finding not found")
    assert_plain(api.get("/api/no-such-route"), 404)
    assert_plain(api.delete("/api/cabinets"), 405)
    make_cabinet(api)
    assert_plain(make_cabinet(api), 409, "already exists")
    assert_plain(make_revision(api, data=png_bytes()), 400, "PDF")
    assert_plain(api.post("/api/uploads", files={"file": ("x.png", b"")}), 400)


def test_expected_item_service_errors_are_plain_strings(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    url = f"/api/design-revisions/{rid}/expected-items"
    assert_plain(api.post(url, json={"items": [{"tag": "A"}, {"tag": "a "}]}), 400, "Duplicate tags")
    assert_plain(api.post(url, json={"items": [{"tag": " "}]}), 400, "blank")
    assert_plain(api.post(url, json={"contract_version": "7", "items": []}), 400, "'0.2'")
    assert_plain(api.post(url, json={"drawing_file_sha256": "00" * 32, "items": []}), 409, "does not match")


def test_unexpected_exceptions_become_a_generic_500_without_internals():
    mini = FastAPI()
    register_error_handlers(mini)

    @mini.get("/boom")
    def boom():
        raise RuntimeError("secret /home/user/db.sqlite password=hunter2")

    r = TestClient(mini, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error."}


def test_validation_message_limits_the_number_of_problems():
    errors = [{"loc": ("body", f"f{i}"), "msg": "Field required", "type": "missing"} for i in range(9)]
    text = validation_message(errors)
    assert text.count("Field required") == 5 and "4 more" in text


# ---------- B. Contract C shape ----------
def done_inspection(api):
    inspection_id, _ = setup_inspection(api, tags=("CB11", "PS11"))
    post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("O1", "CB11")])
    return inspection_id, run(api, inspection_id)


def test_inspection_detail_matches_contract_c(api):
    inspection_id, detail = done_inspection(api)
    InspectionResult.model_validate(detail)  # the repository's own Contract C model accepts it
    bundle = json.loads((REPO_ROOT / "frontend/src/mocks/inspection.synthetic.json").read_text(encoding="utf-8"))
    mock = bundle["inspection"]  # frontend mock is a multi-endpoint bundle; Contract C is under "inspection"
    # Fields the mock adds for demo convenience (not part of Contract C).
    frontend_only = {"cabinet_name", "cabinet_serial", "arrangement"}
    contract_keys = {k for k in mock if not k.startswith("_")} - frontend_only
    assert contract_keys <= set(detail)
    assert set(detail) - contract_keys == {"state", "error", "design_revision_internal_id", "previous_inspection_id"}
    for key in mock["images"][0]:
        if key in {"url", "filename", "alignment_set", "ghost"}:
            continue  # mock-only presentation / alignment-dependent fields
        assert key in detail["images"][0], f"missing image key: {key}"
    # Frontend-only presentation fields on a finding (not part of Contract C).
    finding_frontend_only = {
        "expected_tag", "expected_rating", "observed_tag", "observed_rating",
        "observation", "sources", "evidence_score", "design_revision_id", "reviews", "expected_bbox",
    }
    for key in mock["findings"][0]:
        if key in finding_frontend_only:
            continue
        assert key in detail["findings"][0], f"missing finding key: {key}"
    assert set(mock["findings"][0]["evidence"][0]) <= set(detail["findings"][0]["evidence"][0])
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", detail["created_at"]), detail["created_at"]
    assert detail["inspection_id"] == inspection_id and detail["cabinet_id"] == "CAB-001"
    assert detail["design_revision_id"] == "REV-A"  # the label, as in the contract example
    assert detail["design_revision_internal_id"].startswith("DREV-")
    image = detail["images"][0]
    assert image["url"] == f"/api/images/{image['image_id']}" and (image["width"], image["height"]) == (40, 30)
    assert detail["counts"] == {"verified": 1, "inconclusive": 1}
    assert {f["tag"]: (f["type"], f["status"]) for f in detail["findings"]} == {
        "CB11": ("verified", "verified"), "PS11": ("missing", "inconclusive")}
    unread = next(f for f in detail["findings"] if f["tag"] == "PS11")
    assert unread["evidence"] == [] and unread["observed_text"] is None and "Not proof" in unread["reason"]


def test_state_and_overall_status_before_and_after_the_run(api):
    inspection_id, _ = setup_inspection(api)
    queued = api.get(f"/api/inspections/{inspection_id}").json()
    assert (queued["state"], queued["overall_status"], queued["error"], queued["findings"]) == ("queued", None, None, [])
    assert queued["counts"] == {}
    assert run(api, inspection_id)["overall_status"] == "review_required"


def test_response_models_have_exactly_the_documented_fields(api):
    created = make_cabinet(api)
    assert created.status_code == 201 and set(created.json()) == {"cabinet_id", "name", "created_at"}
    assert created.json()["created_at"].endswith("Z")
    assert set(api.get("/api/cabinets").json()[0]) == {
        "cabinet_id", "name", "created_at", "latest_inspection_id", "latest_inspection_state",
        "latest_overall_status"}
    revision = make_revision(api)
    assert revision.status_code == 201
    assert set(revision.json()) == {"design_revision_id", "cabinet_id", "label", "drawing_sha256",
                                    "parser_version", "created_at"}
    detail = api.get("/api/cabinets/CAB-001").json()
    assert set(detail) == {"cabinet_id", "name", "created_at", "design_revisions"}
    assert set(detail["design_revisions"][0]) == set(revision.json())
    rid = revision.json()["design_revision_id"]
    items = api.post(f"/api/design-revisions/{rid}/expected-items", json={"items": [{"tag": "CB11"}]})
    assert set(items.json()) == {"contract_version", "drawing_file_sha256", "parser_version", "items"}
    assert set(items.json()["items"][0]) == {"tag", "part_number", "description", "quantity", "rating", "source_page", "layout"}
    accepted = make_inspection(api, "CAB-001", rid)
    assert accepted.status_code == 202 and set(accepted.json()) == {"inspection_id", "state"}  # guide: exactly these
    iid = accepted.json()["inspection_id"]
    obs = post_observations(api, iid, image_of(api, iid), [manual_box("OBS-001", "CB11")])
    assert set(obs.json()) == {"contract_version", "image_id", "image_sha256", "image_size", "observations"}
    assert set(obs.json()["observations"][0]) == {
        "observation_id", "source", "kind", "class_name", "bbox", "confidence", "text", "raw_text",
        "text_confidence", "model"}
    started = api.post(f"/api/inspections/{iid}/run")
    assert started.status_code == 202 and set(started.json()) == {"inspection_id", "state"}
    finding = api.get(f"/api/inspections/{iid}").json()["findings"][0]["finding_id"]
    event = api.post(f"/api/findings/{finding}/review",
                     json={"decision": "confirmed_by_reviewer", "reviewer": "A", "note": ""})
    assert event.status_code == 201
    assert set(event.json()) == {"finding_id", "decision", "reviewer", "note", "created_at"}
    assert event.json()["note"] == "" and event.json()["finding_id"] == finding


# ---------- list cabinets: latest state and status ----------
def test_cabinet_list_reports_the_latest_inspection(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    api.post(f"/api/design-revisions/{rid}/expected-items", json={"items": [{"tag": "CB11"}]})
    first = make_inspection(api, "CAB-001", rid).json()["inspection_id"]
    post_observations(api, first, image_of(api, first), [manual_box("O1", "CB11")])
    run(api, first)
    row = api.get("/api/cabinets").json()[0]
    assert (row["latest_inspection_id"], row["latest_inspection_state"], row["latest_overall_status"]) == (
        first, "done", "pass")
    second = make_inspection(api, "CAB-001", rid).json()["inspection_id"]  # newer, not run yet
    row = api.get("/api/cabinets").json()[0]
    assert (row["latest_inspection_id"], row["latest_inspection_state"], row["latest_overall_status"]) == (
        second, "queued", None)


# ---------- images: validation and cleanup ----------
def corrupt(data: bytes) -> bytes:
    flipped = bytearray(data)
    flipped[len(data) // 2] ^= 0xFF
    return bytes(flipped)


@pytest.mark.parametrize("name, bad", [
    ("truncated png", png_bytes()[:-20]),
    ("png without IEND", png_bytes()[:-12]),
    ("png with a flipped byte", corrupt(png_bytes())),
    ("png with a wrong IEND checksum", png_bytes()[:-1] + bytes([png_bytes()[-1] ^ 1])),  # only the CRC sees this
    ("png with a wrong IHDR checksum", png_bytes()[:29] + bytes([png_bytes()[29] ^ 1]) + png_bytes()[30:]),
    ("signature only", b"\x89PNG\r\n\x1a\n"),
    ("truncated jpeg", jpeg_bytes()[:-2]),
    ("jpeg cut in half", jpeg_bytes()[: len(jpeg_bytes()) // 2]),
    ("jpeg magic only", b"\xff\xd8\xff\xe0" + b"\x00" * 30),
], ids=lambda v: v if isinstance(v, str) else "data")
def test_damaged_photos_are_rejected_and_leave_nothing_behind(api, name, bad):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    before = snapshot(api)
    r = make_inspection(api, "CAB-001", rid, [png_bytes(), bad])
    assert "Photo 2" in assert_plain(r, 400, "damaged or truncated")
    assert snapshot(api) == before


def test_valid_png_and_jpeg_report_their_real_dimensions(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    r = make_inspection(api, "CAB-001", rid, [png_bytes(123, 45), jpeg_bytes()])
    images = api.get(f"/api/inspections/{r.json()['inspection_id']}").json()["images"]
    assert [(i["width"], i["height"]) for i in images] == [(123, 45), JPEG_SIZE]


def test_unmeasured_quality_is_flagged_not_left_empty(api):
    inspection_id, _ = setup_inspection(api)
    assert image_of(api, inspection_id)["quality_flags"] == ["quality_not_measured"]


def test_a_failure_while_saving_the_second_photo_removes_the_first(api, monkeypatch):
    import backend.app.api.inspections as routes

    real = routes.save_upload
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("disk full: C:\\secret\\path")
        return real(*args, **kwargs)

    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    before = snapshot(api)
    monkeypatch.setattr(routes, "save_upload", flaky)
    r = TestClient(app, raise_server_exceptions=False).post(
        "/api/cabinets/CAB-001/inspections", data={"design_revision_id": rid},
        files=[("photos", ("a.png", png_bytes(), "image/png")), ("photos", ("b.png", png_bytes(), "image/png"))])
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error."}
    assert len(calls) == 2 and snapshot(api) == before


def test_a_failed_database_write_removes_the_uploaded_drawing(api, monkeypatch):
    make_cabinet(api)
    before = snapshot(api)

    def boom(self, *a, **k):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(Session, "commit", boom)
    r = TestClient(app, raise_server_exceptions=False).post(
        "/api/cabinets/CAB-001/design-revisions", data={"label": "REV-A"},
        files={"drawing": ("d.pdf", PDF, "application/pdf")})
    monkeypatch.undo()
    assert r.status_code == 500 and snapshot(api) == before


def test_each_image_url_serves_only_its_own_file(api):
    inspection_id, _ = setup_inspection(api, photos=[png_bytes(10, 10), png_bytes(20, 20), jpeg_bytes()])
    images = api.get(f"/api/inspections/{inspection_id}").json()["images"]
    served = [api.get(i["url"]).content for i in images]
    assert served == [png_bytes(10, 10), png_bytes(20, 20), jpeg_bytes()]
    assert api.get("/api/images/..%2f..%2fetc%2fpasswd").status_code == 404
    pdf_file = next(api.settings.upload_dir.glob("*.pdf")).stem
    assert api.get(f"/api/images/{pdf_file}").status_code == 404  # file ids are not image ids


# ---------- observations: boxes and concurrency ----------
@pytest.mark.parametrize("bbox", [(-1, 0, 10, 10), (0, 0, 41, 10), (0, 0, 10, 31), (30, 20, 50, 40)])
def test_boxes_outside_the_image_are_rejected(api, bbox):
    inspection_id, _ = setup_inspection(api)  # photo is 40 x 30
    before = snapshot(api)
    r = post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("O1", "CB11", bbox=bbox)])
    assert_plain(r, 400, "outside the image")
    assert snapshot(api) == before


def test_box_on_the_image_edge_is_accepted_and_degenerate_or_nan_boxes_are_not(api):
    inspection_id, _ = setup_inspection(api)
    image = image_of(api, inspection_id)
    assert post_observations(api, inspection_id, image, [manual_box("EDGE", "CB11", bbox=(0, 0, 40, 30))]).status_code == 201
    assert post_observations(api, inspection_id, image, [manual_box("Z", "X", bbox=(5, 5, 5, 9))]).status_code == 422
    nan_body = ('{"image_id": "%s", "image_size": [40, 30], "observations": [{"observation_id": "N", '
                '"source": "manual", "kind": "tag_label", "class_name": "t", "bbox": [NaN, 0, 10, 10]}]}'
                % image["image_id"])
    r = api.post(f"/api/inspections/{inspection_id}/observations", content=nan_body,
                 headers={"content-type": "application/json"})
    assert_plain(r, 400)
    assert [o["observation_id"] for o in api.get(f"/api/inspections/{inspection_id}/observations").json()[0]["observations"]] == ["EDGE"]


def test_concurrent_posts_of_the_same_observation_id_store_exactly_one(api):
    inspection_id, _ = setup_inspection(api)
    image = image_of(api, inspection_id)
    barrier = threading.Barrier(6)
    statuses = []

    def post():
        barrier.wait()
        statuses.append(post_observations(api, inspection_id, image, [manual_box("RACE", "CB11")]).status_code)

    threads = [threading.Thread(target=post) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(statuses) == [201, 409, 409, 409, 409, 409], statuses
    stored = api.get(f"/api/inspections/{inspection_id}/observations").json()[0]["observations"]
    assert [o["observation_id"] for o in stored] == ["RACE"]


# ---------- runs: states, failures, retries ----------
def test_running_state_is_persisted_and_blocks_further_changes(api, monkeypatch):
    monkeypatch.setattr(service, "run_inspection_job", lambda *a, **k: None)  # the job never finishes
    inspection_id, _ = setup_inspection(api)
    assert api.post(f"/api/inspections/{inspection_id}/run").json()["state"] == "running"
    assert api.get(f"/api/inspections/{inspection_id}").json()["state"] == "running"
    assert_plain(api.post(f"/api/inspections/{inspection_id}/run"), 409, "already running")
    late = post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("L", "X")])
    assert_plain(late, 409, "running")
    assert api.get("/api/cabinets").json()[0]["latest_inspection_state"] == "running"


def test_a_failure_after_findings_were_added_leaves_no_partial_findings(api, monkeypatch):
    def boom(findings):
        raise ValueError("engine blew up")

    monkeypatch.setattr(service, "engine_overall_status", boom)  # runs after the findings were added
    inspection_id, _ = setup_inspection(api, tags=("CB11", "PS11"))
    post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("O1", "CB11")])
    detail = run(api, inspection_id)
    assert (detail["state"], detail["error"], detail["findings"], detail["overall_status"]) == (
        "failed", "engine blew up", [], None)
    rows, _ = snapshot(api)
    assert rows["findings"] == []
    monkeypatch.undo()
    retried = run(api, inspection_id)  # retry: no duplicates, review history untouched
    assert retried["state"] == "done" and len(retried["findings"]) == 2 and retried["error"] is None
    assert len({f["finding_id"] for f in retried["findings"]}) == 2


def test_retry_after_failure_does_not_disturb_review_events_of_other_inspections(api, monkeypatch):
    inspection_id, detail = done_inspection(api)
    finding = detail["findings"][0]["finding_id"]
    api.post(f"/api/findings/{finding}/review", json={"decision": "confirmed_by_reviewer", "reviewer": "A"})
    before = snapshot(api)[0]["review_events"]
    other, _ = (lambda r: (r.json()["inspection_id"], None))(make_inspection(
        api, "CAB-001", api.get("/api/cabinets/CAB-001").json()["design_revisions"][0]["design_revision_id"]))
    monkeypatch.setattr(service, "compare", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert run(api, other)["state"] == "failed"
    monkeypatch.undo()
    assert run(api, other)["state"] == "done"
    assert snapshot(api)[0]["review_events"] == before


# ---------- review history ----------
def test_review_history_is_append_only_through_the_database_too(api):
    _, detail = done_inspection(api)
    finding = detail["findings"][0]["finding_id"]
    for decision in ("rejected_by_reviewer", "confirmed_by_reviewer"):
        assert api.post(f"/api/findings/{finding}/review", json={"decision": decision, "reviewer": "A"}).status_code == 201
    con = sqlite3.connect(api.settings.database_url.removeprefix("sqlite:///"))
    before = con.execute("select id, decision from review_events order by id").fetchall()
    for sql in ("UPDATE review_events SET decision='rejected_by_reviewer'", "DELETE FROM review_events",
                "UPDATE findings SET status='verified'", "DELETE FROM findings"):
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql)
    assert con.execute("select id, decision from review_events order by id").fetchall() == before
    assert [d for _, d in before] == ["rejected_by_reviewer", "confirmed_by_reviewer"]
    con.close()


def test_current_status_follows_the_newest_event_while_the_original_is_kept(api):
    inspection_id, detail = done_inspection(api)
    unread = next(f for f in detail["findings"] if f["tag"] == "PS11")["finding_id"]
    for decision in ("confirmed_by_reviewer", "rejected_by_reviewer"):
        api.post(f"/api/findings/{unread}/review", json={"decision": decision, "reviewer": "A"})
    now = api.get(f"/api/inspections/{inspection_id}").json()
    assert next(f for f in now["findings"] if f["finding_id"] == unread)["status"] == "rejected_by_reviewer"
    assert now["overall_status"] == "review_required"  # a rejected unread tag is not proof the part is fine
    con = sqlite3.connect(api.settings.database_url.removeprefix("sqlite:///"))
    assert con.execute("select status from findings where id=?", (unread,)).fetchone()[0] == "inconclusive"
    con.close()


# ---------- every rejected request leaves the database and the upload folder unchanged ----------
def test_rejected_requests_change_nothing(api):
    inspection_id, rid = setup_inspection(api, tags=("CB11",))
    image = image_of(api, inspection_id)
    post_observations(api, inspection_id, image, [manual_box("KEEP", "CB11")])
    done = run(api, inspection_id)
    finding = done["findings"][0]["finding_id"]
    queued = make_inspection(api, "CAB-001", rid).json()["inspection_id"]
    queued_image = image_of(api, queued)
    before = snapshot(api)
    nan_body = json.dumps({"image_id": queued_image["image_id"], "image_size": [40, 30], "observations": []})
    attempts = [
        make_cabinet(api),
        make_cabinet(api, cabinet_id="bad/id"),
        make_revision(api, "NOPE"),
        make_revision(api, label=" "),
        make_revision(api, data=png_bytes()),
        make_revision(api, data=b""),
        api.post(f"/api/design-revisions/{rid}/expected-items", json={"items": [{"tag": "A"}, {"tag": "a"}]}),
        api.post(f"/api/design-revisions/{rid}/expected-items", json={"items": [{"tag": " "}]}),
        api.post(f"/api/design-revisions/{rid}/expected-items", json={"contract_version": "9", "items": []}),
        api.post(f"/api/design-revisions/{rid}/expected-items", json={"parser_version": "p", "drawing_file_sha256": "0" * 64, "items": []}),
        api.post(f"/api/design-revisions/{rid}/expected-items", json={"parser_version": " ", "items": []}),
        api.post(f"/api/design-revisions/{rid}/expected-items", content="{bad", headers={"content-type": "application/json"}),
        make_inspection(api, "CAB-001", rid, []),
        make_inspection(api, "CAB-001", rid, [png_bytes()] * 11),
        make_inspection(api, "CAB-001", rid, [png_bytes(), PDF]),
        make_inspection(api, "CAB-001", rid, [png_bytes(), png_bytes()[:-5]]),
        make_inspection(api, "CAB-001", "DREV-NOPE"),
        make_inspection(api, "NOPE", rid),
        post_observations(api, queued, queued_image, [manual_box("A", "x"), manual_box("A", "y")]),
        post_observations(api, queued, queued_image, [manual_box("A", "x", bbox=(0, 0, 99, 99))]),
        post_observations(api, queued, queued_image, [{**manual_box("A", "x"), "source": "detector"}]),
        post_observations(api, queued, queued_image, [manual_box("A", "x")], image_sha256="0" * 64),
        post_observations(api, queued, queued_image, [manual_box("A", "x")], contract_version="2"),
        post_observations(api, queued, image, [manual_box("A", "x")]),  # image of another inspection
        post_observations(api, inspection_id, image, [manual_box("LATE", "x")]),  # inspection already done
        api.post(f"/api/inspections/{queued}/observations", content=nan_body[:-3],
                 headers={"content-type": "application/json"}),
        api.post(f"/api/inspections/{inspection_id}/run"),  # already done
        api.post("/api/inspections/INS-NOPE/run"),
        api.post(f"/api/findings/{finding}/review", json={"decision": "resolved_after_reinspection", "reviewer": "A"}),
        api.post(f"/api/findings/{finding}/review", json={"decision": "confirmed_by_reviewer", "reviewer": " "}),
        api.post("/api/findings/F-NOPE/review", json={"decision": "confirmed_by_reviewer", "reviewer": "A"}),
    ]
    statuses = [a.status_code for a in attempts]
    assert all(s in (400, 404, 405, 409, 422) for s in statuses), statuses
    for a in attempts:
        assert isinstance(a.json()["detail"], str)
    assert snapshot(api) == before
