"""Pydantic models for the hand-over formats in docs/contracts.md.

Contract A: drawing -> expected items.   Contract B: photo -> observations.
Contract C: backend -> frontend inspection result.
If you change a model here, update docs/contracts.md in the same pull request.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

CONTRACT_VERSION = "0.1"

BBox = list[float]  # [x_min, y_min, x_max, y_max] in original-image pixels


def _check_bbox(v: Optional[BBox]) -> Optional[BBox]:
    if v is None:
        return v
    if len(v) != 4:
        raise ValueError("bbox must have 4 numbers: [x_min, y_min, x_max, y_max]")
    x1, y1, x2, y2 = v
    if x2 <= x1 or y2 <= y1:
        raise ValueError("bbox must have x_max > x_min and y_max > y_min")
    return v


# ---------- Contract A ----------
class Rating(BaseModel):
    value: Optional[str] = None
    source: str = "schematic"
    page: Optional[int] = None
    needs_review: bool = False


class ExpectedItem(BaseModel):
    tag: str
    part_number: Optional[str] = None
    description: Optional[str] = None
    quantity: int = 1
    rating: Optional[Rating] = None
    source_page: Optional[int] = None


class DrawingParseResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    drawing_file_sha256: Optional[str] = None
    parser_version: str
    items: list[ExpectedItem]


# ---------- Contract B ----------
class ModelInfo(BaseModel):
    name: str
    version: Optional[str] = None
    weights_sha256: Optional[str] = None


class Observation(BaseModel):
    observation_id: str
    source: Literal["detector", "ocr", "manual", "synthetic"]
    kind: Literal["component", "tag_label"]
    class_name: str
    bbox: BBox
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    text: Optional[str] = None
    raw_text: Optional[str] = None
    text_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    model: Optional[ModelInfo] = None

    _bbox = field_validator("bbox")(_check_bbox)


class ImageObservations(BaseModel):
    contract_version: str = CONTRACT_VERSION
    image_id: str
    image_sha256: Optional[str] = None
    image_size: tuple[int, int]
    observations: list[Observation]


# ---------- Contract C ----------
FindingType = Literal["missing", "unexpected", "rating_mismatch", "misplaced", "verified"]
FindingStatus = Literal[
    "verified",
    "potential_mismatch",
    "needs_review",
    "inconclusive",
    "confirmed_by_reviewer",
    "rejected_by_reviewer",
    "resolved_after_reinspection",
]
OverallStatus = Literal["pass", "review_required", "mismatch_detected"]


class Evidence(BaseModel):
    image_id: str
    bbox: BBox
    _bbox = field_validator("bbox")(_check_bbox)


class Finding(BaseModel):
    finding_id: str
    type: FindingType
    tag: Optional[str] = None
    expected_value: Optional[str] = None
    observed_text: Optional[str] = None
    detector_confidence: Optional[float] = None
    ocr_confidence: Optional[float] = None
    status: FindingStatus
    reason: Optional[str] = None
    evidence: list[Evidence] = []


class ImageInfo(BaseModel):
    image_id: str
    url: str
    width: int
    height: int
    quality_flags: list[str] = []


class InspectionResult(BaseModel):
    inspection_id: str
    cabinet_id: str
    design_revision_id: Optional[str] = None
    created_at: datetime
    overall_status: OverallStatus
    images: list[ImageInfo]
    findings: list[Finding]
    counts: dict[str, int]


class ReviewDecision(BaseModel):
    decision: Literal["confirmed_by_reviewer", "rejected_by_reviewer"]
    reviewer: str = Field(min_length=1)
    note: str = ""


# ---------- System ----------
class ModelStatus(BaseModel):
    component: str
    available: bool
    detail: str


class UploadResult(BaseModel):
    file_id: str
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
