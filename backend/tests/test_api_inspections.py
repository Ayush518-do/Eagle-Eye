"""Endpoints 6-11 and the end-to-end flow."""
import hashlib

import pytest
from sqlalchemy import text

from backend.app.db import make_engine

from .helpers import (
    PDF, jpeg_bytes, make_cabinet, make_inspection, make_revision, manual_box, png_bytes,
    post_observations, setup_inspection,
)


def image_of(api, inspection_id):
    return api.get(f"/api/inspections/{inspection_id}").json()["images"][0]


def run(api, inspection_id):
    r = api.post(f"/api/inspections/{inspection_id}/run")
    assert r.status_code == 202, r.text
    return api.get(f"/api/inspections/{inspection_id}").json()  # background task has finished by now


def uploaded_files(api):
    d = api.settings.upload_dir
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


# ---------- 6 create inspection ----------
def test_create_inspection_returns_202_queued_and_stores_images_with_sizes(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    r = make_inspection(api, "CAB-001", rid, [png_bytes(40, 30), jpeg_bytes()])
    assert r.status_code == 202
    assert r.json()["state"] == "queued" and r.json()["inspection_id"].startswith("INS-")
    detail = api.get(f"/api/inspections/{r.json()['inspection_id']}").json()
    assert [(i["width"], i["height"]) for i in detail["images"]] == [(40, 30), (64, 48)]
    assert detail["images"][0]["url"] == f"/api/images/{detail['images'][0]['image_id']}"
    assert detail["state"] == "queued" and detail["overall_status"] is None and detail["findings"] == []
    assert len(uploaded_files(api)) == 3  # drawing + 2 photos


@pytest.mark.parametrize("count", [0, 11])
def test_photo_count_outside_1_to_10_is_400(api, count):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    before = uploaded_files(api)
    r = make_inspection(api, "CAB-001", rid, [png_bytes()] * count) if count else api.post(
        "/api/cabinets/CAB-001/inspections", data={"design_revision_id": rid})
    assert r.status_code == 400 and "between 1 and 10" in r.json()["detail"]
    assert uploaded_files(api) == before


def test_ten_photos_are_accepted(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    assert make_inspection(api, "CAB-001", rid, [png_bytes()] * 10).status_code == 202


def test_bad_photo_is_rejected_and_nothing_is_saved(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    before = uploaded_files(api)
    for bad, text_in_message in [(PDF, "JPEG and PNG"), (b"MZ\x90\x00" + b"\x00" * 30, "Unsupported"),
                                 (b"", "empty"), (b"\x89PNG\r\n\x1a\n" + b"\x00" * 30, "damaged"),
                                 (b"\xff\xd8\xff\xe0" + b"\x00" * 30, "damaged")]:
        r = make_inspection(api, "CAB-001", rid, [png_bytes(), bad])  # the good photo comes first
        assert r.status_code == 400, r.text
        assert "Photo 2" in r.json()["detail"] and text_in_message in r.json()["detail"]
    assert uploaded_files(api) == before
    assert api.get("/api/cabinets").json()[0]["latest_inspection_id"] is None


def test_inspection_needs_an_existing_cabinet_and_a_revision_of_that_cabinet(api):
    make_cabinet(api, "CAB-001")
    make_cabinet(api, "CAB-002")
    rid = make_revision(api, "CAB-001").json()["design_revision_id"]
    assert make_inspection(api, "NOPE", rid).status_code == 404
    assert make_inspection(api, "CAB-001", "DREV-NOPE").status_code == 404
    other = make_inspection(api, "CAB-002", rid)  # revision belongs to CAB-001
    assert other.status_code == 404 and "Design revision" in other.json()["detail"]


def test_oversize_photo_is_rejected(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    r = make_inspection(api, "CAB-001", rid, [png_bytes() + b"\x00" * (1024 * 1024)])  # limit is 1 MB
    assert r.status_code == 400 and "larger" in r.json()["detail"]


# ---------- 10 images ----------
def test_image_is_served_with_its_type_and_unknown_ids_404(api):
    inspection_id, _ = setup_inspection(api, photos=[png_bytes(), jpeg_bytes()])
    images = api.get(f"/api/inspections/{inspection_id}").json()["images"]
    first = api.get(images[0]["url"])
    assert first.status_code == 200 and first.headers["content-type"] == "image/png"
    assert first.content == png_bytes() and first.headers["x-content-type-options"] == "nosniff"
    assert api.get(images[1]["url"]).headers["content-type"] == "image/jpeg"
    assert api.get("/api/images/IMG-NOPE").status_code == 404


def test_image_whose_file_is_gone_is_404_not_a_crash(api):
    inspection_id, _ = setup_inspection(api)
    image = image_of(api, inspection_id)
    for f in api.settings.upload_dir.glob("*.png"):
        f.unlink()
    assert api.get(image["url"]).status_code == 404


# ---------- 7 observations ----------
def test_manual_observations_are_stored_and_read_back_in_contract_b_shape(api):
    inspection_id, _ = setup_inspection(api)
    image = image_of(api, inspection_id)
    r = post_observations(api, inspection_id, image, [manual_box("OBS-001", "CB11"), manual_box("OBS-002", "PS11")],
                          image_sha256=hashlib.sha256(png_bytes()).hexdigest())
    assert r.status_code == 201, r.text
    assert [o["observation_id"] for o in r.json()["observations"]] == ["OBS-001", "OBS-002"]
    block = api.get(f"/api/inspections/{inspection_id}/observations").json()
    assert block[0]["image_id"] == image["image_id"] and block[0]["image_size"] == [40, 30]
    assert block[0]["observations"][0]["text"] == "CB11" and block[0]["observations"][0]["source"] == "manual"
    engine = make_engine(api.settings.database_url)
    with engine.connect() as c:  # the client's id is kept apart from the server key
        row = c.execute(text("select id, observation_id from observations order by rowid")).first()
    engine.dispose()
    assert row[0].startswith("OBS-") and row[0] != "OBS-001" and row[1] == "OBS-001"


def test_observation_errors(api):
    inspection_id, _ = setup_inspection(api)
    image = image_of(api, inspection_id)
    ok = [manual_box("OBS-001", "CB11")]
    assert post_observations(api, inspection_id, image, ok).status_code == 201
    dup_stored = post_observations(api, inspection_id, image, [manual_box("OBS-001", "X"), manual_box("OBS-9", "Y")])
    assert dup_stored.status_code == 409 and "OBS-001" in dup_stored.json()["detail"]
    dup_inside = post_observations(api, inspection_id, image, [manual_box("A", "X"), manual_box("A", "Y")])
    assert dup_inside.status_code == 400 and "A" in dup_inside.json()["detail"]
    detector = {**manual_box("D1", "X"), "source": "detector"}
    assert post_observations(api, inspection_id, image, [detector]).status_code == 400
    assert post_observations(api, inspection_id, image, [manual_box("  ", "X")]).status_code == 400
    assert post_observations(api, inspection_id, image, ok, contract_version="2").status_code == 400
    assert post_observations(api, inspection_id, image, [manual_box("N1", "X")],
                             image_sha256="00" * 32).status_code == 409
    wrong_size = api.post(f"/api/inspections/{inspection_id}/observations",
                          json={"image_id": image["image_id"], "image_size": [1, 1], "observations": []})
    assert wrong_size.status_code == 409
    other_image = {**image, "image_id": "IMG-NOPE"}
    assert post_observations(api, inspection_id, other_image, ok).status_code == 404
    assert post_observations(api, "INS-NOPE", image, ok).status_code == 404
    bad_box = api.post(f"/api/inspections/{inspection_id}/observations", json={
        "image_id": image["image_id"], "image_size": [40, 30], "observations": [manual_box("B1", "X", bbox=(5, 5, 1, 1))]})
    assert bad_box.status_code == 422
    stored = api.get(f"/api/inspections/{inspection_id}/observations").json()[0]["observations"]
    assert [o["observation_id"] for o in stored] == ["OBS-001"]  # every rejected request stored nothing


# ---------- 8, 9 run and detail: end to end ----------
def test_end_to_end_manual_boxes_run_and_verified_findings(api):
    inspection_id, _ = setup_inspection(api, tags=("CB11", "PS11"))
    image = image_of(api, inspection_id)
    post_observations(api, inspection_id, image, [manual_box("OBS-001", "CB11"), manual_box("OBS-002", "ps11")])
    started = api.post(f"/api/inspections/{inspection_id}/run")
    assert started.status_code == 202 and started.json() == {"inspection_id": inspection_id, "state": "running"}
    detail = api.get(f"/api/inspections/{inspection_id}").json()
    assert detail["state"] == "done" and detail["error"] is None
    assert {f["tag"]: f["status"] for f in detail["findings"]} == {"CB11": "verified", "PS11": "verified"}
    assert all(f["finding_id"].startswith("F-") for f in detail["findings"])
    assert detail["findings"][0]["evidence"] == [{"image_id": image["image_id"], "bbox": [1.0, 2.0, 30.0, 20.0]}]
    assert detail["counts"] == {"verified": 2} and detail["overall_status"] == "pass"
    assert detail["design_revision_id"] == "REV-A" and detail["design_revision_internal_id"].startswith("DREV-")
    assert api.get("/api/cabinets").json()[0]["latest_overall_status"] == "pass"


def test_unread_tag_is_inconclusive_never_missing_status_and_needs_review(api):
    inspection_id, _ = setup_inspection(api, tags=("CB11", "PS11"))
    image = image_of(api, inspection_id)
    post_observations(api, inspection_id, image, [manual_box("O1", "CB11"), manual_box("O2", "ZZ9")])
    detail = run(api, inspection_id)
    by_tag = {f["tag"]: f for f in detail["findings"]}
    assert by_tag["PS11"]["status"] == "inconclusive" and by_tag["ZZ9"]["type"] == "unexpected"
    assert detail["overall_status"] == "review_required"


def test_run_reads_observations_from_the_database_when_it_runs(api):
    """Observations added after the inspection exists but before the run must be seen."""
    inspection_id, _ = setup_inspection(api, tags=("CB11",))
    assert run(api, inspection_id)["state"] == "done"  # run once with nothing seen -> inconclusive
    inspection_id2, _ = (lambda r: (r.json()["inspection_id"], None))(make_inspection(
        api, "CAB-001", api.get("/api/cabinets/CAB-001").json()["design_revisions"][0]["design_revision_id"]))
    post_observations(api, inspection_id2, image_of(api, inspection_id2), [manual_box("O1", "CB11")])
    assert run(api, inspection_id2)["findings"][0]["status"] == "verified"


def test_run_states_and_conflicts(api):
    inspection_id, _ = setup_inspection(api)
    assert api.get(f"/api/inspections/{inspection_id}").json()["state"] == "queued"
    assert run(api, inspection_id)["state"] == "done"
    again = api.post(f"/api/inspections/{inspection_id}/run")
    assert again.status_code == 409 and "done" in again.json()["detail"]
    late = post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("L1", "X")])
    assert late.status_code == 409
    assert api.post("/api/inspections/INS-NOPE/run").status_code == 404
    assert api.get("/api/inspections/INS-NOPE").status_code == 404
    assert len(api.get(f"/api/inspections/{inspection_id}").json()["findings"]) == 2  # no duplicate findings


def test_failed_run_records_failed_with_a_plain_error_and_writes_no_findings(api, monkeypatch):
    from backend.app.services import inspections as service

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail /home/x/db.sqlite")

    monkeypatch.setattr(service, "compare", boom)
    inspection_id, _ = setup_inspection(api)
    detail = run(api, inspection_id)
    assert detail["state"] == "failed" and detail["overall_status"] is None and detail["findings"] == []
    assert "RuntimeError" in detail["error"] and "secret" not in detail["error"]
    monkeypatch.undo()
    retry = run(api, inspection_id)  # a failed run may be started again
    assert retry["state"] == "done" and retry["error"] is None and len(retry["findings"]) == 2


def test_synthetic_observations_make_the_run_fail_loudly(api):
    from sqlalchemy import update
    from backend.app.models import Observation

    inspection_id, _ = setup_inspection(api)
    post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("O1", "CB11")])
    engine = make_engine(api.settings.database_url)
    with engine.begin() as c:
        c.execute(update(Observation.__table__).values(source="synthetic"))
    engine.dispose()
    detail = run(api, inspection_id)
    assert detail["state"] == "failed" and "Synthetic" in detail["error"] and detail["findings"] == []


