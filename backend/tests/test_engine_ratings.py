import pytest
from pydantic import ValidationError

from PIL import Image

from backend.app.pipeline.ratings import (
    RatingCandidate,
    attest_rating_distance_threshold,
    associate_rating_candidates,
    compare_rating_candidates,
    normalise_rating,
    normalized_center_distance,
    read_image_dimensions,
)
from backend.app.schemas import CONTRACT_VERSION, ExpectedItem, ImageObservations, Observation, Rating


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10 A", ("A", 10.0)),
        ("10A", ("A", 10.0)),
        ("C10", ("A", 10.0)),
        ("24VDC", ("V", 24.0)),
        ("16 A", ("A", 16.0)),
    ],
)
def test_normalise_documented_rating_formats(text, expected):
    assert normalise_rating(text) == expected


@pytest.mark.parametrize(
    "text",
    [None, "", "CB11", "10mA", "D10", "24VAC", "1.5A", "10 A ", " 10 A"],
)
def test_normalise_rating_rejects_unapproved_or_malformed_formats(text):
    assert normalise_rating(text) is None


def _rating_observation(**overrides):
    data = {
        "observation_id": "OBS-RATING-1",
        "source": "ocr",
        "kind": "rating",
        "class_name": "rating",
        "bbox": [1210, 830, 1280, 862],
        "text": None,
        "raw_text": "16 A",
        "text_confidence": 0.94,
    }
    data.update(overrides)
    return data


def test_rating_observation_round_trips_with_bumped_contract_version():
    payload = ImageObservations(
        image_id="IMG-001",
        image_size=(4096, 3072),
        observations=[Observation(**_rating_observation())],
    ).model_dump(mode="json")

    assert CONTRACT_VERSION == "0.2"
    assert payload["contract_version"] == "0.2"
    restored = ImageObservations.model_validate(payload)
    observation = restored.observations[0]
    assert observation.kind == "rating"
    assert observation.raw_text == "16 A"
    assert observation.bbox == [1210.0, 830.0, 1280.0, 862.0]


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "manual"},
        {"class_name": "tag_label"},
        {"raw_text": None},
        {"raw_text": "  "},
        {"text": "CB11"},
    ],
)
def test_rating_observation_requires_explicit_ocr_shape(changes):
    with pytest.raises(ValidationError):
        Observation(**_rating_observation(**changes))


def _tag_observation(tag, bbox, observation_id="OBS-TAG"):
    return Observation(
        observation_id=observation_id,
        source="ocr",
        kind="tag_label",
        class_name="tag_label",
        bbox=bbox,
        text=tag,
        raw_text=tag,
        text_confidence=0.96,
    )


def _rating_obs(text, bbox, confidence=0.95, observation_id="OBS-RATING"):
    return Observation(
        observation_id=observation_id,
        source="ocr",
        kind="rating",
        class_name="rating",
        bbox=bbox,
        text=None,
        raw_text=text,
        text_confidence=confidence,
    )


def _expected(tag="CB11", value="10 A", needs_review=False):
    return ExpectedItem(
        tag=tag,
        rating=Rating(value=value, needs_review=needs_review) if value is not None else None,
    )


@pytest.fixture
def test_threshold_attestation():
    """Explicit test-only caller attestation; not operational calibration."""
    return attest_rating_distance_threshold(
        0.25,
        attestation_reference="test-only fixture, not operational calibration",
    )


def _candidate(tag, text, bbox=(1, 1, 5, 5), confidence=0.95, distance=0.01, ambiguous=False):
    return RatingCandidate(
        tag=tag,
        image_id="IMG-1",
        observation=_rating_obs(text, bbox, confidence),
        distance_fraction=distance,
        ambiguous=ambiguous,
    )


def test_read_image_dimensions_returns_sizes_and_none_for_unreadable_paths(tmp_path):
    image_path = tmp_path / "photo.png"
    Image.new("RGB", (640, 480), "white").save(image_path)

    result = read_image_dimensions({
        "IMG-OK": image_path,
        "IMG-MISSING": tmp_path / "missing.png",
    })

    assert result == {"IMG-OK": (640, 480), "IMG-MISSING": None}


