"""JPEG decoding with Pillow, PNG behaviour, decompression-bomb limits, and clean failure."""
import warnings

import pytest
from PIL import Image

from backend.app.services import images
from backend.app.services.images import MAX_PIXELS, image_size
from backend.app.services.storage import UploadRejected

from .helpers import (
    PDF, jpeg_bytes, jpeg_with_size, make_cabinet, make_inspection, make_revision, noisy_image, noisy_jpeg,
    png_bytes, png_with_header, pillow_bytes, scan_start, setup_inspection,
)
from .test_api_contract_and_errors import assert_plain, snapshot


def exif_bytes() -> bytes:
    exif = Image.Exif()
    exif[0x0112] = 1  # orientation
    return exif.tobytes()


def accepted(data, content_type="image/jpeg"):
    return image_size(data, content_type)


def rejected(data, content_type="image/jpeg"):
    with pytest.raises(UploadRejected) as e:
        image_size(data, content_type)
    return str(e.value)


# ---------- valid files ----------
@pytest.mark.parametrize("name, data, size", [
    ("static fixture", jpeg_bytes(), (64, 48)),
    ("baseline RGB", noisy_jpeg(), (96, 72)),
    ("progressive (several scans)", noisy_jpeg(progressive=True), (96, 72)),
    ("grayscale", noisy_jpeg(mode="L"), (96, 72)),
    ("CMYK", noisy_jpeg(mode="CMYK"), (96, 72)),
    ("odd size", noisy_jpeg(size=(37, 19)), (37, 19)),
    ("with restart markers", noisy_jpeg(restart_marker_blocks=2), (96, 72)),
    ("4:4:4 subsampling", noisy_jpeg(subsampling=0), (96, 72)),
    ("with EXIF block", noisy_jpeg(exif=exif_bytes()), (96, 72)),
    ("extra bytes after the end marker", noisy_jpeg() + b"\x00" * 10, (96, 72)),
    ("arithmetic-conditioning (DAC) segment", noisy_jpeg()[: scan_start(noisy_jpeg()) - 14] + b"\xff\xcc\x00\x04\x00\x00"
     + noisy_jpeg()[scan_start(noisy_jpeg()) - 14:], (96, 72)),
    ("Adobe APP14 and comment segments", noisy_jpeg()[:2] + b"\xff\xee\x00\x0e" + b"Adobe\x00\x64\x00\x00\x00\x00\x00"
     + b"\xff\xfe\x00\x07hello" + noisy_jpeg()[2:], (96, 72)),
    ("multi-frame (MPO) phone photo",
     pillow_bytes(noisy_image((64, 48)), format="MPO", save_all=True, append_images=[noisy_image((64, 48), seed=9)]),
     (64, 48)),
], ids=lambda v: v if isinstance(v, str) else "x")
def test_valid_jpegs_are_decoded_and_accepted(name, data, size):
    assert accepted(data) == size


def test_png_behaviour_is_unchanged(tmp_path):
    assert accepted(png_bytes(40, 30), "image/png") == (40, 30)
    for mode in ("RGB", "RGBA", "L", "LA", "P", "I;16"):
        data = pillow_bytes(noisy_image((33, 21), mode if mode not in ("P", "I;16") else "L").convert(mode), format="PNG")
        assert accepted(data, "image/png") == (33, 21), mode
    assert "damaged" in rejected(png_bytes()[:-20], "image/png")


# ---------- truncated and malformed JPEGs ----------
GOOD = noisy_jpeg()
SCAN = scan_start(GOOD)


@pytest.mark.parametrize("cut", [2, 3, 10, 20, SCAN - 1, SCAN, SCAN + 1, len(GOOD) // 2, len(GOOD) - 100,
                                 len(GOOD) - 3, len(GOOD) - 2, len(GOOD) - 1])
def test_truncated_jpegs_are_rejected(cut):
    assert "damaged or truncated" in rejected(GOOD[:cut])


def strip_segments(jpeg: bytes, marker: bytes) -> bytes:
    head, tail = jpeg[:SCAN], jpeg[SCAN:]
    while marker in head:
        i = head.index(marker)
        head = head[:i] + head[i + 2 + int.from_bytes(head[i + 2:i + 4], "big"):]
    return head + tail


def patch_frame(jpeg: bytes, offset: int, value: bytes) -> bytes:
    """Overwrite bytes of the frame header, `offset` bytes after the SOF marker's length field."""
    i = jpeg.index(b"\xff\xc0")
    at = i + 4 + offset
    return jpeg[:at] + value + jpeg[at + len(value):]


DECODER_ONLY = {
    "no quantization tables": strip_segments(GOOD, b"\xff\xdb"),
    "12-bit precision in a baseline frame": patch_frame(GOOD, 0, b"\x0c"),
    # components start 6 bytes into the frame header, 3 bytes each: copy the first id over the second
    "two components share an id": patch_frame(GOOD, 9, GOOD[GOOD.index(b"\xff\xc0") + 4 + 6:][:1]),
    "lossless frame type": GOOD.replace(b"\xff\xc0", b"\xff\xc3", 1),
}


