# Part 2 — Drawing parser and tag reading

Task list: [`../../docs/team/ml-ocr-drawing.md`](../../docs/team/ml-ocr-drawing.md).
Outputs: contract A (drawing) and contract B (`kind: "tag_label"`) in [`../../docs/contracts.md`](../../docs/contracts.md).

```text
ml/
├── drawing/parse_drawing.py   # tags + page from the PDF; stacked-character helper; ratings marked needs_review
└── ocr/
    ├── read_tags.py           # RapidOCR on a photo -> observations (raw_text kept)
    └── tag_matcher.py         # "C811" -> "CB11" with look-alike swaps; ambiguous -> no match
```

```bash
pip install -r ml/requirements-ocr.txt
python -m ml.drawing.parse_drawing data/private/drawing.pdf
python -m ml.ocr.read_tags data/private/photo1.jpg --expected CB11 CB12 PS11
pytest ml/tests -q
```

## Not done yet (needs the drawing and photos)
- BOM table reader fitted to the real drawing (part numbers, descriptions, quantities)
- CB/DS rating reader; PS11–PS23 stacked ratings checked on the real drawing
- Full-resolution crop reading for small labels, answer-key evaluation (`eval_ocr.py`)
- Wiring `parse_drawing()` / `read_tags()` into `ml/interfaces.py`
