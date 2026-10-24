# Part 1 — Component detection

Task list: [`../../docs/team/part1-ml-detection.md`](../../docs/team/part1-ml-detection.md).
Output format: contract B in [`../../docs/contracts.md`](../../docs/contracts.md).

```text
ml/detection/
├── classes.yaml          # agreed class list
├── inspect_dataset.py    # what is in a folder: counts, sizes, duplicates, corrupt files, labels
├── strip_metadata.py     # clean working copies without GPS/camera metadata
└── split.py              # train/test split by cabinet group
```

```bash
pip install -r ml/requirements-detection.txt
python -m ml.detection.inspect_dataset data/private/photos
python -m ml.detection.strip_metadata data/private/photos data/private/clean
python -m ml.detection.split data/private/groups.csv --test-groups CAB-B --out data/private/split.json
pytest ml/tests -q
```

All company files stay in `data/private/` (ignored by Git).

## Not started yet (needs decisions or documents)
- Model choice and baseline run (D-FINE-S or YOLOX-s, Apache-2.0)
- Labelling (local tool, no cloud upload) and training — needs permission to train on company images
- `evaluate.py`, `models/registry.json`, `detect_components()` in `ml/interfaces.py`
