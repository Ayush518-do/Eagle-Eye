import pytest
from PIL import Image, ImageDraw, ImageFilter

from backend.app.pipeline import engine
from backend.app.pipeline import thresholds as threshold_module
from backend.app.pipeline.image_quality import check_photo
from backend.app.schemas import ExpectedItem, Finding, Observation


def _pattern(size=(256, 96)):
    image = Image.new("L", size, 200)
    draw = ImageDraw.Draw(image)
    tile = 4
    for y in range(0, size[1], tile):
        for x in range(0, size[0], tile):
            if (x // tile + y // tile) % 2:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=0)
    return image


@pytest.fixture
def thresholds():
    return {
        "min_text_confidence": 0.80,
        "min_detector_confidence": 0.50,
        "min_photo_width": 128,
        "min_sharpness": 100.0,
        "max_overexposed_fraction": 0.15,
    }


def _observation(text="CB11", confidence=0.95):
    return Observation(
        observation_id="OBS-1",
        source="ocr",
        kind="tag_label",
        class_name="tag_label",
        bbox=[10, 10, 50, 30],
        text=text,
        text_confidence=confidence,
    )


def test_good_quality_image_has_no_flags(tmp_path, thresholds):
    path = tmp_path / "sharp.png"
    _pattern().save(path)

    assert check_photo(path, thresholds) == []


def test_low_resolution_image_flagged(tmp_path, thresholds):
    path = tmp_path / "small.png"
    _pattern((100, 96)).save(path)

    assert "low_resolution" in check_photo(path, thresholds)


def test_blurred_image_flagged(tmp_path, thresholds):
    path = tmp_path / "blurred.png"
    _pattern().filter(ImageFilter.GaussianBlur(radius=5)).save(path)

    assert "low_sharpness" in check_photo(path, thresholds)


def test_overexposed_image_flagged(tmp_path, thresholds):
    path = tmp_path / "white.png"
    Image.new("L", (256, 96), 255).save(path)

    assert "overexposed" in check_photo(path, thresholds)


def test_verified_finding_is_gated_when_its_only_photo_is_blurry(tmp_path, thresholds):
    path = tmp_path / "blurred.png"
    _pattern().filter(ImageFilter.GaussianBlur(radius=5)).save(path)

    findings, flags = engine.run_inspection(
        [ExpectedItem(tag="CB11")],
        {"IMG-001": [_observation()]},
        {"IMG-001": path},
        thresholds,
    )

    assert "low_sharpness" in flags["IMG-001"]
    assert findings[0].status == "needs_review"
    assert findings[0].reason == "Supporting photo may be blurry."


def test_finding_stays_verified_if_another_supporting_photo_is_sharp(
    tmp_path, thresholds
):
    sharp_path = tmp_path / "sharp.png"
    blurred_path = tmp_path / "blurred.png"
    _pattern().save(sharp_path)
    _pattern().filter(ImageFilter.GaussianBlur(radius=5)).save(blurred_path)

    findings, _ = engine.run_inspection(
        [ExpectedItem(tag="CB11")],
        {"IMG-001": [_observation()], "IMG-002": [_observation()]},
        {"IMG-001": blurred_path, "IMG-002": sharp_path},
        thresholds,
    )

    assert findings[0].status == "verified"


def test_unrelated_blurry_photo_does_not_gate_finding(tmp_path, thresholds):
    sharp_path = tmp_path / "sharp.png"
    blurred_path = tmp_path / "unrelated-blurred.png"
    _pattern().save(sharp_path)
    _pattern().filter(ImageFilter.GaussianBlur(radius=5)).save(blurred_path)

    findings, flags = engine.run_inspection(
        [ExpectedItem(tag="CB11")],
        {"IMG-001": [_observation()], "IMG-002": []},
        {"IMG-001": sharp_path, "IMG-002": blurred_path},
        thresholds,
    )

    assert "low_sharpness" in flags["IMG-002"]
    assert findings[0].evidence[0].image_id == "IMG-001"
    assert findings[0].status == "verified"


def test_unassessed_evidence_image_downgrades_verified_finding(thresholds):
    findings, flags = engine.run_inspection(
        [ExpectedItem(tag="CB11")],
        {"IMG-001": [_observation()]},
        {},  # No quality result for the image that supports the finding.
        thresholds,
    )

    assert flags == {}
    assert findings[0].status == "needs_review"
    assert findings[0].reason == "Evidence photo quality could not be assessed."


def test_verified_finding_with_empty_evidence_is_downgraded():
    finding = Finding(finding_id="F-001", type="verified", status="verified")

    gated = engine.apply_confidence_gate([finding], {})

    assert gated[0].status == "needs_review"
    assert gated[0].reason == "Evidence photo quality could not be assessed."


def test_low_text_confidence_does_not_become_verified(tmp_path, thresholds):
    sharp_path = tmp_path / "sharp.png"
    _pattern().save(sharp_path)

    findings, _ = engine.run_inspection(
        [ExpectedItem(tag="CB11")],
        {"IMG-001": [_observation(confidence=0.2)]},
        {"IMG-001": sharp_path},
        thresholds,
    )

    assert findings[0].status == "needs_review"


def test_unseen_expected_item_remains_inconclusive_even_with_bad_photo(
    tmp_path, thresholds
):
    blurred_path = tmp_path / "blurred.png"
    _pattern().filter(ImageFilter.GaussianBlur(radius=5)).save(blurred_path)

    findings, flags = engine.run_inspection(
        [ExpectedItem(tag="PS11")],
        {"IMG-001": []},
        {"IMG-001": blurred_path},
        thresholds,
    )

    assert "low_sharpness" in flags["IMG-001"]
    assert findings[0].type == "missing"
    assert findings[0].status == "inconclusive"


def test_missing_image_raises_file_not_found(tmp_path, thresholds):
    with pytest.raises(FileNotFoundError):
        check_photo(tmp_path / "absent.png", thresholds)


def test_invalid_image_raises_value_error(tmp_path, thresholds):
    path = tmp_path / "invalid.png"
    path.write_bytes(b"not a real image")

    with pytest.raises(ValueError, match="Unable to read inspection image"):
        check_photo(path, thresholds)


def test_synthetic_observation_still_rejected(tmp_path, thresholds):
    path = tmp_path / "sharp.png"
    _pattern().save(path)

    with pytest.raises(ValueError, match="Synthetic observations"):
        engine.run_inspection(
            [ExpectedItem(tag="CB11")],
            {"IMG-001": [_observation().model_copy(update={"source": "synthetic"})]},
            {"IMG-001": path},
            thresholds,
        )


def test_threshold_loader_reports_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(threshold_module, "_CONFIG_PATH", tmp_path / "missing.yaml")

    with pytest.raises(RuntimeError, match="Unable to read inspection thresholds"):
        threshold_module.load_thresholds()


@pytest.mark.parametrize(
    "contents",
    [
        "min_text_confidence: not-a-number\n",
        "min_text_confidence: nan\n",
        "min_text_confidence: 0.8\nmin_text_confidence: 0.7\n",
        "min_text_confidence: 0.8\nunknown_threshold: 2\n",
        "min_text_confidence: 0.8\n",
    ],
)
def test_threshold_loader_rejects_malformed_file(monkeypatch, tmp_path, contents):
    path = tmp_path / "thresholds.yaml"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(threshold_module, "_CONFIG_PATH", path)

    with pytest.raises(ValueError):
        threshold_module.load_thresholds()
