"""Database tables, as listed in docs/team/backend.md (Step 1).

Rules encoded here:
- `findings` holds the engine's original output and `review_events` holds reviewer decisions.
  Neither is ever updated or deleted (see the guards at the bottom). A finding's current
  status is derived from its original status plus the latest review event.
- Vocabulary that is still under team discussion (`overall_status`, finding `type` and
  `status`) is not enforced by a database constraint; the Pydantic schemas validate it.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.types import TypeDecorator

from backend.app.ids import new_id


class UTCDateTime(TypeDecorator):
    """Stores UTC, returns timezone-aware UTC. SQLite alone would drop the timezone."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime refused; use timezone-aware UTC datetimes.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        return None if value is None else value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Cabinet(Base):
    __tablename__ = "cabinets"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # supplied by the client, e.g. CAB-001
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class DesignRevision(Base):
    __tablename__ = "design_revisions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("DREV"))
    cabinet_id: Mapped[str] = mapped_column(ForeignKey("cabinets.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))  # display label, e.g. REV-A
    drawing_file_id: Mapped[str] = mapped_column(String(64))
    drawing_sha256: Mapped[str] = mapped_column(String(64))  # SHA-256 of the PDF bytes
    # Contract A `parser_version`; null when the items were typed by hand.
    parser_version: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ExpectedItem(Base):
    __tablename__ = "expected_items"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("ITEM"))
    design_revision_id: Mapped[str] = mapped_column(ForeignKey("design_revisions.id"), index=True)
    tag: Mapped[str] = mapped_column(String(100))
    part_number: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    rating_value: Mapped[Optional[str]] = mapped_column(String(100))
    rating_needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    # Contract A `rating` metadata. A rating object exists when rating_source is set.
    rating_source: Mapped[Optional[str]] = mapped_column(String(50))
    rating_page: Mapped[Optional[int]] = mapped_column(Integer)
    source_page: Mapped[Optional[int]] = mapped_column(Integer)
    # Contract A `layout`: where the tag sits on the drawing's general-arrangement page.
    # Nullable because hand-typed items and older parsers may not include it. Shape:
    # {"page": int, "view": str|null, "bbox": [x1,y1,x2,y2] in PDF points, "anchor": "component"|"callout"|null}
    layout: Mapped[Optional[dict]] = mapped_column(JSON)


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="ck_inspections_state"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("INS"))
    cabinet_id: Mapped[str] = mapped_column(ForeignKey("cabinets.id"), index=True)
    design_revision_id: Mapped[str] = mapped_column(ForeignKey("design_revisions.id"), index=True)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[Optional[str]] = mapped_column(Text)
    # Engine-time outcome; null until a run has produced a result. Not constrained here.
    overall_status: Mapped[Optional[str]] = mapped_column(String(40))
    previous_inspection_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("inspections.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("IMG"))
    inspection_id: Mapped[str] = mapped_column(ForeignKey("inspections.id"), index=True)
    file_id: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    quality_flags: Mapped[list[str]] = mapped_column(JSON, default=list)


class ImageAlignment(Base):
    """Per-image 4-point homography between the drawing and the photo (Contract E).

    One row per image at most. `drawing_points` are in PDF points on `drawing_page`; `photo_points`
    are in original-photo pixels. Points are listed TL, TR, BR, BL. See docs/contracts.md section E.
    """

    __tablename__ = "image_alignments"

    image_id: Mapped[str] = mapped_column(ForeignKey("images.id"), primary_key=True)
    drawing_page: Mapped[int] = mapped_column(Integer)
    drawing_points: Mapped[list[list[float]]] = mapped_column(JSON)
    photo_points: Mapped[list[list[float]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        # Contract B ids (OBS-001, OCR-001, ...) are only unique within one image.
        UniqueConstraint("image_id", "observation_id", name="uq_observations_image_observation"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("OBS"))
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id"), index=True)
    # The id the producer gave this observation (Contract B `observation_id`), kept as sent.
    observation_id: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))
    class_name: Mapped[str] = mapped_column(String(100))
    bbox: Mapped[list[float]] = mapped_column(JSON)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    text: Mapped[Optional[str]] = mapped_column(Text)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    text_confidence: Mapped[Optional[float]] = mapped_column(Float)
    model: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)


class Finding(Base):
    """Original engine output. Written once, never changed."""

    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("F"))
    inspection_id: Mapped[str] = mapped_column(ForeignKey("inspections.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    tag: Mapped[Optional[str]] = mapped_column(String(100))
    expected_value: Mapped[Optional[str]] = mapped_column(Text)
    observed_text: Mapped[Optional[str]] = mapped_column(Text)
    detector_confidence: Mapped[Optional[float]] = mapped_column(Float)
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40))  # the engine's status, not the current one
    reason: Mapped[Optional[str]] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ReviewEvent(Base):
    """One reviewer decision. Append-only: a correction is a new row."""

    __tablename__ = "review_events"

    # Internal integer key, used only to order events that share a timestamp.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), index=True)
    decision: Mapped[str] = mapped_column(String(40))
    reviewer: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


# ---------- Append-only guards ----------
# These stop the application from changing history through the ORM, including bulk
# Query.update()/delete(). They cannot stop raw SQL or a hand-written Core statement;
# only a database trigger would. See the Stage 1 report for that proposal.
APPEND_ONLY_MODELS = (Finding, ReviewEvent)


class AppendOnlyError(RuntimeError):
    """Raised on any attempt to update or delete an append-only record."""


def _refuse(mapper, connection, target) -> None:
    raise AppendOnlyError(
        f"{type(target).__name__} records are append-only and cannot be updated or deleted."
    )


for _model in APPEND_ONLY_MODELS:
    event.listen(_model, "before_update", _refuse)
    event.listen(_model, "before_delete", _refuse)


@event.listens_for(Session, "do_orm_execute")
def _refuse_bulk_changes(state) -> None:
    if state.is_update or state.is_delete:
        for mapper in state.all_mappers:
            if mapper.class_ in APPEND_ONLY_MODELS:
                raise AppendOnlyError(
                    f"{mapper.class_.__name__} records are append-only and cannot be updated or deleted."
                )
