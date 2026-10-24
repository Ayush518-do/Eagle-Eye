# Drawing parser + tag/rating reading (no training, no labelling)

This is the **core check** of Eagle Eye: read what the drawing expects, read the tag stickers and ratings
in the photo, compare. Everything uses the drawing's text layer and pretrained OCR (RapidOCR); nothing
is trained and nothing needs labelling. Runs on a normal processor.

```text
drawing PDF ──parse_drawing──► expected items (tag, type, rating, part no., position, order)
                                        │
photo ──read_tags + ratings──► tags read + ratings read
                                        ▼
                               check_photo ──► found / not read · rating match / mismatch · order
```

## Commands

```powershell
# 1. Drawing -> expected items (contract A)
python -m ml.drawing.parse_drawing data/private/company-dataset/cab1_drawing_13GE03331.pdf --out data/private/expected_items.json

# 2. Photos vs drawing
python -m ml.ocr.check_photo data/private/company-dataset/cab1_breakers_CB11-CB16_closeup.jpg data/private/company-dataset/cab1_power_supplies_closeup.jpg --expected data/private/expected_items.json --out data/private/checks

# Demo only: pretend the drawing said CB14 is 16 A -> must be flagged as a mismatch (report marked synthetic)
python -m ml.ocr.check_photo data/private/company-dataset/cab1_breakers_CB11-CB16_closeup.jpg --expected data/private/expected_items.json --override "CB14=16 A"

# Just the tag readings for one photo (contract B, kind tag_label)
python -m ml.ocr.read_tags <photo> --expected-json data/private/expected_items.json --out <file.json>
```

Install: `pip install -r ml/requirements-ocr.txt`. Reading one 12-megapixel photo takes ~20 s on a laptop processor.

## What the drawing parser reads

| From | What | How |
|---|---|---|
| Bill of material pages | Every line: item, manufacturer, part number, description, quantity | Columns from the header words' positions |
| Schematic pages | Each component tag and the rating printed under it ("16A TYPE C", "40A 100-240 VAC") | Words read with a 1-point letter gap, so neighbouring labels don't merge |
| Same | Ratings that aren't printed (CB61–CB79 only say "TYPE C") | Inferred **only** when the BOM count proves it (exactly one breaker line with exactly that many unassigned units); marked `needs_review` |
| General-arrangement page | Position of each tag (tiny text drawn on the part = real position; callout list = beside the view) and the order of tags in each row/column | Rows from tiny tags at the same height; columns from callout lists |
| BOM ↔ tags | Part number per tag and a count check per BOM line | e.g. "A9N2P16C: 6 tags found / 6 in BOM: ok" |

## Rules in the photo reader

- The photo is turned upright first (EXIF rotation), read in overlapping 1280 px tiles, each tile as-is and turned 90° (breaker stickers are sideways).
- **Only standalone tags count.** Wire sleeves printed "CB11-4/PS11-N" mention a tag but prove nothing, so they're ignored. Part numbers like "A9N2P16CIN" too.
- Look-alike fixes ("C811" → "CB11") only when lengths agree; the raw reading is always kept (`raw_text`).
- The same sticker read twice is merged; a cut-off read at the same spot ("DS2" inside "DS21", "6A" inside "16A") is dropped.
- A rating belongs to the nearest tag it sits **below** (or directly above in the same column), never to a tag on its right. The busbar's "100A@40°C" and input/output specs ("24V=|40A") are not device ratings.
- "Not read" is reported as **inconclusive**, never as missing.

## Results on the company data (24 Oct 2026)

Not tuned on any answer key. The checks below were made by looking at the photos.

- **Drawing:** 46 components, 70/70 BOM lines; 28 ratings printed, 18 inferred from BOM counts (CB61–CB79, needs review), 0 unknown; all 9 BOM count checks OK; 6 arrangement groups. Order and ratings agree with what the close-up photos show.
- **Breaker close-up:** 7 tags read (CB11–CB16, DS1), none wrong; ratings 6/6 match on CB11–CB16 (DS1 rating not read); order matches.
- **Power-supply close-up:** all 12 visible tags read, none wrong; 6 ratings match (PS11, PS21, PS12, PS13, PS23, D13), 6 not read (PS22, D23, DS11–DS22); both rows in drawing order.
- **Full-cabinet and I/O photos:** stickers too small to read reliably; reported as not read.
- **Synthetic demo:** with the drawing's CB14 changed to 16 A, CB14 is flagged as a mismatch (reads 6 A).

Limits: one cabinet, close-up photos only, one person checking by eye. Not a measured accuracy on unseen cabinets.
