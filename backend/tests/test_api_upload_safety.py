"""Drawing PDF validation, hostile file names, and concurrent runs."""
import re
import threading

import pytest

from .helpers import PDF, make_cabinet, make_revision, manual_box, pdf_bytes, png_bytes, post_observations, \
    setup_inspection
from .test_api_contract_and_errors import assert_plain, image_of, snapshot


def broken_offset(data: bytes, offset: int) -> bytes:
    return re.sub(rb"startxref\n\d+\n", b"startxref\n%d\n" % offset, data)


@pytest.mark.parametrize("name, bad", [
    ("header only", b"%PDF-1.7\n" + b"\x00" * 32),
    ("cut before the trailer", PDF[:-30]),
    ("cut in half", PDF[: len(PDF) // 2]),
    ("no EOF marker", PDF.replace(b"%%EOF\n", b"")),
    ("startxref points past the end", broken_offset(PDF, 999_999)),
    ("startxref points at nothing useful", broken_offset(PDF, 12)),
    ("startxref is zero", broken_offset(PDF, 0)),
    ("junk before the header", b"JUNK" + PDF),
    ("far too much after the end", PDF + b"x" * 3000),
    ("a little junk after the end", PDF + b"junk"),
    ("cut inside a later update", PDF + b"1 0 obj\n<< /Type /Catalog"),
], ids=lambda v: v if isinstance(v, str) else "data")
def test_damaged_or_incomplete_drawing_is_rejected_and_nothing_is_saved(api, name, bad):
    make_cabinet(api)
    before = snapshot(api)
    assert_plain(make_revision(api, data=bad), 400)
    assert snapshot(api) == before


def test_complete_pdf_is_accepted_and_tolerates_trailing_whitespace(api):
    make_cabinet(api)
    assert make_revision(api, data=pdf_bytes()).status_code == 201
    assert make_revision(api, label="REV-B", data=pdf_bytes() + b"\r\n\r\n").status_code == 201


def test_a_png_or_jpeg_named_like_a_pdf_is_still_rejected(api):
    make_cabinet(api)
    assert_plain(make_revision(api, data=png_bytes()), 400, "PDF")


# ---------- hostile file names ----------
@pytest.mark.parametrize("hostile", ["../../evil", "..\\..\\evil", "/etc/passwd", "C:\\Windows\\evil", "a/b/../c"])
def test_client_file_names_never_choose_where_files_go(api, tmp_path, hostile):
    make_cabinet(api)
    r = api.post("/api/cabinets/CAB-001/design-revisions", data={"label": "REV-A"},
                 files={"drawing": (hostile + ".pdf", PDF, "application/pdf")})
    assert r.status_code == 201
    rid = r.json()["design_revision_id"]
    photo = api.post("/api/cabinets/CAB-001/inspections", data={"design_revision_id": rid},
                     files=[("photos", (hostile + ".png", png_bytes(), "image/png"))])
    assert photo.status_code == 202
    names = sorted(p.name for p in api.settings.upload_dir.iterdir())
    assert len(names) == 2 and all(re.fullmatch(r"[0-9a-f]{32}\.(pdf|png)", n) for n in names), names
    assert not list(tmp_path.parent.glob("evil*")) and not (tmp_path / "evil.pdf").exists()
    assert hostile not in r.text and "evil" not in photo.text


def test_error_messages_show_only_a_sanitised_file_name(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    r = api.post("/api/cabinets/CAB-001/inspections", data={"design_revision_id": rid},
                 files=[("photos", ("../../secret/dir/x.png", png_bytes()[:-9], "image/png"))])
    detail = assert_plain(r, 400, "damaged or truncated")
    assert "secret" not in detail and ".." not in detail and "x.png" in detail


# ---------- concurrent runs ----------
def test_concurrent_run_requests_start_exactly_one_run_and_one_set_of_findings(api):
    inspection_id, _ = setup_inspection(api, tags=("CB11", "PS11"))
    post_observations(api, inspection_id, image_of(api, inspection_id), [manual_box("O1", "CB11")])
    barrier = threading.Barrier(6)
    statuses = []

    def start():
        barrier.wait()
        statuses.append(api.post(f"/api/inspections/{inspection_id}/run").status_code)

    threads = [threading.Thread(target=start) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(statuses) == [202, 409, 409, 409, 409, 409], statuses
    detail = api.get(f"/api/inspections/{inspection_id}").json()
    assert detail["state"] == "done" and len(detail["findings"]) == 2