@pytest.mark.parametrize("image_size", [(100, 100), (1000, 1000), (4096, 3072)])
def test_normalized_center_distance_is_scale_invariant(image_size):
    width, height = image_size
    first = [width * 0.1, height * 0.1, width * 0.2, height * 0.2]
    second = [width * 0.3, height * 0.3, width * 0.4, height * 0.4]

    distance = normalized_center_distance(first, second, image_size)

    assert distance == pytest.approx(0.2)


def test_normalized_center_distance_rejects_unavailable_dimensions():
    assert normalized_center_distance([0, 0, 1, 1], [1, 1, 2, 2], (0, 100)) is None
    assert normalized_center_distance([0, 0, 1], [1, 1, 2, 2], (100, 100)) is None


def test_rating_candidate_uses_normalized_expected_tag_and_no_default_threshold():
    observations = {
        "IMG-1": [
            _tag_observation("cb-11", [10, 10, 30, 30]),
            _rating_obs("16 A", [40, 10, 60, 30]),
        ]
    }

    candidates = associate_rating_candidates(
        [_expected("CB11")], observations, {"IMG-1": (100, 100)}
    )

    assert len(candidates) == 1
    assert candidates[0].tag == "CB11"
    assert compare_rating_candidates(_expected(), candidates, "F-R1", 0.80).finding is None


def test_rating_candidate_requires_image_dimensions_and_only_uses_expected_tag_labels():
    observations = {
        "IMG-1": [
            _tag_observation("cb-11", [40, 10, 60, 30]),
            _tag_observation("CB12", [80, 80, 90, 90], "OBS-TAG-2"),
            _rating_obs("16 A", [45, 10, 55, 20]),
        ]
    }

    assert associate_rating_candidates([_expected()], observations, {"IMG-1": None}) == []
    candidates = associate_rating_candidates([_expected()], observations, {"IMG-1": (100, 100)})
    assert len(candidates) == 1
    assert candidates[0].tag == "CB11"
    assert candidates[0].distance_fraction == pytest.approx(5 / (2 * (2**0.5) * 50))


def test_run_inspection_keeps_rating_findings_disabled_without_calibrated_threshold(monkeypatch):
    from backend.app.pipeline import engine

    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    findings, _ = engine.run_inspection(
        [_expected()],
        {
            "IMG-1": [
                _tag_observation("CB11", [40, 10, 60, 30]),
                _rating_obs("16 A", [45, 10, 55, 20]),
            ]
        },
        {"IMG-1": "provided-only-for-quality-check"},
    )

    assert len(findings) == 1
    assert findings[0].type == "verified"
    assert findings[0].status == "verified"


def test_equal_distance_expected_tags_are_marked_ambiguous(test_threshold_attestation):
    observations = {
        "IMG-1": [
            _tag_observation("CB11", [10, 40, 20, 50]),
            _tag_observation("CB12", [80, 40, 90, 50], "OBS-TAG-2"),
            _rating_obs("16 A", [45, 40, 55, 50]),
        ]
    }
    candidates = associate_rating_candidates(
        [_expected("CB11"), _expected("CB12")],
        observations,
        {"IMG-1": (100, 100)},
    )

    assert {candidate.tag for candidate in candidates} == {"CB11", "CB12"}
    assert all(candidate.ambiguous for candidate in candidates)
    assert candidates[0].distance_fraction == candidates[1].distance_fraction
    assert all(candidate.distance_fraction <= test_threshold_attestation.value for candidate in candidates)
    assert all(
        compare_rating_candidates(
            _expected(candidate.tag), [candidate], "F-R1", 0.8,
            attested_threshold=test_threshold_attestation,
        ).finding is None
        for candidate in candidates
    )
    assert all(
        compare_rating_candidates(
            _expected(candidate.tag), [candidate], "F-R2", 0.8,
            attested_threshold=test_threshold_attestation,
        ).review_reason
        for candidate in candidates
    )


