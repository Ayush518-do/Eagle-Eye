# ML: component detection (overview)

**Step-by-step guide: [`ml/detection/README.md`](../../ml/detection/README.md).**

Branch: `feature/ml-detection` · Folder: `ml/detection/` · Produces: contract B (`kind: "component"`)

## Strategy

| Class | Found by | Learned from |
|---|---|---|
| `mcb` (CB/DS breakers) | RF-DETR Small, fine-tuned (source `detector`) + OWLv2 (source `zero_shot`) | Public CC BY 4.0 breaker datasets |
| `power_supply` | OWLv2 zero-shot (text prompts) | Nothing: pretrained only (no public data exists) |
| `io_module` | OWLv2 zero-shot (text prompts) | Nothing: pretrained only (no public data exists) |
| tag labels | OCR (ML drawing/OCR branch) | Pretrained OCR |

**Company photos are never trained on.** They are the answer key: 2 *dev* photos for choosing prompts and
thresholds, 3 *test* photos for the final, honest scores (`ml/detection/splits.yaml`).

## Done when

- [ ] All 5 company photos labelled (answer key), `company_coco.json` written.
- [ ] Breaker detector trained on public data; `train_record.json` saved.
- [ ] Prompts and thresholds chosen on dev only.
- [ ] Test scores per source and combined in `runs/eval/test_metrics.json` and `models/registry.json`.
- [ ] `detect_components()` works with `.env` settings; the backend gets observations from both sources.