@pytest.mark.parametrize("name", list(DECODER_ONLY))
def test_files_that_look_complete_to_the_marker_walk_but_cannot_be_decoded_are_rejected(name):
    """Proves the Pillow decode is doing real work: the structure alone accepts these."""
    data = DECODER_ONLY[name]
    assert images._check_jpeg(data) == (96, 72)  # every marker is where it should be
    assert "damaged or truncated" in rejected(data)  # the decoder cannot produce an image


def test_the_decoder_is_really_in_the_path(monkeypatch):
    data = DECODER_ONLY["no quantization tables"]
    monkeypatch.setattr(images, "_decode_jpeg", lambda *a, **k: None)
    assert accepted(data) == (96, 72)  # without the decode step the file would have been accepted


@pytest.mark.parametrize("name, data", [
    ("empty after magic", b"\xff\xd8"),
    ("magic and zeros", b"\xff\xd8\xff\xe0" + b"\x00" * 60),
    ("no frame header", GOOD.replace(b"\xff\xc0", b"\xff\xfe", 1)),
    ("no scan data at all", GOOD[:SCAN] + b"\xff\xd9"),
    ("invalid marker inside the scan data", GOOD[: SCAN + 40] + b"\xff\x12" + GOOD[SCAN + 40:]),
    ("a second SOI inside the scan data", GOOD[: SCAN + 40] + b"\xff\xd8" + GOOD[SCAN + 40:]),
    ("reserved marker before the frame", GOOD[:2] + b"\xff\x02\x00\x04ab" + GOOD[2:]),
    ("segment longer than the file", GOOD[:2] + b"\xff\xe1\xff\xff" + GOOD[2:40]),
    ("frame header with wrong length", GOOD.replace(b"\xff\xc0\x00\x11", b"\xff\xc0\x00\x0f", 1)),
    ("end marker before any scan", GOOD[:SCAN - 14] + b"\xff\xd9"),
    ("jpeg magic then a png", b"\xff\xd8\xff" + png_bytes()),
    ("png bytes", png_bytes()),
    ("pdf bytes", PDF),
    ("gif bytes", pillow_bytes(noisy_image((8, 8), "P"), format="GIF")),
    ("webp bytes", pillow_bytes(noisy_image((8, 8)), format="WEBP")),
], ids=lambda v: v if isinstance(v, str) else "x")
def test_malformed_jpegs_are_rejected(name, data):
    assert rejected(data)


@pytest.mark.parametrize("name, data", [
    ("invalid marker inside the scan data", GOOD[: SCAN + 40] + b"\xff\x12" + GOOD[SCAN + 40:]),
    ("a second SOI inside the scan data", GOOD[: SCAN + 40] + b"\xff\xd8" + GOOD[SCAN + 40:]),
    ("reserved marker before the frame", GOOD[:2] + b"\xff\x02\x00\x04ab" + GOOD[2:]),
    ("end marker before any scan", GOOD[:SCAN - 14] + b"\xff\xd9"),
    ("no frame header", GOOD.replace(b"\xff\xc0", b"\xff\xfe", 1)),
    ("no scan data at all", GOOD[:SCAN] + b"\xff\xd9"),
    ("never ends", GOOD[:-2]),
], ids=lambda v: v if isinstance(v, str) else "x")
def test_the_marker_walk_alone_refuses_structurally_broken_files(name, data):
    assert images._check_jpeg(data) is None  # independent of what the decoder would say


def test_the_marker_walk_accepts_multi_scan_and_restart_files():
    assert images._check_jpeg(noisy_jpeg(progressive=True)) == (96, 72)
    assert images._check_jpeg(noisy_jpeg(restart_marker_blocks=2)) == (96, 72)


# ---------- the decoded format and size must match ----------
def test_detected_and_decoded_formats_must_agree():
    assert "damaged" in rejected(png_bytes(), "image/jpeg")  # PNG bytes presented as a JPEG
    assert "damaged" in rejected(GOOD, "image/png")  # JPEG bytes presented as a PNG
    assert "Only JPEG and PNG" in rejected(GOOD, "image/gif")
    assert "Only JPEG and PNG" in rejected(PDF, "application/pdf")


def test_decoder_refuses_a_different_format_or_size_than_expected():
    with pytest.raises(UploadRejected):
        images._decode_jpeg(png_bytes(), (40, 30))  # decoded format is not JPEG
    with pytest.raises(UploadRejected):
        images._decode_jpeg(GOOD, (95, 72))  # decoded size differs from the one in the header walk
    images._decode_jpeg(GOOD, (96, 72))


