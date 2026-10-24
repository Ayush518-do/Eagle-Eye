"""Pydantic models for the hand-over formats in docs/contracts.md.

Contract A: drawing -> expected items.   Contract B: photo -> observations.
Contract C: backend -> frontend inspection result.
If you change a model here, update docs/contracts.md in the same pull request.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "0.2"

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


class Layout(BaseModel):
    """Where the tag sits on the drawing's general-arrangement page (Contract A, used by the ghost overlay)."""

    page: int = Field(ge=1)
    view: Optional[str] = None
    bbox: BBox  # [x1, y1, x2, y2] in PDF points on `page`
    anchor: Optional[Literal["component", "callout"]] = None
    _bbox = field_validator("bbox")(_check_bbox)


class ExpectedItem(BaseModel):
    tag: str
    part_number: Optional[str] = None
    description: Optional[str] = None
    quantity: int = 1
    rating: Optional[Rating] = None
    source_page: Optional[int] = None
    layout: Optional[Layout] = None


class DrawingParseResult(BaseModel):
    contract_version: str = CONTRACT_VERSION
    drawing_file_sha256: Optional[str] = None
    parser_version: str
    items: list[ExpectedItem]


class ExpectedItemsSubmission(BaseModel):
    """Request body for storing expected items. Accepts every valid `DrawingParseResult`;
    a hand-typed list may also leave out `parser_version`. `contract_version` is accepted as
    any string here and checked by the service, so an unsupported one is a 400, not a 422."""

    contract_version: str = CONTRACT_VERSION
    drawing_file_sha256: Optional[str] = None
    parser_version: Optional[str] = None
    items: list[ExpectedItem]


# ---------- Contract B ----------
class ModelInfo(BaseModel):
    name: str
    version: Optional[str] = None
    weights_sha256: Optional[str] = None


class Observation(BaseModel):
    observation_id: str
    source: Literal["detector", "ocr", "manual", "synthetic"]
    kind: Literal["component", "tag_label", "rating"]
    class_name: str
    bbox: BBox
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    text: Optional[str] = None
    raw_text: Optional[str] = None
    text_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    model: Optional[ModelInfo] = None

    _bbox = field_validator("bbox")(_check_bbox)

    @model_validator(mode="after")
    def _validate_rating_observation(self):
        if self.kind == "rating":
            if self.source != "ocr":
                raise ValueError("rating observations must have source='ocr'")
            if self.class_name != "rating":
                raise ValueError("rating observations must have class_name='rating'")
            if self.text is not None:
                raise ValueError("rating observations must leave text unset")
            if self.raw_text is None or not self.raw_text.strip():
                raise ValueError("rating observations require non-empty raw_text")
        return self


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
    # When a per-image alignment is set and the item's layout places it on that drawing page,
    # the ghost overlay provides the projected box in photo pixels. Only set for `missing` findings.
    expected_bbox: Optional[BBox] = None
    # Evidence-weighted confidence for this finding, in [0, 1]. Derived from OCR text confidence,
    # detector confidence, number of agreeing sources and number of distinct images that support it.
    # Not a hard threshold: for a `verified` finding it indicates how sure we are; for a `missing`
    # finding it indicates how sure we are that the component is really absent (vs just unseen).
    evidence_score: Optional[float] = Field(default=None, ge=0, le=1)
    # Short list of source labels contributing to the score, e.g. ["ocr", "detector"].
    sources: list[str] = []


class GhostBox(BaseModel):
    tag: Optional[str] = None
    bbox: BBox
    status: str


class ImageInfo(BaseModel):
    image_id: str
    url: str
    width: int
    height: int
    quality_flags: list[str] = []
    alignment_set: bool = False
    ghost: list[GhostBox] = []
    # True when this image is the cabinet's approved baseline / reference photo.
    is_reference: bool = False


class AlignmentIn(BaseModel):
    drawing_page: int = Field(ge=1)
    drawing_points: list[list[float]]
    photo_points: list[list[float]]


class AlignmentOut(BaseModel):
    image_id: str
    drawing_page: int
    drawing_points: list[list[float]]
    photo_points: list[list[float]]
    created_at: datetime
    updated_at: datetime


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


# ---------- API requests and responses ----------
# NOT in docs/contracts.md yet. docs/team/backend.md names these endpoints but gives no body or
# response shapes for them; the fields below are taken from the doc's examples and from what
# frontend/src/api.js already reads (`cabinet_id`). They are proposals pending team review.
InspectionState = Literal["queued", "running", "done", "failed"]


class CabinetCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    # Used in URLs, so no slashes or spaces.
    cabinet_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=200)


class CabinetOut(BaseModel):
    cabinet_id: str
    name: str
    created_at: datetime


class CabinetSummary(CabinetOut):
    latest_inspection_id: Optional[str] = None
    latest_inspection_state: Optional[InspectionState] = None
    latest_overall_status: Optional[OverallStatus] = None  # current status; null until a run is done


class DesignRevisionOut(BaseModel):
    design_revision_id: str
    cabinet_id: str
    label: str
    drawing_sha256: str
    parser_version: Optional[str] = None
    created_at: datetime


class CabinetDetail(CabinetOut):
    design_revisions: list[DesignRevisionOut]


class InspectionAccepted(BaseModel):
    inspection_id: str
    state: InspectionState


class InspectionDetail(InspectionResult):
    """Contract C plus `state` and `error`. `overall_status` is null until the run is done."""

    overall_status: Optional[OverallStatus] = None
    # `design_revision_id` carries the display label as in Contract C; this is the internal id
    # (the one used in URLs and in the create-inspection form).
    design_revision_internal_id: Optional[str] = None
    previous_inspection_id: Optional[str] = None  # set on a reinspection
    state: InspectionState
    error: Optional[str] = None


class ReviewEventOut(BaseModel):
    finding_id: str
    decision: Literal["confirmed_by_reviewer", "rejected_by_reviewer"]
    reviewer: str
    note: str
    created_at: datetime


class ReinspectionAccepted(InspectionAccepted):
    previous_inspection_id: str


class PassportImage(BaseModel):
    image_id: str
    sha256: str
    width: int
    height: int
    quality_flags: list[str]


class PassportFinding(BaseModel):
    finding_id: str
    type: str
    tag: Optional[str] = None
    original_status: str  # what the engine reported; never changes
    current_status: str  # after the latest review event, if any
    reason: Optional[str] = None


class PassportInspection(BaseModel):
    inspection_id: str
    state: InspectionState
    error: Optional[str] = None
    created_at: datetime
    design_revision_id: str  # display label, as in Contract C
    design_revision_internal_id: str
    previous_inspection_id: Optional[str] = None
    overall_status: Optional[OverallStatus] = None  # current; null unless the run is done
    engine_overall_status: Optional[str] = None  # as stored when the run finished
    images: list[PassportImage]
    findings: list[PassportFinding]
    review_events: list[ReviewEventOut]  # oldest first


class QualityPassport(BaseModel):
    cabinet_id: str
    name: str
    inspections: list[PassportInspection]  # oldest first; [] when there are none


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
