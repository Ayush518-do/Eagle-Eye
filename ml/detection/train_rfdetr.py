"""Step 5: fine-tune RF-DETR on the dataset from build_dataset.py (on the RTX 4050).

    python -m ml.detection.train_rfdetr --dataset data/private/rfdetr_dataset --out runs/rfdetr-mcb-v1

"Fine-tune" = start from a model already trained on everyday objects (COCO) and continue training it
on our parts. That needs far less data than training from scratch.

Memory (RTX 4050 = 6 GB): batch 2 x 8 accumulation steps = an effective batch of 16 images per update.
If you get "CUDA out of memory": --batch-size 1 --grad-accum 16, or --size nano.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--size", choices=["nano", "small", "medium"], default="small")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--patience", type=int, default=8, help="stop after this many rounds without improvement")
    ap.add_argument("--workers", type=int, default=0, help="0 is safest on Windows")
    a = ap.parse_args()

    for split in ("train", "valid"):
        if not (a.dataset / split / "_annotations.coco.json").exists():
            raise SystemExit(f"Missing {a.dataset / split / '_annotations.coco.json'}. Run build_dataset first.")

    import rfdetr
    import torch
    from ml.detection.detector import SIZES
    if not torch.cuda.is_available():
        print("WARNING: no GPU found. Training on CPU will take many hours. See README step 0.")

    a.out.mkdir(parents=True, exist_ok=True)
    model = getattr(rfdetr, SIZES[a.size])()
    started = time.time()
    model.train(
        dataset_dir=str(a.dataset),
        output_dir=str(a.out),
        epochs=a.epochs,
        batch_size=a.batch_size,
        grad_accum_steps=a.grad_accum,
        lr=a.lr,
        early_stopping=True,
        early_stopping_patience=a.patience,
        num_workers=a.workers,
    )
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = None
    record = {
        "model": f"rf-detr-{a.size}", "dataset": str(a.dataset), "epochs_max": a.epochs,
        "batch_size": a.batch_size, "grad_accum": a.grad_accum, "lr": a.lr,
        "minutes": round((time.time() - started) / 60, 1), "git_commit": commit,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
    }
    (a.out / "train_record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))
    print(f"\nBest weights: {a.out / 'checkpoint_best_total.pth'}")
    print("Next: README steps 6-7 (predict_all + evaluate on the company test photos). Validation numbers are from public images, NOT our cabinets.")


if __name__ == "__main__":   # required on Windows: training starts worker processes
    main()
