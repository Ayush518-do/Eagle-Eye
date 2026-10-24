from datetime import datetime

import pytest
from sqlalchemy import delete, select, update

from backend.app.ids import new_id
from backend.app.models import (
    AppendOnlyError, Cabinet, DesignRevision, Finding, Image, Inspection, Observation, ReviewEvent,
)
from backend.app.schemas import InspectionResult


def seed_finding(s) -> Finding:
    s.add(Cabinet(id="CAB-001", name="Line 3 panel"))
    s.add(DesignRevision(id="D1", cabinet_id="CAB-001", label="REV-A", drawing_file_id="f",
                         drawing_sha256="0" * 64))
    s.flush()
    ins = Inspection(cabinet_id="CAB-001", design_revision_id="D1")
    s.add(ins)
    s.flush()
    finding = Finding(inspection_id=ins.id, type="rating_mismatch", tag="CB11", status="needs_review",
                      evidence=[{"image_id": "IMG-1", "bbox": [1, 2, 3, 4]}])
    s.add(finding)
    s.commit()
    return finding


def test_ids_have_documented_prefixes_and_are_unique():
    ids = {new_id("INS") for _ in range(2000)}
    assert len(ids) == 2000
    assert all(i.startswith("INS-") and len(i) == 16 for i in ids)


def test_defaults_and_display_label_is_separate_from_id(session_factory):
    with session_factory() as s:
        f = seed_finding(s)
        ins = s.get(Inspection, f.inspection_id)
        rev = s.get(DesignRevision, "D1")
        assert ins.id.startswith("INS-") and f.id.startswith("F-")
        assert ins.state == "queued" and ins.overall_status is None and ins.error is None
        assert rev.label == "REV-A" and rev.id != rev.label


def test_new_design_revision_gets_a_generated_id_distinct_from_its_label(session_factory):
    with session_factory() as s:
        s.add(Cabinet(id="CAB-001", name="x"))
        rev = DesignRevision(cabinet_id="CAB-001", label="REV-A", drawing_file_id="f", drawing_sha256="0" * 64)
        s.add(rev)
        s.commit()
        assert rev.id.startswith("DREV-") and rev.id != "REV-A"


def test_datetimes_come_back_timezone_aware_and_serialize_with_offset(session_factory):
    with session_factory() as s:
        f = seed_finding(s)
    with session_factory() as s:
        ins = s.get(Inspection, f.inspection_id)
        assert ins.created_at.utcoffset().total_seconds() == 0
        dumped = InspectionResult(
            inspection_id=ins.id, cabinet_id=ins.cabinet_id, created_at=ins.created_at,
            overall_status="review_required", images=[], findings=[], counts={},
        ).model_dump_json()
        assert '"created_at":"' in dumped and ("Z" in dumped or "+00:00" in dumped)


def test_naive_datetime_is_refused(session_factory):
    with session_factory() as s:
        s.add(Cabinet(id="CAB-X", name="x", created_at=datetime(2026, 1, 1)))
        with pytest.raises(Exception, match="Naive datetime"):
            s.commit()


def test_json_and_optional_columns_round_trip(session_factory):
    with session_factory() as s:
        f = seed_finding(s)
        img = Image(inspection_id=f.inspection_id, file_id="abc", sha256="1" * 64, width=4096, height=3072,
                    quality_flags=["low_sharpness"])
        s.add(img)
        s.flush()
        s.add(Observation(image_id=img.id, observation_id="OBS-001", source="manual", kind="tag_label",
                          class_name="tag_label", bbox=[1210, 790, 1280, 822], text="CB11"))
        s.commit()
    with session_factory() as s:
        obs = s.scalars(select(Observation)).one()
        assert obs.bbox == [1210, 790, 1280, 822]
        assert obs.confidence is None and obs.model is None and obs.raw_text is None
        assert s.scalars(select(Image)).one().quality_flags == ["low_sharpness"]
        assert s.scalars(select(Finding)).one().evidence == [{"image_id": "IMG-1", "bbox": [1, 2, 3, 4]}]


# ---------- append-only safeguards ----------
def test_review_events_accumulate_and_keep_order(session_factory):
    with session_factory() as s:
        f = seed_finding(s)
        s.add(ReviewEvent(finding_id=f.id, decision="confirmed_by_reviewer", reviewer="A"))
        s.commit()
        s.add(ReviewEvent(finding_id=f.id, decision="rejected_by_reviewer", reviewer="B", note="mistake"))
        s.commit()
        events = s.scalars(select(ReviewEvent).order_by(ReviewEvent.id)).all()
        assert [e.decision for e in events] == ["confirmed_by_reviewer", "rejected_by_reviewer"]


@pytest.fixture
def with_event(session_factory):
    with session_factory() as s:
        f = seed_finding(s)
        s.add(ReviewEvent(finding_id=f.id, decision="confirmed_by_reviewer", reviewer="A", note="n"))
        s.commit()
    return session_factory


def test_orm_update_of_a_finding_is_refused_and_row_is_unchanged(with_event):
    with with_event() as s:
        s.scalars(select(Finding)).one().status = "verified"
        with pytest.raises(AppendOnlyError):
            s.commit()
    with with_event() as s:
        assert s.scalars(select(Finding)).one().status == "needs_review"


def test_orm_update_of_a_review_event_is_refused_and_row_is_unchanged(with_event):
    with with_event() as s:
        s.scalars(select(ReviewEvent)).one().note = "rewritten"
        with pytest.raises(AppendOnlyError):
            s.commit()
    with with_event() as s:
        assert s.scalars(select(ReviewEvent)).one().note == "n"


@pytest.mark.parametrize("model", [Finding, ReviewEvent])
def test_orm_delete_is_refused(with_event, model):
    with with_event() as s:
        s.delete(s.scalars(select(model)).one())
        with pytest.raises(AppendOnlyError):
            s.commit()
    with with_event() as s:
        assert len(s.scalars(select(model)).all()) == 1


@pytest.mark.parametrize("model, values", [(Finding, {"status": "verified"}), (ReviewEvent, {"note": "x"})])
def test_bulk_update_and_delete_are_refused(with_event, model, values):
    with with_event() as s:
        with pytest.raises(AppendOnlyError):
            s.execute(update(model).values(**values))
        with pytest.raises(AppendOnlyError):
            s.execute(delete(model))
    with with_event() as s:
        assert len(s.scalars(select(model)).all()) == 1


def test_other_tables_are_not_blocked(with_event):
    """The guard covers history only: an inspection can still move from queued to running."""
    with with_event() as s:
        ins = s.scalars(select(Inspection)).one()
        ins.state = "running"
        s.commit()
        assert s.scalars(select(Inspection)).one().state == "running"
