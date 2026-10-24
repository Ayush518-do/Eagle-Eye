# Component detection: training and testing guide (RTX 4050, Windows)

**Goal:** find `power_supply`, `mcb` and `io_module` parts in cabinet photos. Tag labels are not a
detector class: OCR finds and reads them.

## The plan in one picture

```text
PUBLIC breaker datasets ──train──► RF-DETR (fine-tuned)  ─┐  source "detector"   (mcb)
                                                           ├─► combined boxes ──► app
pretrained OWLv2 (text prompts, no training) ─────────────┘  source "zero_shot"  (all 3 classes)

COMPANY photos + drawing ──► never trained on ──► answer key ──► honest test scores
```

- **RF-DETR** is a detector already trained on everyday objects. We *fine-tune* it (continue training)
  on public breaker photos, so it learns `mcb`.
- **OWLv2** finds objects from a text description ("a DIN rail power supply unit") with no training.
  No public data exists for DIN-rail power supplies or these I/O modules, so OWLv2 covers those
  classes, and gives a second opinion on breakers.
- **Company photos are only for testing.** Every score on them is measured on data no model learned from.

Company photos are split in `splits.yaml`:

- **dev**: 2 close-ups. You may look at these while choosing prompts and thresholds (*tuning*).
- **test**: 3 photos covering all classes. **Never tune on them.** Final scores come from these only.

| Step | What | Time | Output |
|---|---|---|---|
| 0 | Set up Python + GPU | 30 min, once | `check_env` says GPU OK |
| 1 | OWLv2: tune prompts on dev, then pre-label all | 20 min | previews + Label Studio import file |
| 2 | Label all 5 company photos (the answer key) | 1.5–2 h | Label Studio export |
| 3 | Convert labels | 1 min | `company_coco.json` |
| 4 | Download public data + build dataset | 30 min | `rfdetr_dataset/` |
| 5 | Train the breaker detector | 30–60 min | `checkpoint_best_ema.pth` |
| 6 | Choose thresholds on dev | 10 min | thresholds |
| 7 | Final test on the test photos | 10 min | `test_metrics.json` |
| 8 | Plug into the app | 2 min | `.env` settings |

**Shortcut:** `ml/detection/run.ps1` runs each stage with one command, e.g. `.\ml\detection\run.ps1 setup`,
then `prelabel-dev`, `prelabel-all`, `labelstudio`, `dataset`, `train`, `dev`, `test` (list at the top of the file).
The sections below explain what each stage does.

Run all commands in **PowerShell in the repo folder** (`vit\Eagle-Eye`), on branch `feature/ml-detection`.
Company files are in `data/private/company-dataset/`. `data/private/`, `data/external/` and `runs/` are
ignored by Git. **Never commit them.**

---

## Step 0: Set up (once)

1. `nvidia-smi` should show "NVIDIA GeForce RTX 4050".
2. Python **3.11 or 3.12**, in a separate environment:
   ```powershell
   py -3.11 -m venv .venv-ml
   .venv-ml\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   ```
3. PyTorch **with CUDA**: open https://pytorch.org/get-started/locally/, choose
   *Stable · Windows · Pip · Python · CUDA 12.x*, and run the command shown. It looks like:
   ```powershell
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
   ```
   A plain `pip install torch` gives a CPU-only build, which is the most common mistake.
4. The rest, then check:
   ```powershell
   pip install -r ml/requirements-train.txt
   python -m ml.detection.check_env
   ```
   Expected: `GPU NVIDIA GeForce RTX 4050 Laptop GPU, 6.0 GB` and `GPU test OK`.

## Step 1: OWLv2, tune on dev, then pre-label everything

**1a. Tune on the dev photos only:**
```powershell
python -m ml.detection.prelabel_owlv2 data/private/company-dataset --out data/private/prelabels --only cab1_power_supplies_closeup cab1_breakers_CB11-CB16_closeup
```
The first run downloads OWLv2 (about 600 MB). Open `data/private/prelabels/previews/`:
blue = power_supply, red = mcb, green = io_module.

