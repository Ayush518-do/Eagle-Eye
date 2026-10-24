"""API routes under /api. Planned endpoints are listed in docs/api-contract.md."""
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.app import __version__
from backend.app.config import Settings, get_settings
from backend.app.schemas import ModelStatus, UploadResult
from backend.app.services.storage import UploadRejected, save_upload

router = APIRouter(prefix="/api")


@router.get("/health", tags=["system"])
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "eagle-eye-api", "version": __version__}


@router.get("/model/status", response_model=list[ModelStatus], tags=["system"])
def model_status(settings: Settings = Depends(get_settings)) -> list[ModelStatus]:
    """Say honestly which models can run. Does not load the models."""
    weights = settings.detector_weights_path
    if not weights:
        det = ModelStatus(component="detector", available=False,
                          detail="DETECTOR_WEIGHTS_PATH is not set.")
    elif not os.path.isfile(weights):
        det = ModelStatus(component="detector", available=False,
                          detail=f"Weights file not found: {weights}")
    else:
        det = ModelStatus(component="detector", available=True,
                          detail=f"{settings.detector_model_name or 'detector'} weights found.")

    try:
        import rapidocr_onnxruntime  # noqa: F401
        ocr = ModelStatus(component="ocr", available=True, detail="RapidOCR installed.")
    except ImportError:
        ocr = ModelStatus(component="ocr", available=False,
                          detail="RapidOCR not installed (pip install -r ml/requirements-ocr.txt).")
    return [det, ocr]


@router.post("/uploads", response_model=UploadResult, status_code=201, tags=["files"])
async def upload_file(
    file: UploadFile = File(...), settings: Settings = Depends(get_settings)
) -> UploadResult:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)  # read one byte past the limit to detect oversize
    try:
        meta = save_upload(data, file.filename or "upload", settings.upload_dir, settings.max_upload_mb)
    except UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UploadResult(**meta)
