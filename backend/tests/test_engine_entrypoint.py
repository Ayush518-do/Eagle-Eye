from backend.app.pipeline import engine
from backend.app.schemas import ExpectedItem, Observation


def _tag(text, confidence=0.95, source="ocr"):
    return Observation(
        observation_id="OBS-1",
        source=source,
        kind="tag_label",
        class_name="tag_label",
        bbox=[10, 10, 50, 30],
        text=text,
        text_confidence=confidence,
    )


def test_run_inspection_orchestrates_quality_comparison_and_gate(monkeypatch):
    calls = []
    expected = [ExpectedItem(tag="CB11")]
    observations = {"IMG-001": [_tag("CB11")]}
    source_findings = [object()]

    def fake_check_photo(path, thresholds):
        calls.append(("photo", path, thresholds))
        return ["low_sharpness"]

    def fake_compare(items, by_image, min_text_confidence):
        calls.append(("compare", items, by_image, min_text_confidence))
        return source_findings

    def fake_gate(findings, flags, thresholds):
        calls.append(("gate", findings, flags, thresholds))
        return findings

    monkeypatch.setattr(engine, "check_photo", fake_check_photo)
    monkeypatch.setattr(engine, "compare", fake_compare)
    monkeypatch.setattr(engine, "apply_confidence_gate", fake_gate)

    result_findings, image_flags = engine.run_inspection(
        expected,
        observations,
        {"IMG-001": "cabinet.jpg"},
        {"min_text_confidence": 0.72},
    )

    assert result_findings is source_findings
    assert image_flags == {"IMG-001": ["low_sharpness"]}
    resolved_thresholds = {
        "min_text_confidence": 0.72,
        "min_detector_confidence": 0.5,
        "min_photo_width": 1600.0,
        "min_sharpness": 100.0,
        "max_overexposed_fraction": 0.15,
    }
    assert calls == [
        ("photo", "cabinet.jpg", resolved_thresholds),
        ("compare", expected, observations, 0.72),
        ("gate", source_findings, image_flags, resolved_thresholds),
    ]


def test_unseen_expected_item_remains_inconclusive(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    findings, flags = engine.run_inspection(
        [ExpectedItem(tag="PS11")],
        {"IMG-001": []},
        {"IMG-001": "cabinet.jpg"},
    )

    assert flags == {"IMG-001": []}
    assert len(findings) == 1
    assert findings[0].status == "inconclusive"
    assert "Not proof" in findings[0].reason


def test_run_inspection_preserves_synthetic_observation_rejection():
    import pytest

    with pytest.raises(ValueError, match="Synthetic observations"):
        engine.run_inspection(
            [ExpectedItem(tag="CB11")],
            {"IMG-001": [_tag("CB11", source="synthetic")]},
            {},
        )