# ---------- documented limit: libjpeg conceals damage inside a complete scan ----------
def test_known_limit_pixel_damage_inside_a_complete_scan_is_not_detectable():
    damaged = bytearray(GOOD)
    for i in range(SCAN + 20, SCAN + 80):  # overwrite pixel data with a constant (no 0xFF bytes)
        damaged[i] = 0x55
    assert accepted(bytes(damaged)) == (96, 72)  # decodes, to a distorted picture; see images.py
    # A file cut short and then given a fresh end marker is treated as a complete stream too.
    assert accepted(GOOD[: (SCAN + len(GOOD)) // 2] + b"\xff\xd9") == (96, 72)


# ---------- decompression bombs and memory ----------
@pytest.mark.parametrize("width, height", [(30000, 30000), (14000, 12000), (9460, 9460), (65535, 65535)])
def test_jpegs_claiming_too_many_pixels_are_refused_before_any_decoding(width, height):
    assert width * height > MAX_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no DecompressionBombWarning may escape
        assert "pixels" in rejected(jpeg_with_size(GOOD, width, height))


def test_pngs_claiming_too_much_are_refused_without_inflating():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert "million pixels" in rejected(png_with_header(60000, 60000), "image/png")  # too many pixels
        assert "too large" in rejected(png_with_header(7000, 6000, depth=16, color=6), "image/png")  # 336 MB
        assert "damaged" in rejected(png_with_header(2000, 2000), "image/png")  # claims 12 MB, supplies 16 bytes


def test_the_pixel_limit_is_pillows_default_threshold():
    assert MAX_PIXELS == Image.MAX_IMAGE_PIXELS == 1024 * 1024 * 1024 // 4 // 3


@pytest.mark.parametrize("error", [MemoryError, ValueError, SyntaxError, OSError, RecursionError, ZeroDivisionError])
def test_any_failure_inside_pillow_becomes_a_clean_rejection(monkeypatch, error):
    def boom(*args, **kwargs):
        raise error("hostile")

    monkeypatch.setattr(images.Image, "open", boom)
    assert "damaged or truncated" in rejected(GOOD)  # not an unhandled exception


# ---------- through the API ----------
def corrupt_cases():
    return {
        "no quantization tables (decoder only)": DECODER_ONLY["no quantization tables"],
        "invalid marker in the scan": GOOD[: SCAN + 40] + b"\xff\x12" + GOOD[SCAN + 40:],
        "truncated": GOOD[:-300],
        "bomb header": jpeg_with_size(GOOD, 30000, 30000),
        "valid-looking png header only": png_bytes()[:30],
    }


@pytest.mark.parametrize("name", list(corrupt_cases()))
def test_rejected_photos_leave_no_rows_and_no_files(api, name):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    before = snapshot(api)
    for photos in ([corrupt_cases()[name]], [GOOD, corrupt_cases()[name]], [png_bytes(), corrupt_cases()[name]]):
        files = [("photos", (f"p{i}.jpg", p, "image/jpeg")) for i, p in enumerate(photos)]
        r = api.post("/api/cabinets/CAB-001/inspections", data={"design_revision_id": rid}, files=files)
        detail = assert_plain(r, 400)
        assert f"Photo {len(photos)}" in detail
    assert snapshot(api) == before


def test_valid_jpegs_and_pngs_upload_with_their_decoded_sizes(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    r = make_inspection(api, "CAB-001", rid, [GOOD, noisy_jpeg(progressive=True, size=(50, 40)), png_bytes(10, 20)])
    assert r.status_code == 202
    images_ = api.get(f"/api/inspections/{r.json()['inspection_id']}").json()["images"]
    assert [(i["width"], i["height"]) for i in images_] == [(96, 72), (50, 40), (10, 20)]
    assert all(i["quality_flags"] == ["quality_not_measured"] for i in images_)


def test_a_corrupt_jpeg_is_refused_for_a_reinspection_too(api):
    inspection_id, _ = setup_inspection(api)
    assert api.post(f"/api/inspections/{inspection_id}/run").status_code == 202
    before = snapshot(api)
    r = api.post(f"/api/inspections/{inspection_id}/reinspection",
                 files=[("photos", ("x.jpg", corrupt_cases()["truncated"], "image/jpeg"))])
    assert_plain(r, 400, "damaged or truncated")
    assert snapshot(api) == before


def test_oversized_jpeg_upload_is_still_refused_by_the_size_limit(api):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    before = snapshot(api)
    r = make_inspection(api, "CAB-001", rid, [GOOD + b"\x00" * (1024 * 1024)])  # limit is 1 MB in tests
    assert_plain(r, 400, "larger than the 1 MB limit")
    assert snapshot(api) == before


def test_pdf_validation_is_unchanged_by_image_decoding(api):
    make_cabinet(api)
    assert_plain(make_revision(api, data=GOOD), 400, "PDF")
    assert_plain(make_revision(api, data=PDF[:-30]), 400, "damaged or truncated")
    assert make_revision(api).status_code == 201
    rid = api.get("/api/cabinets/CAB-001").json()["design_revisions"][0]["design_revision_id"]
    assert_plain(make_inspection(api, "CAB-001", rid, [PDF]), 400, "JPEG and PNG")


def test_hostile_pillow_failure_in_the_api_is_a_400_not_a_crash(api, monkeypatch):
    make_cabinet(api)
    rid = make_revision(api).json()["design_revision_id"]
    before = snapshot(api)

    def boom(*args, **kwargs):
        raise MemoryError("hostile")

    monkeypatch.setattr(images.Image, "open", boom)
    assert_plain(make_inspection(api, "CAB-001", rid, [GOOD]), 400, "damaged or truncated")
    assert snapshot(api) == before
