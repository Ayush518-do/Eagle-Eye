import pytest
from backend.app.pipeline.fit_feasibility import (
    DEFAULT_CATALOG,
    ComponentSpec,
    assess_empty_position,
    evaluate_candidate_fit,
)


def test_default_catalog_has_required_standard_parts():
    assert "A9N2P16C" in DEFAULT_CATALOG
    assert "VE5127" in DEFAULT_CATALOG
    assert "3001501" in DEFAULT_CATALOG
    mcb = DEFAULT_CATALOG["A9N2P16C"]
    assert mcb.width_mm == 36.0
    assert mcb.mounting_type == "DIN-rail 35mm"
    assert mcb.pole_count == 2
    assert mcb.rated_current_a == 16.0


def test_evaluate_candidate_fit_identical_spec_is_compatible():
    mcb = DEFAULT_CATALOG["A9N2P16C"]
    result = evaluate_candidate_fit(
        expected_spec=mcb,
        candidate=mcb,
        available_width_mm=36.0,
        mounting_type="DIN-rail 35mm",
        has_image_calibration=True,
    )
    assert result.classification == "Compatible"
    assert result.evaluated_constraints["component_type"] == "PASS"
    assert result.evaluated_constraints["mounting"] == "PASS"
    assert "PASS" in result.evaluated_constraints["width"]
    assert "Physical fit does NOT imply electrical safety" in result.safety_disclaimer


def test_evaluate_candidate_fit_type_mismatch_is_incompatible():
    mcb = DEFAULT_CATALOG["A9N2P16C"]
    psu = DEFAULT_CATALOG["VE5127"]
    result = evaluate_candidate_fit(
        expected_spec=mcb,
        candidate=psu,
        available_width_mm=36.0,
    )
    assert result.classification == "Incompatible"
    assert result.evaluated_constraints["component_type"] == "FAIL"
    assert any("Component type mismatch" in r for r in result.reasons)


def test_evaluate_candidate_fit_width_exceeded_is_incompatible():
    mcb = DEFAULT_CATALOG["A9N2P16C"]
    result = evaluate_candidate_fit(
        expected_spec=mcb,
        candidate=mcb,
        available_width_mm=20.0,  # slot is only 20mm, mcb is 36mm
    )
    assert result.classification == "Incompatible"
    assert "FAIL" in result.evaluated_constraints["width"]
    assert any("exceeds available slot width" in r for r in result.reasons)


def test_evaluate_candidate_fit_mounting_mismatch_is_incompatible():
    mcb = DEFAULT_CATALOG["A9N2P16C"]
    result = evaluate_candidate_fit(
        expected_spec=mcb,
        candidate=mcb,
        mounting_type="G-rail",  # different rail
    )
    assert result.classification == "Incompatible"
    assert result.evaluated_constraints["mounting"] == "FAIL"


def test_evaluate_candidate_fit_uncalibrated_scale_is_potentially_compatible():
    mcb = DEFAULT_CATALOG["A9N2P16C"]
    result = evaluate_candidate_fit(
        expected_spec=mcb,
        candidate=mcb,
        has_image_calibration=False,
    )
    assert result.classification == "Potentially compatible"
    assert any("uncalibrated" in n for n in result.uncertainty_notes)


def test_evaluate_candidate_fit_current_difference_is_potential_and_flags_reason():
    mcb16 = DEFAULT_CATALOG["A9N2P16C"]
    mcb10 = DEFAULT_CATALOG["A9N2P10C"]
    result = evaluate_candidate_fit(
        expected_spec=mcb16,
        candidate=mcb10,
        available_width_mm=36.0,
        has_image_calibration=True,
    )
    assert result.classification == "Potentially compatible"
    assert any("Rated current differs" in r for r in result.reasons)


def test_assess_empty_position_reports_candidates_ordered():
    report = assess_empty_position(
        finding_id="F-MISS-01",
        tag="CB14",
        component_type="mcb",
        expected_part_number="A9N2P16C",
        image_flags=[],
    )
    assert report.tag == "CB14"
    assert report.slot_status == "unoccupied_verified"
    assert len(report.candidates) > 0
    # First candidate should be compatible or potentially compatible
    assert report.candidates[0].classification in ("Compatible", "Potentially compatible")
    assert report.candidates[0].candidate_part_number == "A9N2P16C"


def test_assess_empty_position_blurry_image_marks_slot_inconclusive():
    report = assess_empty_position(
        finding_id="F-MISS-02",
        tag="CB15",
        component_type="mcb",
        image_flags=["low_sharpness"],
    )
    assert report.slot_status == "unoccupied_inconclusive"
    assert any("low sharpness" in n for c in report.candidates for n in c.uncertainty_notes)
