# Eagle Eye detection pipeline: one command per stage (Windows PowerShell, from the repo folder).
#
#   .\ml\detection\run.ps1 setup [-Py 3.12] # step 0: create .venv-ml, install PyTorch (CUDA) + packages, check GPU
#   .\ml\detection\run.ps1 prelabel-dev # step 1a: OWLv2 on the 2 dev photos only (tune prompts here)
#   .\ml\detection\run.ps1 prelabel-all # step 1b: OWLv2 on all 5 photos -> Label Studio import file
#   .\ml\detection\run.ps1 labelstudio  # step 2: start Label Studio (separate .venv-ls)
#   .\ml\detection\run.ps1 dataset      # steps 3-4: convert labels + build dataset (needs ls_export.json + public data)
#   .\ml\detection\run.ps1 train        # step 5: train the breaker detector on the GPU (public data; can run while you label)
#   .\ml\detection\run.ps1 dev          # step 6: both models on dev photos + scores (choose thresholds)
#   .\ml\detection\run.ps1 test -Det 0.3 -Zs 0.15   # step 7: final test, once
#
# If PowerShell refuses to run scripts: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
param(
    [Parameter(Mandatory = $true)][string]$Stage,
    [double]$Det = 0.3,
    [double]$Zs = 0.15,
    [string]$Cuda = "cu126",
    [string]$Py = "3.11"
)
$ErrorActionPreference = "Stop"
$Photos = "data/private/company-dataset"
$Data = "data/private/rfdetr_dataset"      # company test/dev answer key (+ public, unused here)
$Public = "data/private/public_dataset"   # public training data only
$Run = "runs/rfdetr-mcb-v1"
$Weights = "$Run/checkpoint_best_ema.pth"

function Use-Ml {
    if (-not (Test-Path ".venv-ml")) { throw "Run '.\ml\detection\run.ps1 setup' first." }
    . .\.venv-ml\Scripts\Activate.ps1
}
function Check([string]$what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE). Copy the messages above and send them over." } }

switch ($Stage) {
    "setup" {
        if (-not (Test-Path ".venv-ml")) { py -$Py -m venv .venv-ml; Check "Creating .venv-ml (is Python $Py installed? list them with: py -0)" }
        . .\.venv-ml\Scripts\Activate.ps1
        python -m pip install --upgrade pip; Check "pip upgrade"
        pip install torch torchvision --index-url "https://download.pytorch.org/whl/$Cuda"; Check "PyTorch install"
        pip install -r ml/requirements-train.txt; Check "package install"
        python -m ml.detection.check_env; Check "check_env"
    }
    "prelabel-dev" {
        Use-Ml
        python -m ml.detection.prelabel_owlv2 $Photos --out data/private/prelabels --only cab1_power_supplies_closeup cab1_breakers_CB11-CB16_closeup; Check "OWLv2 (dev)"
        Write-Host "Open data/private/prelabels/previews and judge the boxes."
    }
    "prelabel-all" {
        Use-Ml
        python -m ml.detection.prelabel_owlv2 $Photos --out data/private/prelabels --threshold $Zs; Check "OWLv2 (all)"
    }
    "labelstudio" {
        if (-not (Test-Path ".venv-ls")) { py -$Py -m venv .venv-ls; . .\.venv-ls\Scripts\Activate.ps1; pip install label-studio; Check "Label Studio install" }
        else { . .\.venv-ls\Scripts\Activate.ps1 }
        $env:LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED = "true"
        $env:LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT = (Resolve-Path "data/private").Path
        Write-Host "Local files root: $env:LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT"
        Write-Host "Storage path to enter in Label Studio: $((Resolve-Path $Photos).Path)"
        label-studio start
    }
    "dataset" {
        Use-Ml
        if (-not (Test-Path "data/private/labels/ls_export.json")) { throw "Export from Label Studio (JSON) to data/private/labels/ls_export.json first." }
        python -m ml.detection.import_labels data/private/labels/ls_export.json --photos $Photos --out data/private/labels/company_coco.json; Check "import_labels"
        python -m ml.detection.build_dataset --labels data/private/labels/company_coco.json --photos $Photos --splits ml/detection/splits.yaml --public-map ml/detection/public_class_map.yaml --out $Data; Check "build_dataset"
    }
    "train" {
        # Trains on PUBLIC data only, so it doesn't need the company labels: run it while you label.
        Use-Ml
        python -m ml.detection.build_dataset --public-map ml/detection/public_class_map.yaml --out $Public; Check "build public dataset"
        python -m ml.detection.train_rfdetr --dataset $Public --out $Run; Check "training"
    }
    "dev" {
        Use-Ml
        python -m ml.detection.predict_all "$Data/dev_full" --weights $Weights --zero-shot --out runs/eval/dev; Check "predict (dev)"
        python -m ml.detection.evaluate --truth "$Data/dev_full" --pred-dir runs/eval/dev --out runs/eval/dev_metrics.json --threshold "detector=$Det" --threshold "zero_shot=$Zs"; Check "evaluate (dev)"
        Write-Host "Try other values: .\ml\detection\run.ps1 dev -Det 0.5 -Zs 0.2   (only re-scores is quicker: run evaluate directly)"
    }
    "test" {
        Use-Ml
        python -m ml.detection.predict_all "$Data/test_full" --weights $Weights --zero-shot --out runs/eval/test; Check "predict (test)"
        python -m ml.detection.evaluate --truth "$Data/test_full" --pred-dir runs/eval/test --out runs/eval/test_metrics.json --threshold "detector=$Det" --threshold "zero_shot=$Zs" --register-weights $Weights; Check "evaluate (test)"
    }
    default { throw "Unknown stage '$Stage'. See the list at the top of ml/detection/run.ps1." }
}
