# Component detector: training guide (RTX 4050, Windows)

**Goal:** a detector that draws boxes around `power_supply`, `mcb` and `io_module` parts in cabinet
photos. Tag labels are not a detector class: OCR finds and reads those.

**How:** start from RF-DETR Small, a model already trained on everyday objects. Teach it our parts
using the company photos (labelled by us) plus public breaker photos. That is *fine-tuning*.
OWLv2, a model that finds objects from a text description with no training, draws first-guess boxes
so labelling is faster, and later acts as a second, independent detector.

| Step | What | Time | Output |
|---|---|---|---|
| 0 | Set up Python + GPU | 30 min, once | `check_env` says GPU OK |
| 1 | OWLv2 test + first-guess boxes | 15 min | preview pictures, Label Studio import file |
| 2 | Correct the boxes in Label Studio | 1.5–2 h | Label Studio export |
| 3 | Convert labels to COCO | 1 min | `company_coco.json` |
| 4 | Public data + build dataset (tiles) | 20 min | `rfdetr_dataset/` |
| 5 | Train | 30–60 min | `checkpoint_best_total.pth` |
| 6 | Evaluate on the unseen cabinet | 5 min | `test_metrics.json` |
| 7 | Run on photos, plug into the app | 5 min | pictures with boxes, `.env` settings |

All commands run in **PowerShell in the repo folder** (`vit\Eagle-Eye`), on branch `feature/ml-detection`.
Company photos are in `data/private/company-dataset/`. Everything under `data/private/`, `data/external/`
and `runs/` is ignored by Git. **Never commit them.**

---

## Step 0: Set up (once)

1. Check the GPU driver: `nvidia-smi` should show "NVIDIA GeForce RTX 4050".
2. Python **3.11 or 3.12** (`py -3.11 --version`). Then make a separate environment for ML:
   ```powershell
   py -3.11 -m venv .venv-ml
   .venv-ml\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   ```
3. Install PyTorch **with CUDA**: open https://pytorch.org/get-started/locally/, choose
   *Stable · Windows · Pip · Python · CUDA 12.x*, and run the command it shows. It looks like:
   ```powershell
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
   ```
   A plain `pip install torch` gives a CPU-only build, which is the most common mistake.
4. The rest:
   ```powershell
   pip install -r ml/requirements-train.txt
   python -m ml.detection.check_env
   ```
   Expected: `GPU  NVIDIA GeForce RTX 4050 Laptop GPU, 6.0 GB` and `GPU test OK`.

## Step 1: OWLv2 test + first-guess boxes

```powershell
python -m ml.detection.prelabel_owlv2 data/private/company-dataset --out data/private/prelabels
```

The first run downloads OWLv2 (about 600 MB). Then open the pictures in `data/private/prelabels/previews/`
and look at them: blue = power_supply, red = mcb, green = io_module.

- **Boxes mostly right?** Good: labelling will be quick, and OWLv2 is useful as our second detector.
- **Many wrong or missing?** Normal for unusual parts. Try `--threshold 0.10` (more boxes) or `0.25`
  (fewer), or edit the descriptions under `prompts:` in `ml/detection/classes.yaml`, and run again.
  Labelling just takes longer.

Write down what you saw. It goes in the results note (step 6).

## Step 2: Correct the boxes in Label Studio

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

1. Sign up (a local account on your laptop) → **Create Project** "Eagle Eye parts".
2. **Labeling Setup → Custom template → Code**: paste the content of `ml/detection/label_studio_config.xml` → Save.
3. **Settings → Cloud Storage → Add Source Storage → Local files**:
   absolute path = `<repo>\data\private\company-dataset` (e.g. `C:\Users\archi\OneDrive\Desktop\vit\Eagle-Eye\data\private\company-dataset`),
   file filter `.*\.jpg` → **Add storage**. **Don't click "Sync"**: that would create a second set of tasks.
4. **Import** → upload `data/private/prelabels/label_studio_tasks.json`. Each photo appears with
   OWLv2's boxes as suggestions.
   *If the photos show as broken images:* delete the tasks, click **Sync Storage** instead, and label
   without suggestions.
5. Label each photo. Zoom in (mouse wheel) and fix every box: move, resize, delete wrong ones, draw missing ones.
   Then **Submit**.

**What to box (be consistent, the model copies you exactly):**

| Class | One box around | Example |
|---|---|---|
| `power_supply` | The whole body of each power supply unit, terminals included. Also the narrow redundancy modules D13/D23 for now | PS11, PS21, D13 |
| `mcb` | Each breaker or isolator body, one box per tagged device (a 2-pole breaker is one box) | CB11, DS11, DS1 |
| `io_module` | Each numbered I/O carrier block (the groups 1–8 with yellow labels), one box per block | block "3" in a column |

- Skip a part if more than 40 % of it is hidden or cut off by the photo edge.
- Don't box tag stickers, wires, ducts or the controllers.
- Label **all 5 photos**, including cabinet 2: it becomes the test, and test labels must be just as careful.

6. **Export → JSON** (not JSON-MIN, not COCO) → save as `data/private/labels/ls_export.json`.

## Step 3: Convert labels

