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


# ---------- full drawing parser on a small generated drawing (no company data) ----------
def _make_drawing(path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    # page 1: bill of material
    c.setFont("Helvetica", 7)
    c.drawString(200, 760, "BILL OF MATERIAL - 1")
    for x, t in [(50, "ITEM"), (80, "MANUFACTURER"), (180, "MANUFACTURER PART NO."),
                 (300, "ITEM SHORT DESCRIPTION"), (540, "QTY")]:
        c.drawString(x, 740, t)
    rows = [("1", "SCHNEIDER", "A9N2P16C", "ACTI9 MCB, 16A, 2P, C TYPE", "1"),
            ("2", "SCHNEIDER", "A9N2P10C", "ACTI9 MCB, 10A, 2P, C TYPE", "2"),
            ("3", "EMERSON", "VE5127", "BULK POWER SUPPLY 24 VDC, 20A", "1"),
            ("4", "PHOENIX CONTACT", "3001501", "TERMINAL, UK 3 N", "22")]
    for i, r in enumerate(rows):
        y = 728 - 12 * i
        for x, t in zip((52, 80, 180, 300, 542), r):
            c.drawString(x, y, t)
    c.showPage()
    # page 2: schematic. CB11 has a printed rating, CB12/CB13 don't (so the BOM count decides)
    c.setFont("Helvetica", 6)
    c.drawString(100, 700, "CB11"); c.setFont("Helvetica", 5); c.drawString(100, 692, "16A TYPE C")
    c.setFont("Helvetica", 6); c.drawString(100, 640, "CB12"); c.drawString(100, 600, "CB13")
    c.drawString(250, 700, "PS11"); c.setFont("Helvetica", 5); c.drawString(250, 692, "20A 100-240 VAC")
    c.showPage()
    # page 3: general arrangement: callout column (CB11..CB13) and a tiny tag drawn on PS11
    c.setFont("Helvetica", 7); c.drawString(200, 760, "INTERNAL GENERAL ARRANGEMENT")
    for i, t in enumerate(["CB11", "CB12", "CB13"]):
        c.drawString(60, 600 - 9 * i, t)
    c.setFont("Helvetica", 1.5); c.drawString(420, 500, "PS11")
    c.save()


def test_parse_drawing_full(tmp_path):
    pdf = tmp_path / "d.pdf"
    _make_drawing(pdf)
    out = to_contract(pdf)
    items = {i["tag"]: i for i in out["items"]}
    assert set(items) == {"CB11", "CB12", "CB13", "PS11"}
    # BOM read with all columns
    assert [r["part_number"] for r in out["bom"]] == ["A9N2P16C", "A9N2P10C", "VE5127", "3001501"]
    assert out["bom"][3]["manufacturer"] == "PHOENIX CONTACT" and out["bom"][3]["quantity"] == 22
    # printed ratings
    assert items["CB11"]["rating"]["value"] == "16 A" and items["CB11"]["rating"]["curve"] == "C"
    assert items["CB11"]["part_number"] == "A9N2P16C" and items["CB11"]["rating"]["needs_review"] is False
    assert items["PS11"]["component_type"] == "power_supply" and items["PS11"]["part_number"] == "VE5127"
    # inferred from BOM count: 2 unrated breakers, exactly one MCB line with 2 free units
    for t in ("CB12", "CB13"):
        r = items[t]["rating"]
        assert r["value"] == "10 A" and r["source"] == "bom_count" and r["needs_review"] is True
    assert all(k["status"] == "ok" for k in out["bom_checks"])
    # layout + arrangement
    assert items["PS11"]["layout"]["anchor"] == "component"
    assert items["CB11"]["layout"]["anchor"] == "callout"
    assert [items[t]["arrangement"]["position"] for t in ("CB11", "CB12", "CB13")] == [1, 2, 3]
    assert items["CB11"]["arrangement"]["direction"] == "top_to_bottom"


def test_bom_count_not_inferred_when_ambiguous(tmp_path):
    """Two MCB lines with room for the unrated breakers -> no guess; rating stays unknown."""
    from ml.drawing.parse_drawing import link_bom
    items = [{"tag": "CB1", "component_type": "mcb", "rating": {"value": None, "source": None, "page": None,
                                                                 "needs_review": True}, "part_number": None, "description": None}]
    bom = [{"item": 1, "part_number": "A", "description": "MCB, 10A", "quantity": 1, "page": 1},
           {"item": 2, "part_number": "B", "description": "MCB, 16A", "quantity": 1, "page": 1}]
    link_bom(items, bom)
    assert items[0]["rating"]["value"] is None and items[0]["part_number"] is None


# ---------- tag reader rules ----------
def test_only_standalone_tags_count():
    from ml.ocr.read_tags import is_standalone_tag
    assert is_standalone_tag("CB11") and is_standalone_tag("RCCB1") and is_standalone_tag("PS 22")
    assert not is_standalone_tag("CB11-4/PS11-N")      # wire sleeve: mentions a tag, proves nothing
    assert not is_standalone_tag("XG11-1/PS11-PE")
    assert not is_standalone_tag("A9N2P16CIN")          # part number, not a tag
    assert not is_standalone_tag("16A")


def test_merge_keeps_one_reading_per_sticker_and_drops_cut_off_reads():
    from ml.ocr.read_tags import merge_duplicates
    obs = [{"tag": "DS21", "score": 0.70, "bbox": [3142, 1502, 3201, 1536]},
           {"tag": "DS2", "score": 0.75, "bbox": [3145, 1502, 3200, 1532]},     # cut-off read of DS21
           {"tag": "DS21", "score": 0.80, "bbox": [3279, 1002, 3347, 1031]},    # a second, real sticker
           {"tag": "CB11", "score": 0.79, "bbox": [10, 10, 80, 40]},
           {"tag": "CB11", "score": 0.60, "bbox": [12, 11, 79, 41]}]            # same sticker, other tile
    tags = sorted(o["tag"] for o in merge_duplicates(obs))
    assert tags == ["CB11", "DS21", "DS21"]


def test_sideways_label_is_read_and_mapped_back(tmp_path):
    pytest.importorskip("rapidocr_onnxruntime")
    from ml.ocr.read_tags import read_tags
    label = Image.new("RGB", (420, 140), "white")
    ImageDraw.Draw(label).text((30, 20), "CB13", fill="black", font=ImageFont.load_default(size=90))
    img = Image.new("RGB", (900, 900), (200, 200, 200))
    img.paste(label.rotate(90, expand=True), (500, 200))          # printed sideways, like the breakers
    p = tmp_path / "side.png"; img.save(p)
    obs = read_tags(str(p), expected=["CB13", "CB14"])["observations"]
    hits = [o for o in obs if o["text"] == "CB13"]
    assert hits, obs
    x1, y1, x2, y2 = hits[0]["bbox"]
    assert 480 <= x1 and x2 <= 660 and 180 <= y1 and y2 <= 640   # inside where the label was pasted


# ---------- ratings: reading and attaching to tags (positions modelled on a breaker rail) ----------
def test_parse_rating():
    from ml.ocr.ratings import parse_rating
    assert parse_rating("16A") == "16 A" and parse_rating("6A") == "6 A"
    assert parse_rating("16A 415V~") == "16 A"
    assert parse_rating("20A PowerSupply") == "20 A" and parse_rating("40APower Supply") == "40 A"
    assert parse_rating("80A RedundancyN") == "80 A"
    assert parse_rating("24V=|40A") is None            # output spec, starts with a voltage
    assert parse_rating("100-240V~12A-50/60HZ") is None
    assert parse_rating("100A@40°C") is None            # busbar thermal rating
    assert parse_rating("CB11") is None


def test_cut_off_rating_dropped():
    from ml.ocr.ratings import rating_observations
    raw = [{"text": "16A", "score": 0.73, "bbox": [1416, 1236, 1449, 1309]},
           {"text": "6A", "score": 0.58, "bbox": [1416, 1240, 1447, 1279]}]
    assert [r["value"] for r in rating_observations(raw)] == ["16 A"]


def test_each_breaker_gets_the_rating_below_it_not_the_one_above():
    """Ratings sit below each sticker. CB14's nearest text is CB13's '16A' up-right; it must take its own '6A'."""
    from ml.ocr.ratings import assign_ratings
    tags = [{"tag": "CB13", "bbox": [1059, 1697, 1136, 1855]},
            {"tag": "CB14", "bbox": [1060, 2094, 1129, 2239]}]
    ratings = [{"value": "16 A", "raw": "16A", "score": .8, "bbox": [1423, 1877, 1467, 2049]},
               {"value": "6 A", "raw": "6A", "score": .7, "bbox": [1426, 2385, 1461, 2438]},
               {"value": "100 A", "raw": "100A", "score": .8, "bbox": [666, 1452, 699, 1580]}]   # left: ignored
    got = assign_ratings(tags, ratings)
    assert got["CB13"]["value"] == "16 A" and got["CB14"]["value"] == "6 A"


def test_rating_directly_above_in_same_column_allowed():
    from ml.ocr.ratings import assign_ratings
    tags = [{"tag": "D13", "bbox": [2419, 1085, 2480, 1123]}]
    ratings = [{"value": "80 A", "raw": "80A Redundancy", "score": .8, "bbox": [2381, 1059, 2486, 1078]}]
    assert assign_ratings(tags, ratings)["D13"]["value"] == "80 A"


def test_lcs_order_check():
    from ml.ocr.check_photo import lcs
    exp = ["CB11", "CB12", "CB13", "CB14", "CB15", "CB16"]
    obs = ["CB11", "CB12", "CB14", "CB13", "CB15", "CB16"]
    keep = lcs(exp, obs)
    assert len(keep) == 5 and [t for t in obs if t not in keep] in (["CB13"], ["CB14"])
    assert lcs(exp, exp) == exp


# ---------- shared entry points used by the backend ----------
def test_interface_parse_drawing(tmp_path):
    from ml.interfaces import parse_drawing
    pdf = tmp_path / "d.pdf"
    _make_drawing(pdf)
    out = parse_drawing(str(pdf))
    assert {i["tag"] for i in out["items"]} == {"CB11", "CB12", "CB13", "PS11"} and out["contract_version"] == "0.3"


def test_interface_parse_drawing_without_tags_refuses(tmp_path):
    from reportlab.pdfgen import canvas
    from ml.interfaces import ModelUnavailableError, parse_drawing
    pdf = tmp_path / "empty.pdf"
    c = canvas.Canvas(str(pdf)); c.drawString(100, 700, "no tags here"); c.save()
    with pytest.raises(ModelUnavailableError, match="by hand"):
        parse_drawing(str(pdf))


def test_interface_read_tags_returns_tags_and_ratings(tmp_path):
    pytest.importorskip("rapidocr_onnxruntime")
    from ml.interfaces import read_tags
    img = Image.new("RGB", (900, 400), "white")
    d = ImageDraw.Draw(img)
    d.text((60, 40), "CB11", fill="black", font=ImageFont.load_default(size=80))
    d.text((60, 200), "16A", fill="black", font=ImageFont.load_default(size=80))
    p = tmp_path / "x.png"; img.save(p)
    obs = read_tags(str(p), ["CB11", "CB12"])["observations"]
    kinds = {(o["kind"], o["text"]) for o in obs}
    assert ("tag_label", "CB11") in kinds and ("rating_text", "16 A") in kinds