def test_compare_rating_values_match_mismatch_missing_and_unparseable():
    item = _expected()
    matching = _candidate("CB11", "C10")
    mismatch = _candidate("CB11", "16 A")
    unreadable = _candidate("CB11", "unreadable")

    assert compare_rating_candidates(item, [matching], "F-R1", 0.8,
                                     attested_threshold=attest_rating_distance_threshold(
                                         0.1, attestation_reference="test-only fixture"
                                     )).finding is None
    finding = compare_rating_candidates(
        item, [mismatch], "F-R2", 0.8,
        attested_threshold=attest_rating_distance_threshold(0.1, attestation_reference="test-only fixture"),
    ).finding
    assert finding is not None
    assert (finding.type, finding.status, finding.expected_value, finding.observed_text) == (
        "rating_mismatch", "potential_mismatch", "10 A", "16 A"
    )
    assert finding.evidence[0].bbox == [1, 1, 5, 5]
    approval = attest_rating_distance_threshold(0.1, attestation_reference="test-only fixture")
    assert compare_rating_candidates(item, [unreadable], "F-R3", 0.8,
                                     attested_threshold=approval).finding is None
    mixed_unreadable = compare_rating_candidates(
        item, [mismatch, unreadable], "F-R7", 0.8, attested_threshold=approval
    )
    assert mixed_unreadable.finding is None
    assert "unparseable" in mixed_unreadable.review_reason
    assert compare_rating_candidates(_expected(value=None), [mismatch], "F-R4", 0.8,
                                     attested_threshold=approval).finding is None
    assert compare_rating_candidates(_expected(value="not a rating"), [mismatch], "F-R5", 0.8,
                                     attested_threshold=approval).finding is None
    assert compare_rating_candidates(_expected(needs_review=True), [mismatch], "F-R6", 0.8,
                                     attested_threshold=approval).finding is None


def test_duplicate_and_conflicting_rating_candidates():
    first = _candidate("CB11", "16 A")
    duplicate = _candidate("CB11", "16A", [2, 2, 6, 6])
    conflict = _candidate("CB11", "20 A", [3, 3, 7, 7])

    approval = attest_rating_distance_threshold(0.1, attestation_reference="test-only fixture")
    result = compare_rating_candidates(_expected(), [first, duplicate], "F-R1", 0.8,
                                       attested_threshold=approval)
    assert result.finding is not None
    assert result.finding.status == "potential_mismatch"
    assert len(result.finding.evidence) == 2

    conflicting = compare_rating_candidates(_expected(), [first, conflict], "F-R2", 0.8,
                                            attested_threshold=approval)
    assert conflicting.finding is None
    assert "Conflicting" in conflicting.review_reason


@pytest.mark.parametrize(
    "confidence, expected_status",
    [(None, "needs_review"), (0.79, "needs_review"), (0.80, "potential_mismatch"), (0.81, "potential_mismatch")],
)
def test_rating_mismatch_respects_confidence_threshold(confidence, expected_status, test_threshold_attestation):
    candidate = _candidate("CB11", "16 A", confidence=confidence)

    finding = compare_rating_candidates(
        _expected(), [candidate], "F-R1", 0.80,
        attested_threshold=test_threshold_attestation,
    ).finding

    assert finding is not None
    assert finding.type == "rating_mismatch"
    assert finding.status == expected_status
    assert finding.ocr_confidence is confidence


def test_uncalibrated_distance_and_manual_candidate_cannot_approve_mismatch():
    candidate = _candidate("CB11", "16 A", distance=0.001)

    assert compare_rating_candidates(_expected(), [candidate], "F-R1", 0.8).finding is None
    with pytest.raises(TypeError, match="attested_threshold"):
        compare_rating_candidates(_expected(), [candidate], "F-R2", 0.8,
                                  attested_threshold=0.001)
    with pytest.raises(TypeError, match="within_threshold"):
        RatingCandidate(
            tag="CB11", image_id="IMG-1", observation=_rating_obs("16 A", [1, 1, 5, 5]),
            distance_fraction=0.001, ambiguous=False, within_threshold=True,
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, 1.01, True])
def test_explicit_attestation_factory_validates_test_threshold(value):
    with pytest.raises((TypeError, ValueError)):
        attest_rating_distance_threshold(value, attestation_reference="test-only fixture")


def test_explicit_attestation_requires_reference():
    with pytest.raises(ValueError, match="attestation reference"):
        attest_rating_distance_threshold(0.1, attestation_reference="  ")