```powershell
.venv-ml\Scripts\Activate.ps1
python -m ml.detection.import_labels data/private/labels/ls_export.json --photos data/private/company-dataset --out data/private/labels/company_coco.json
```

It prints the boxes per class per photo. Check the numbers look right.

## Step 4: Public data + build the dataset

**Public breaker photos (optional, recommended for `mcb`):** sign in to Roboflow Universe (free), open each
link below → **Download Dataset → Format: COCO → Download zip**, and unzip into `data/external/<folder>/`:

| Folder | Dataset | Licence |
|---|---|---|
| `data/external/audit-panel/` | https://universe.roboflow.com/parking-detection-nfmxg/audit-panel | CC BY 4.0 |
| `data/external/circuitbreakerdetection/` | https://universe.roboflow.com/mahmoud-wali/circuitbreakerdetection | CC BY 4.0 |

Each folder must contain `train/` and `valid/` with `_annotations.coco.json`. Look at 10 images of
each first. If their "circuit breaker" boxes don't look like our DIN-rail breakers, set that class to
`null` in `ml/detection/public_class_map.yaml`.

Build:

```powershell
python -m ml.detection.build_dataset --labels data/private/labels/company_coco.json --photos data/private/company-dataset --splits ml/detection/splits.yaml --public-map ml/detection/public_class_map.yaml --out data/private/rfdetr_dataset
```

Without public data, leave out `--public-map ...`.

What it does:

- Cuts each photo into overlapping 1024 px tiles, plus one shrunk copy of the whole photo. Small parts stay
  visible, and 5 photos become roughly 80 training images.
- Splits by **cabinet**, as set in `ml/detection/splits.yaml`. Cabinet 2 = test, never trained on.
- Prints the boxes per class per split. **Check `train` has at least ~20 boxes of each class.**

## Step 5: Train

```powershell
python -m ml.detection.train_rfdetr --dataset data/private/rfdetr_dataset --out runs/rfdetr-small-v1
```

- The first run downloads the RF-DETR Small starting weights.
- It prints a validation score each round (*epoch*) and stops by itself when it stops improving.
  These validation numbers come from another photo of cabinet 1, so they are **optimistic**. Don't report them.
- **"CUDA out of memory"** → add `--batch-size 1 --grad-accum 16`; still failing → add `--size nano`.
- Training writes `runs/rfdetr-small-v1/checkpoint_best_total.pth` and `train_record.json`.

## Step 6: Evaluate on the unseen cabinet

```powershell
python -m ml.detection.evaluate --weights runs/rfdetr-small-v1/checkpoint_best_total.pth --test data/private/rfdetr_dataset/test_full --out runs/rfdetr-small-v1/test_metrics.json --register
```

Prints precision, recall and AP50 per class on cabinet 2.

- *Precision* = of the boxes drawn, how many were right.
- *Recall* = of the real parts, how many were found.
- *AP50* = both combined, counting a box as right when it overlaps the real one by at least half (IoU ≥ 0.5).

**Only `io_module` has test data** (cabinet 2 has no power supplies or breakers in view). The others
show "no test data". That's the honest result until the company sends more cabinets.
`--register` adds the result to `models/registry.json`. Commit that file; the weights stay out of Git.

## Step 7: Run it on photos and plug it into the app

```powershell
python -m ml.detection.predict data/private/company-dataset/cab1_full_front.jpg --weights runs/rfdetr-small-v1/checkpoint_best_total.pth
```

Open `runs/predictions/*_pred.jpg` to see the boxes. To let the backend use the model, add to `.env`:

```text
DETECTOR_WEIGHTS_PATH=runs/rfdetr-small-v1/checkpoint_best_total.pth
DETECTOR_MODEL_SIZE=small
DETECTOR_THRESHOLD=0.3
```

`ml.interfaces.detect_components()` then returns real observations (contract B, `source: "detector"`).

## Send back for review

Don't send the photos or the weights. Send these:

- `data/private/rfdetr_dataset/dataset_info.json`
- `runs/rfdetr-small-v1/train_record.json` and `test_metrics.json`
- 2–3 preview pictures (OWLv2 and trained model)
- What OWLv2 got right or wrong, in a few sentences

## Files

| File | Purpose |
|---|---|
| `classes.yaml` | The 3 classes + OWLv2 descriptions |
| `boxes.py` | Box maths, tiles, COCO and Label Studio formats |
| `check_env.py` | Step 0 check |
| `prelabel_owlv2.py` | Step 1 |
| `label_studio_config.xml` | Step 2 labelling screen |
| `import_labels.py` | Step 3 |
| `build_dataset.py`, `splits.yaml`, `public_class_map.yaml` | Step 4 |
| `train_rfdetr.py` | Step 5 |
| `evaluate.py` | Step 6 |
| `detector.py`, `predict.py` | Step 7; tiled detection used by the app |
| `inspect_dataset.py`, `strip_metadata.py`, `split.py` | Earlier helper tools |

Tests (no GPU needed): `pytest ml/tests -q`.

## Credits

If public datasets are used: *Audit Panel* (Roboflow Universe, parking-detection-nfmxg) and
*CircuitBreakerDetection* (Roboflow Universe, Mahmoud Wali), both CC BY 4.0.
Models: RF-DETR (Roboflow, Apache-2.0), OWLv2 (Google, Apache-2.0).
