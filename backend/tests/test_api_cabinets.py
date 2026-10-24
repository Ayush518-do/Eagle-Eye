"""Endpoints 1-5 (+ GET expected items)."""
import hashlib

from .helpers import PDF, make_cabinet, make_revision, png_bytes


# ---------- 1-3 cabinets ----------
def test_create_cabinet_returns_201_and_duplicate_gives_409(api):
    r = make_cabinet(api)
    assert r.status_code == 201
    assert r.json()["cabinet_id"] == "CAB-001" and r.json()["name"] == "Line 3 panel"
    dup = make_cabinet(api, name="other name")
    assert dup.status_code == 409 and dup.json() == {"detail": "Cabinet CAB-001 already exists."}
    assert api.get("/api/cabinets/CAB-001").json()["name"] == "Line 3 panel"  # untouched


def test_cabinet_id_must_be_url_safe(api):
    assert make_cabinet(api, cabinet_id="a/b").status_code == 422
    assert make_cabinet(api, cabinet_id="").status_code == 422
    assert make_cabinet(api, name="  ").status_code == 422
    assert make_cabinet(api, cabinet_id="  CAB-9  ").json()["cabinet_id"] == "CAB-9"  # trimmed


def test_list_cabinets_has_cabinet_id_keys_and_no_status_before_any_inspection(api):
    assert api.get("/api/cabinets").json() == []
    make_cabinet(api, "CAB-001")
    make_cabinet(api, "CAB-002", "Second")
    rows = api.get("/api/cabinets").json()
    assert [r["cabinet_id"] for r in rows] == ["CAB-001", "CAB-002"]
    assert rows[0]["latest_inspection_id"] is None and rows[0]["latest_overall_status"] is None


def test_cabinet_detail_lists_design_revisions_and_404s(api):
    make_cabinet(api)
    make_revision(api, label="REV-A")
    make_revision(api, label="REV-B")
    detail = api.get("/api/cabinets/CAB-001").json()
    assert [r["label"] for r in detail["design_revisions"]] == ["REV-A", "REV-B"]
    assert api.get("/api/cabinets/NOPE").status_code == 404


# ---------- 4 design revisions ----------
def test_design_revision_stores_the_pdf_and_its_hash(api):
    make_cabinet(api)
    r = make_revision(api)
    assert r.status_code == 201
    body = r.json()
    assert body["design_revision_id"].startswith("DREV-") and body["label"] == "REV-A"
    assert body["drawing_sha256"] == hashlib.sha256(PDF).hexdigest() and body["parser_version"] is None
    assert len(list(api.settings.upload_dir.iterdir())) == 1


def test_design_revision_rejects_missing_cabinet_non_pdf_blank_label_and_empty(api):
    assert make_revision(api, "NOPE").status_code == 404
    make_cabinet(api)
    png = make_revision(api, data=png_bytes())
    assert png.status_code == 400 and "PDF" in png.json()["detail"]
    assert make_revision(api, label="  ").status_code == 400
    assert make_revision(api, data=b"").status_code == 400
    assert make_revision(api, data=b"MZ\x90\x00" + b"\x00" * 20).status_code == 400
    assert not api.settings.upload_dir.exists() or list(api.settings.upload_dir.iterdir()) == []
    assert api.get("/api/cabinets/CAB-001").json()["design_revisions"] == []


# ---------- 5 expected items ----------
def revision_id(api):
    make_cabinet(api)
    return make_revision(api).json()["design_revision_id"]


def test_expected_items_replace_not_append_and_read_back_contract_a_shape(api):
    rid = revision_id(api)
    first = {"parser_version": "drawing-parser 0.1.0", "items": [
        {"tag": "CB11", "rating": {"value": "10 A", "source": "schematic", "page": 5, "needs_review": False},
         "source_page": 3}, {"tag": "PS11"}]}
    r = api.post(f"/api/design-revisions/{rid}/expected-items", json=first)
    assert r.status_code == 201
    assert r.json()["contract_version"] == "0.2" and r.json()["parser_version"] == "drawing-parser 0.1.0"
    assert r.json()["items"][0]["rating"]["page"] == 5 and r.json()["items"][1]["rating"] is None
    manual = api.post(f"/api/design-revisions/{rid}/expected-items", json={"items": [{"tag": " x1 "}]})
    assert manual.status_code == 201
    stored = api.get(f"/api/design-revisions/{rid}/expected-items").json()
    assert [i["tag"] for i in stored["items"]] == ["x1"]  # replaced, trimmed, case kept
    assert stored["parser_version"] == "drawing-parser 0.1.0"  # manual list keeps the old value


def test_expected_items_errors_use_the_detail_format_and_change_nothing(api):
    rid = revision_id(api)
    api.post(f"/api/design-revisions/{rid}/expected-items", json={"items": [{"tag": "CB11"}]})
    url = f"/api/design-revisions/{rid}/expected-items"
    cases = [
        ({"items": [{"tag": "A"}, {"tag": " a"}]}, 400, "Duplicate tags"),
        ({"items": [{"tag": "  "}]}, 400, "blank"),
        ({"contract_version": "9", "items": []}, 400, "Unsupported contract_version"),
        ({"parser_version": " ", "items": []}, 400, "parser_version"),
        ({"drawing_file_sha256": "00" * 32, "items": []}, 409, "does not match"),
    ]
    for body, status, text in cases:
        r = api.post(url, json=body)
        assert r.status_code == status and text in r.json()["detail"], (body, r.text)
    assert [i["tag"] for i in api.get(url).json()["items"]] == ["CB11"]
    assert api.post("/api/design-revisions/DREV-NOPE/expected-items", json={"items": []}).status_code == 404
    assert api.get("/api/design-revisions/DREV-NOPE/expected-items").status_code == 404


def test_matching_drawing_hash_is_accepted(api):
    rid = revision_id(api)
    sha = hashlib.sha256(PDF).hexdigest()
    r = api.post(f"/api/design-revisions/{rid}/expected-items", json={"drawing_file_sha256": sha, "items": []})
    assert r.status_code == 201 and r.json()["drawing_file_sha256"] == sha