# ---------- 11 review ----------
def reviewed_setup(api):
    inspection_id, _ = setup_inspection(api, tags=("CB11", "PS11"))
    post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("O1", "CB11")])
    detail = run(api, inspection_id)
    return inspection_id, {f["tag"]: f for f in detail["findings"]}


def review(api, finding_id, decision, reviewer="Archita", note="n"):
    return api.post(f"/api/findings/{finding_id}/review",
                    json={"decision": decision, "reviewer": reviewer, "note": note})


def test_review_twice_keeps_both_events_and_shows_the_latest(api):
    inspection_id, f = reviewed_setup(api)
    ps = f["PS11"]["finding_id"]
    first = review(api, ps, "rejected_by_reviewer", note="looked again")
    assert first.status_code == 201 and first.json()["finding_id"] == ps and first.json()["note"] == "looked again"
    second = review(api, ps, "confirmed_by_reviewer", reviewer="  Bo ", note="label missing")
    assert second.status_code == 201 and second.json()["reviewer"] == "Bo"
    detail = api.get(f"/api/inspections/{inspection_id}").json()
    assert {x["tag"]: x["status"] for x in detail["findings"]}["PS11"] == "confirmed_by_reviewer"
    engine = make_engine(api.settings.database_url)
    with engine.connect() as c:
        events = c.execute(text("select decision, reviewer from review_events order by id")).all()
        original = c.execute(text("select status from findings where id=:i"), {"i": ps}).scalar()
    engine.dispose()
    assert [tuple(e) for e in events] == [("rejected_by_reviewer", "Archita"), ("confirmed_by_reviewer", "Bo")]
    assert original == "inconclusive"  # the engine's original finding is never overwritten