- Too many wrong boxes → raise `--threshold` (e.g. `0.25`). Parts missed → lower it (e.g. `0.10`).
- Wrong kind of thing found → change the descriptions under `prompts:` in `ml/detection/classes.yaml`.
- Repeat until the dev previews look reasonable. **Write down the final prompts and threshold.**

**1b. Pre-label all 5 photos once with those settings** (don't tune any further after this):
```powershell
python -m ml.detection.prelabel_owlv2 data/private/company-dataset --out data/private/prelabels --threshold 0.15
```

## Step 2: Label all 5 company photos (the answer key)

These labels are what every model is scored against, so they must be careful and complete.
Label Studio is a free labelling tool (Apache-2.0) that runs on your laptop; nothing is uploaded.
Use a **separate** environment, because its packages clash with the training packages:

```powershell
py -3.11 -m venv .venv-ls
.venv-ls\Scripts\Activate.ps1
pip install label-studio
$env:LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED = "true"
$env:LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT = "$PWD\data\private"
label-studio start
```

In the browser (http://localhost:8080):

1. Sign up (a local account) → **Create Project** "Eagle Eye answer key".
2. **Labeling Setup → Custom template → Code**: paste `ml/detection/label_studio_config.xml` → Save.
3. **Settings → Cloud Storage → Add Source Storage → Local files**: absolute path
   `<repo>\data\private\company-dataset`, file filter `.*\.jpg` → **Add storage**. **Don't click "Sync".**
4. **Import** → `data/private/prelabels/label_studio_tasks.json`. OWLv2's boxes appear as suggestions.
   *If photos show as broken images:* delete the tasks, click **Sync Storage**, and label without suggestions.
5. For every photo: zoom in, fix every box (move, resize, delete wrong ones, draw missing ones) → **Submit**.

| Class | One box around | Examples |
|---|---|---|
| `power_supply` | The whole body of each power supply unit, terminals included. Also the narrow redundancy modules for now | PS11, PS21, D13 |
| `mcb` | Each breaker or isolator body, one box per tagged device (a 2-pole breaker is one box) | CB11, DS11, DS1 |
| `io_module` | Each numbered I/O carrier block (the groups with yellow labels), one box per block | block "3" of a column |

- Skip a part only if more than 40 % of it is hidden or cut off by the photo edge.
- Don't box tag stickers, wires, ducts or controllers.
- **Box every visible part**, even small ones in the full-cabinet photos. A part you skip counts against the model.

6. **Export → JSON** (not JSON-MIN, not COCO) → save as `data/private/labels/ls_export.json`.

## Step 3: Convert labels

```powershell
.venv-ml\Scripts\Activate.ps1
python -m ml.detection.import_labels data/private/labels/ls_export.json --photos data/private/company-dataset --out data/private/labels/company_coco.json
```

## Step 4: Download public data and build the dataset

Sign in to Roboflow Universe (free). For each dataset in `ml/detection/public_class_map.yaml`, open the link
→ **Download Dataset → Format: COCO → Download zip**, and unzip into `data/external/<folder name>/`.
Start with **audit-panel** and **circuitbreakerdetection**.

**Look at ~10 images of each first.** Keep a dataset only if its breakers look like ours (DIN-rail
breakers, one box per device). Remove its block from the yaml if not.

```powershell
python -m ml.detection.build_dataset --labels data/private/labels/company_coco.json --photos data/private/company-dataset --splits ml/detection/splits.yaml --public-map ml/detection/public_class_map.yaml --out data/private/rfdetr_dataset
```

It prints, per split, the image count, boxes per class and sources. Check:

- `train` / `valid`: `public:…` sources only, class `mcb`. **Aim for 300+ train boxes.** Fewer → add another dataset.
- `test_full`: 3 company photos with all three classes. `dev_full`: 2 photos.

## Step 5: Train the breaker detector

```powershell
python -m ml.detection.train_rfdetr --dataset data/private/rfdetr_dataset --out runs/rfdetr-mcb-v1
```

- It downloads the RF-DETR Small starting weights, prints a validation score each round (*epoch*), and stops by
  itself when it stops improving. Those scores are on **public** images, not our cabinets. Don't report them.
- **"CUDA out of memory"** → add `--batch-size 1 --grad-accum 16`; still failing → add `--size nano`.

## Step 6: Choose thresholds on dev

A *threshold* is the minimum confidence a box needs to be kept. Run both models on the dev photos,
then try thresholds:

```powershell
python -m ml.detection.predict_all data/private/rfdetr_dataset/dev_full --weights runs/rfdetr-mcb-v1/checkpoint_best_ema.pth --zero-shot --out runs/eval/dev
python -m ml.detection.evaluate --truth data/private/rfdetr_dataset/dev_full --pred-dir runs/eval/dev --out runs/eval/dev_metrics.json --threshold detector=0.3 --threshold zero_shot=0.15
```

Try a few values (e.g. detector 0.3 / 0.5, zero_shot 0.10 / 0.15 / 0.25). Pick the pair with the best
precision/recall balance. **Write them down.**

## Step 7: Final test (once)

```powershell
python -m ml.detection.predict_all data/private/rfdetr_dataset/test_full --weights runs/rfdetr-mcb-v1/checkpoint_best_ema.pth --zero-shot --out runs/eval/test
python -m ml.detection.evaluate --truth data/private/rfdetr_dataset/test_full --pred-dir runs/eval/test --out runs/eval/test_metrics.json --threshold detector=<your value> --threshold zero_shot=<your value> --register-weights runs/rfdetr-mcb-v1/checkpoint_best_ema.pth
```

You get precision, recall and AP50 per class for `detector`, `zero_shot` and `combined`:

- *Precision* = of the boxes drawn, how many were right.
- *Recall* = of the real parts, how many were found.
- *AP50* = both combined over all confidence levels, counting a box as right when it overlaps the real one by at least half.

`detector` scores 0 for power_supply and io_module, because it never learned them. That is expected.
The `combined` row is what the app uses. Look at `runs/eval/test/previews/` to see the boxes.

**Don't go back and tune after seeing these numbers.** If you change anything, the test photos are no
longer a fair test; say so when presenting.

## Step 8: Plug into the app

Add to `.env`:

```text
DETECTOR_WEIGHTS_PATH=runs/rfdetr-mcb-v1/checkpoint_best_ema.pth
DETECTOR_MODEL_SIZE=small
DETECTOR_THRESHOLD=<your detector value>
ZERO_SHOT_ENABLED=true
ZERO_SHOT_THRESHOLD=<your zero_shot value>
```

`ml.interfaces.detect_components()` then returns observations from both sources (contract B, `source:
"detector"` and `"zero_shot"`). The engine merges them and scores how many sources agree.

## Send back for review

Don't send photos or weights. Send:

- `data/private/rfdetr_dataset/dataset_info.json`
- `runs/rfdetr-mcb-v1/train_record.json`
- `runs/eval/dev_metrics.json`, `runs/eval/test_metrics.json`
- 2–3 preview pictures
- The prompts and thresholds you chose

## Files

| File | Purpose |
|---|---|
| `classes.yaml` | The 3 classes, OWLv2 prompts, and which class the detector learns (`detector: true`) |
| `splits.yaml` | Company photos → dev / test (never train) |
| `public_class_map.yaml` | Public datasets and how their classes map to ours |
| `boxes.py` | Box maths, tiles, COCO and Label Studio formats |
| `check_env.py` | Step 0 |
| `zero_shot.py`, `prelabel_owlv2.py` | OWLv2 detector; step 1 |
| `label_studio_config.xml`, `import_labels.py` | Steps 2–3 |
| `build_dataset.py` | Step 4 |
| `train_rfdetr.py` | Step 5 |
| `detector.py`, `predict_all.py` | Tiled detection; steps 6–7 |
| `evaluate.py` | Scores per source and combined |
| `inspect_dataset.py`, `strip_metadata.py`, `split.py` | Earlier helper tools |

Tests (no GPU needed): `pytest ml/tests -q`.

## Credits

Models: RF-DETR (Roboflow, Apache-2.0), OWLv2 (Google, Apache-2.0).
Public datasets used for training (CC BY 4.0, Roboflow Universe), list the ones you actually used:
Audit Panel (parking-detection-nfmxg), CircuitBreakerDetection (Mahmoud Wali),
Control Panels (control-panel-azure), Electrical Devices (VIT).
