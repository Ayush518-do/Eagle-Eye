# Part 2 — Drawing parser and OCR (ML)

Branch: `feature/ml-ocr-drawing` · Folder: `ml/ocr/`, `ml/drawing/` · Produces: contract A and contract B (`kind: "tag_label"`)

**Goal:** (1) read the drawing PDF and list what *should* be in the cabinet; (2) read the printed tag
labels (for example `CB11`) in the photos. OCR means optical character recognition: turning text in an
image into characters.

## What we already know (prototype, not in the repo)

- The BOM (bill of materials, the parts list) in the drawing has 70 lines; all were read.
- Breaker and isolator ratings CB11–CB26 and DS1–DS2 were read from the schematic pages.
- Power-supply ratings PS11–PS23 could not be read: the schematic prints them as stacked single
  characters. They must come out as `needs_review: true`, never guessed.
- On 12 hand-marked tag regions: RapidOCR 12/12 exact, Tesseract 5/12 (7 wrong). One reviewer, same
  photos used for development, so treat it as a sanity check, not a measured accuracy.

## Tasks

- [ ] 1. `ml/drawing/parse_drawing.py`: rebuild the BOM reader (use `pdfplumber` or PyMuPDF text with positions).
      Output contract A.
- [ ] 2. Add the schematic rating reader for CB/DS tags; mark anything uncertain `needs_review: true`.
- [ ] 3. Try one approach for PS11–PS23 (rebuilding stacked characters by their x/y positions). If it is
      not reliable, leave them for human review and say so.
- [ ] 4. `ml/ocr/find_labels.py`: find tag-label regions in a full-resolution photo (RapidOCR's text
      detector), then read each crop.
- [ ] 5. Match readings to the expected tag list from the drawing (for example `C811` → `CB11`) and keep
      both the raw text and the matched tag, so a correction is always visible.
- [ ] 6. Implement `parse_drawing()` and `read_tags()` in `ml/interfaces.py`.
- [ ] 7. `ml/ocr/eval_ocr.py`: compare readings against an answer key kept in `data/private/`.
      Write the answer key from photos not used while tuning, if any become available.
- [ ] 8. Unit tests with small synthetic images and a tiny generated PDF (`backend/tests/` or `ml/tests/`).
- [ ] 9. Share the text-detector boxes with Part 1 as labelling proposals.

## Done when

- `parse_drawing` returns contract A for the real drawing, with every uncertain value flagged.
- `read_tags` returns contract B for a photo, with raw and matched text.
- OCR results are reported with how many labels, which photos and who made the answer key.
