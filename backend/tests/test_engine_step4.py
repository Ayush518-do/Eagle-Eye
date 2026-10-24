import pytest

from backend.app.pipeline import engine
from backend.app.schemas import ExpectedItem, Finding, Observation, Rating


def _observation(text, image_id, raw_text=None, confidence=0.95):
    return Observation(
        observation_id=f"OBS-{image_id}",
        source="ocr",
        kind="tag_label",
        class_name="tag_label",
        bbox=[10, 10, 50, 30],
        text=text,
        raw_text=raw_text,
        text_confidence=confidence,
    )


@pytest.mark.parametrize(
    "confidence, expected_status",
    [
        (0.79, "needs_review"),
        (0.80, "potential_mismatch"),
        (0.81, "potential_mismatch"),
        (None, "needs_review"),
    ],
)
def test_potential_mismatch_confidence_boundary(confidence, expected_status):
    finding = Finding(
        finding_id="F-001",
        type="rating_mismatch",
        tag="CB11",
        status="potential_mismatch",
        ocr_confidence=confidence,
    )

    [gated] = engine.apply_confidence_gate([finding], {}, {
        "min_text_confidence": 0.8,
    })

    assert gated.status == expected_status
    if expected_status == "needs_review":
        assert gated.reason == "Potential mismatch read with low confidence."


def test_rating_marked_needs_review_is_explicitly_skipped(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    finding, = engine.run_inspection(
        [ExpectedItem(tag="PS11", rating=Rating(value=None, needs_review=True))],
        {"IMG-001": [_observation("PS11", "IMG-001")]},
        {"IMG-001": "unused.jpg"},
    )[0]

    assert finding.status == "verified"
    assert finding.reason == "Rating check skipped because the expected rating needs review."


def test_conflicting_raw_readings_across_photos_need_review(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    findings, _ = engine.run_inspection(
        [ExpectedItem(tag="CB11")],
        {
            "IMG-001": [_observation("CB11", "IMG-001", raw_text="CB11")],
            "IMG-002": [_observation("CB11", "IMG-002", raw_text="CB1I")],
        },
        {"IMG-001": "one.jpg", "IMG-002": "two.jpg"},
    )

    assert findings[0].status == "needs_review"
    assert '"CB11"' in findings[0].reason
    assert '"CB1I"' in findings[0].reason


def test_same_reading_across_photos_stays_verified(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    findings, _ = engine.run_inspection(
        [ExpectedItem(tag="CB11")],
        {
            "IMG-001": [_observation("CB11", "IMG-001", raw_text="CB11")],
            "IMG-002": [_observation("CB11", "IMG-002", raw_text="CB11")],
        },
        {"IMG-001": "one.jpg", "IMG-002": "two.jpg"},
    )

    assert findings[0].status == "verified"
    assert findings[0].reason is None

def test_formatting_variation_is_not_a_conflicting_reading(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    findings, _ = engine.run_inspection(
        [ExpectedItem(tag="CB11")],
        {
            "IMG-001": [_observation("CB11", "IMG-001", raw_text="CB11")],
            "IMG-002": [_observation("CB11", "IMG-002", raw_text="CB-11")],
        },
        {"IMG-001": "one.jpg", "IMG-002": "two.jpg"},
    )

    assert findings[0].status == "verified"
    assert findings[0].reason is None