def test_a_confirmed_discrepancy_is_never_a_pass(api):
    inspection_id, f = reviewed_setup(api)
    review(api, f["PS11"]["finding_id"], "confirmed_by_reviewer")  # reviewer confirms the part is missing
    detail = api.get(f"/api/inspections/{inspection_id}").json()
    assert detail["overall_status"] == "mismatch_detected"
    assert api.get("/api/cabinets").json()[0]["latest_overall_status"] == "mismatch_detected"


def test_rejecting_an_inconclusive_finding_does_not_make_the_inspection_pass(api):
    inspection_id, f = reviewed_setup(api)
    review(api, f["PS11"]["finding_id"], "rejected_by_reviewer")
    assert api.get(f"/api/inspections/{inspection_id}").json()["overall_status"] == "review_required"


def test_review_errors(api):
    _, f = reviewed_setup(api)
    fid = f["CB11"]["finding_id"]
    assert review(api, "F-NOPE", "confirmed_by_reviewer").status_code == 404
    assert review(api, fid, "resolved_after_reinspection").status_code == 422  # not a reviewer decision
    assert review(api, fid, "confirmed_by_reviewer", reviewer="   ").status_code == 400
    assert review(api, fid, "confirmed_by_reviewer", reviewer="").status_code == 422
    engine = make_engine(api.settings.database_url)
    with engine.connect() as c:
        assert c.execute(text("select count(*) from review_events")).scalar() == 0
    engine.dispose()


def test_no_endpoint_can_update_or_delete_review_events(api):
    paths = api.get("/openapi.json").json()["paths"]
    review_paths = {p: set(v) for p, v in paths.items() if "review" in p}
    assert review_paths == {"/api/findings/{finding_id}/review": {"post"}}
