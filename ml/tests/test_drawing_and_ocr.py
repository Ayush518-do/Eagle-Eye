import pytest
from PIL import Image, ImageDraw, ImageFont

from ml.drawing.parse_drawing import Word, find_tags, rebuild_stacked_text, to_contract
from ml.ocr.tag_matcher import match_tag

EXPECTED = ["CB11", "CB12", "PS11", "DS1"]


# ---------- tag matcher ----------
@pytest.mark.parametrize("raw,tag", [("CB11", "CB11"), ("cb-11", "CB11"), ("C811", "CB11"), ("PSl1", "PS11")])
def test_matches_lookalikes(raw, tag):
    m = match_tag(raw, EXPECTED)
    assert m.tag == tag and m.raw == raw


def test_unrelated_text_not_matched():
    assert match_tag("24VDC", EXPECTED).tag is None


def test_ambiguous_reading_left_for_review():
    assert match_tag("CB1?", ["CB11", "CB12"]).tag is None


# ---------- drawing ----------
def test_stacked_characters_rebuilt_per_column():
    chars = [Word(c, 4, 100, top, 104, top + 5) for top, c in [(30, "V"), (10, "2"), (20, "4")]]
    chars += [Word(c, 4, 140, top, 144, top + 5) for top, c in [(10, "5"), (20, "A")]]
    assert rebuild_stacked_text(chars) == ["24V", "5A"]


def test_find_tags_ignores_non_tags():
    words = [Word("CB11", 1, 0, 0, 1, 1), Word("Breaker", 1, 0, 0, 1, 1), Word("PS11", 3, 0, 0, 1, 1)]
    assert set(find_tags(words)) == {"CB11", "PS11"}


def test_contract_from_generated_pdf(tmp_path):
    from reportlab.pdfgen import canvas
    pdf = tmp_path / "d.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(100, 700, "CB11 MCB 10A"); c.drawString(100, 680, "PS11 Power supply")
    c.showPage(); c.drawString(100, 700, "CB11"); c.save()
    out = to_contract(pdf)
    tags = {i["tag"]: i for i in out["items"]}
    assert set(tags) == {"CB11", "PS11"}
    assert tags["CB11"]["source_page"] == 1
    assert all(i["rating"]["needs_review"] for i in out["items"])   # never guessed
    assert len(out["drawing_file_sha256"]) == 64


# ---------- OCR (runs only when RapidOCR is installed) ----------
def test_read_tags_on_generated_label(tmp_path):
    pytest.importorskip("rapidocr_onnxruntime")
    from ml.ocr.read_tags import read_tags
    img = Image.new("RGB", (600, 200), "white")
    font = ImageFont.load_default(size=80)
    ImageDraw.Draw(img).text((60, 50), "CB11", fill="black", font=font)
    p = tmp_path / "label.png"; img.save(p)
    out = read_tags(str(p), expected=EXPECTED)
    texts = [o["text"] for o in out["observations"]]
    assert "CB11" in texts
    obs = out["observations"][0]
    x1, y1, x2, y2 = obs["bbox"]
    assert x2 > x1 and y2 > y1 and out["image_size"] == [600, 200]
