"""Small valid files and request helpers for the API tests (no imaging library needed)."""
import struct
import zlib

def pdf_bytes() -> bytes:
    """A small complete PDF (catalog, pages, one blank page, xref table, trailer)."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


PDF = pdf_bytes()


def png_bytes(width: int = 40, height: int = 30) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows))
            + chunk(b"IEND", b""))


# A real 64 x 48 baseline JPEG (674 bytes, solid colour), written once with an imaging library.
JPEG_SIZE = (64, 48)
_JPEG_HEX = (
    "ffd8ffe000104a46494600010100000100010000ffdb0043001b12141714111b1716171e1c1b2028422b28252528513a3d30"
    "42605565645f555d5b6a7899816a7190735b5d85b586909ea3abadab6780bcc9baa6c799a8aba4ffdb0043011c1e1e282328"
    "4e2b2b4ea46e5d6ea4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4a4"
    "a4a4a4a4a4a4a4a4ffc00011080030004003012200021101031101ffc4001f00000105010101010101000000000000000001"
    "02030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114"
    "328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a53545556"
    "5758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5"
    "b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f010003"
    "0101010101010101010000000000000102030405060708090a0bffc400b51100020102040403040705040400010277000102"
    "031104052131061241510761711322328108144291a1b1c109233352f0156272d10a162434e125f11718191a262728292a35"
    "363738393a434445464748494a535455565758595a636465666768696a737475767778797a82838485868788898a92939495"
    "969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9ea"
    "f2f3f4f5f6f7f8f9faffda000c03010002110311003f0028a28aa2428a28a0028a28a0028a28a0028a28a0028a28a0028a28"
    "a0028a28a0028a28a0028a28a0028a28a0028a28a00fffd9"
)


def jpeg_bytes() -> bytes:
    return bytes.fromhex(_JPEG_HEX)


def make_cabinet(api, cabinet_id="CAB-001", name="Line 3 panel"):
    return api.post("/api/cabinets", json={"cabinet_id": cabinet_id, "name": name})


def make_revision(api, cabinet_id="CAB-001", label="REV-A", data=PDF):
    return api.post(f"/api/cabinets/{cabinet_id}/design-revisions", data={"label": label},
                    files={"drawing": ("drawing.pdf", data, "application/pdf")})


def make_inspection(api, cabinet_id, revision_id, photos=None):
    photos = photos if photos is not None else [png_bytes()]
    files = [("photos", (f"p{i}.png", p, "image/png")) for i, p in enumerate(photos)]
    return api.post(f"/api/cabinets/{cabinet_id}/inspections", data={"design_revision_id": revision_id},
                    files=files or None)


def manual_box(observation_id, text, bbox=(1, 2, 30, 20), text_confidence=0.97):
    return {"observation_id": observation_id, "source": "manual", "kind": "tag_label",
            "class_name": "tag_label", "bbox": list(bbox), "confidence": None, "text": text,
            "raw_text": None, "text_confidence": text_confidence, "model": None}


def post_observations(api, inspection_id, image, boxes, **extra):
    return api.post(f"/api/inspections/{inspection_id}/observations",
                    json={"image_id": image["image_id"], "image_size": [image["width"], image["height"]],
                          "observations": boxes, **extra})


def setup_inspection(api, tags=("CB11", "PS11"), photos=None):
    """Cabinet + revision + expected items + inspection. Returns (inspection_id, revision_id)."""
    assert make_cabinet(api).status_code == 201
    revision = make_revision(api).json()["design_revision_id"]
    r = api.post(f"/api/design-revisions/{revision}/expected-items", json={"items": [{"tag": t} for t in tags]})
    assert r.status_code == 201, r.text
    created = make_inspection(api, "CAB-001", revision, photos)
    assert created.status_code == 202, created.text
    return created.json()["inspection_id"], revision


# ---------- generated image fixtures (Pillow is a declared backend dependency) ----------
def noisy_image(size=(96, 72), mode="RGB", seed=7):
    """Deterministic random pixels: the compressed data is large enough to corrupt meaningfully."""
    import random

    from PIL import Image

    rng = random.Random(seed)
    channels = len(Image.new(mode, (1, 1)).getbands())
    return Image.frombytes(mode, size, bytes(rng.randrange(256) for _ in range(size[0] * size[1] * channels)))


def pillow_bytes(image, **save) -> bytes:
    import io

    buf = io.BytesIO()
    image.save(buf, **save)
    return buf.getvalue()


def noisy_jpeg(size=(96, 72), mode="RGB", seed=7, **save) -> bytes:
    return pillow_bytes(noisy_image(size, mode, seed), format="JPEG", **({"quality": 85} | save))


def scan_start(jpeg: bytes) -> int:
    """Index of the first byte of compressed pixel data (just after the first SOS header)."""
    sos = jpeg.index(b"\xff\xda")
    return sos + 2 + int.from_bytes(jpeg[sos + 2:sos + 4], "big")


def jpeg_with_size(jpeg: bytes, width: int, height: int) -> bytes:
    """The same bytes with the frame header claiming another size (a decompression-bomb shape)."""
    for marker in (b"\xff\xc0", b"\xff\xc1", b"\xff\xc2"):
        if marker in jpeg:
            i = jpeg.index(marker)
            return jpeg[: i + 5] + struct.pack(">HH", height, width) + jpeg[i + 9:]
    raise ValueError("no frame header")


def png_with_header(width: int, height: int, depth: int = 8, color: int = 2) -> bytes:
    """A PNG whose header promises a lot of pixels but whose data is tiny."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00" * 16))
            + chunk(b"IEND", b""))
