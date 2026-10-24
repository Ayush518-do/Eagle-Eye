import pytest
from PIL import Image

from backend.app.pipeline import engine


def _drawing(items=None):
    return {
        "contract_version": "0.2",
        "parser_version": "drawing-parser test",
        "items": items if items is not None else [{"tag": "CB11"}],
    }


def _image(image_id, observations):
    return {
        "contract_version": "0.2",
        "image_id": image_id,
        "image_size": [100, 80],
        "observations": observations,
    }


def _observation(oid, kind, *, text=None, raw_text=None):
    return {
        "observation_id": oid,
        "source": "ocr",
        "kind": kind,
        "class_name": kind,
        "bbox": [10, 10, 30, 20],
        "text": text,
        "raw_text": raw_text,
        "text_confidence": 0.95,
    }


def test_contract_adapter_validates_and_runs_producer_dictionaries(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    photo = tmp_path / "photo.png"
    Image.new("RGB", (100, 80), "white").save(photo)
    finding_result = engine.run_inspection_from_contracts(
        _drawing(),
        {"IMG-1": _image("IMG-1", [_observation("O-1", "tag_label", text="CB11")])},
        {"IMG-1": photo},
    )

    findings, flags = finding_result
    assert findings[0].status == "verified"
    assert findings[0].evidence[0].image_id == "IMG-1"
    assert flags == {"IMG-1": []}


def test_contract_adapter_supports_multiple_images_and_empty_observations(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    paths = {}
    for image_id in ("IMG-1", "IMG-2", "IMG-3"):
        path = tmp_path / f"{image_id}.png"
        Image.new("RGB", (100, 80), "white").save(path)
        paths[image_id] = path
    findings, flags = engine.run_inspection_from_contracts(
        _drawing(),
        {
            "IMG-1": _image("IMG-1", []),
            "IMG-2": _image("IMG-2", [_observation("O-2", "tag_label", text="CB11")]),
        },
        paths,
    )

    assert flags == {"IMG-1": [], "IMG-2": [], "IMG-3": []}
    assert findings[0].status == "verified"
    assert {e.image_id for e in findings[0].evidence} == {"IMG-2"}


def test_contract_adapter_accepts_ml_detector_v03_output(monkeypatch, tmp_path):
    """The available producer shape uses v0.3 but keeps v0.2 observation fields."""
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    photo = tmp_path / "cabinet.png"
    Image.new("RGB", (400, 300), "white").save(photo)
    detector_output = {
        "contract_version": "0.3",
        "image_id": "cabinet",
        "image_sha256": "a" * 64,
        "image_size": [400, 300],
        "observations": [
            {
                "observation_id": "DET-001",
                "source": "detector",
                "kind": "component",
                "class_name": "mcb",
                "bbox": [120.0, 80.0, 170.0, 180.0],
                "confidence": 0.77,
                "text": None,
                "raw_text": None,
                "text_confidence": None,
                "model": {
                    "name": "rf-detr-small",
                    "version": "checkpoint_best_total.pth",
                    "weights_sha256": "b" * 64,
                },
            }
        ],
    }

    findings, flags = engine.run_inspection_from_contracts(
        _drawing(), {"cabinet": detector_output}, {"cabinet": photo}
    )

    # Detector boxes are accepted and validated but do not imply a tag match.
    assert findings[0].status == "inconclusive"
    assert findings[0].observed_text is None
    assert flags == {"cabinet": []}


def test_contract_adapter_rejects_zero_shot_source_until_contract_supports_it(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    photo = tmp_path / "cabinet.png"
    Image.new("RGB", (400, 300), "white").save(photo)
    contract = {
        "contract_version": "0.3",
        "image_id": "cabinet",
        "image_size": [400, 300],
        "observations": [
            {
                "observation_id": "ZS-001",
                "source": "zero_shot",
                "kind": "component",
                "class_name": "power_supply",
                "bbox": [120, 80, 170, 180],
                "confidence": 0.77,
            }
        ],
    }

    with pytest.raises(ValueError, match="(?s)Invalid image contract.*source"):
        engine.run_inspection_from_contracts(
            _drawing(), {"cabinet": contract}, {"cabinet": photo}
        )


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda c: c["observations"][0].update(bbox=[390, 10, 410, 20]), "bbox falls outside"),
        (lambda c: c["observations"][0].update(confidence=1.1), "confidence"),
        (lambda c: c["observations"][0].update(observation_id=" "), "IDs must be non-empty"),
        (lambda c: c["observations"][0].update(class_name=None), "class_name"),
        (lambda c: c.update(image_size=[399, 300]), "but the original image is"),
    ],
)
def test_contract_adapter_rejects_invalid_ml_detector_output(
    monkeypatch, tmp_path, mutate, message
):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    photo = tmp_path / "cabinet.png"
    Image.new("RGB", (400, 300), "white").save(photo)
    contract = {
        "contract_version": "0.3",
        "image_id": "cabinet",
        "image_size": [400, 300],
        "observations": [
            {
                "observation_id": "DET-001",
                "source": "detector",
                "kind": "component",
                "class_name": "mcb",
                "bbox": [120.0, 80.0, 170.0, 180.0],
                "confidence": 0.77,
            }
        ],
    }
    mutate(contract)
    with pytest.raises((ValueError, TypeError), match=message):
        engine.run_inspection_from_contracts(
            _drawing(), {"cabinet": contract}, {"cabinet": photo}
        )


@pytest.mark.parametrize(
    "drawing, images, message",
    [
        ({"contract_version": "0.1", "parser_version": "x", "items": []}, {}, "contract_version"),
        ({"contract_version": "0.2", "parser_version": "x", "items": [{"tag": "CB11", "unknown": 1}]}, {}, "unsupported field"),
        (_drawing(), {"IMG-1": {"contract_version": "0.2", "image_id": "IMG-1", "image_size": [1, 1], "observations": [{"bad": 1}]}}, "unsupported field"),
    ],
)
def test_contract_adapter_rejects_incompatible_or_malformed_dictionaries(
    drawing, images, message
):
    with pytest.raises((ValueError, TypeError), match=message):
        engine.run_inspection_from_contracts(drawing, images, {})


def test_contract_adapter_rejects_image_key_mismatch():
    with pytest.raises(ValueError, match="does not match its mapping key"):
        engine.run_inspection_from_contracts(
            _drawing(), {"IMG-1": _image("IMG-2", [])}, {}
        )


def test_contract_adapter_rejects_dimensions_that_do_not_match_original_photo(tmp_path):
    photo = tmp_path / "actual.png"
    Image.new("RGB", (100, 80), "white").save(photo)
    mismatched = _image("IMG-1", [])
    mismatched["image_size"] = [99, 80]
    with pytest.raises(ValueError, match="but the original image is"):
        engine.run_inspection_from_contracts(
            _drawing(), {"IMG-1": mismatched}, {"IMG-1": photo}
        )


@pytest.mark.parametrize(
    "drawing, image, message",
    [
        (_drawing([{"tag": " "}]), _image("IMG-1", []), "tags must be non-empty"),
        (_drawing(), _image("IMG-1", [_observation(" ", "tag_label", text="CB11")]), "observation IDs must be non-empty"),
        (_drawing(), _image("IMG-1", [_observation("O-1", "tag_label", text="CB11")]), "bbox falls outside"),
    ],
)
def test_contract_adapter_rejects_empty_ids_and_out_of_image_boxes(
    drawing, image, message, tmp_path
):
    photo = tmp_path / "bounded.png"
    Image.new("RGB", (100, 80), "white").save(photo)
    if message == "bbox falls outside":
        image["observations"][0]["bbox"] = [90, 10, 110, 20]
    with pytest.raises(ValueError, match=message):
        engine.run_inspection_from_contracts(drawing, {"IMG-1": image}, {"IMG-1": photo})


def test_contract_adapter_rejects_missing_image_path_and_invalid_path_mapping():
    image = {"IMG-1": _image("IMG-1", [])}
    with pytest.raises(ValueError, match="no corresponding entry in image_paths"):
        engine.run_inspection_from_contracts(_drawing(), image, {})
    with pytest.raises(TypeError, match="image_paths must map"):
        engine.run_inspection_from_contracts(_drawing(), {}, [])


def test_rating_observation_is_preserved_but_never_treated_as_tag_label(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    photo = tmp_path / "rating.png"
    Image.new("RGB", (100, 80), "white").save(photo)
    findings, _ = engine.run_inspection_from_contracts(
        _drawing(),
        {
            "IMG-1": _image(
                "IMG-1", [_observation("O-R", "rating", raw_text="10 A")]
            )
        },
        {"IMG-1": photo},
    )

    assert findings[0].type == "missing"
    assert findings[0].status == "inconclusive"
    assert findings[0].evidence == []


def test_component_observation_is_not_misread_as_a_tag_label(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    photo = tmp_path / "component.png"
    Image.new("RGB", (100, 80), "white").save(photo)
    component = {
        "observation_id": "DET-1",
        "source": "detector",
        "kind": "component",
        "class_name": "mcb",
        "bbox": [10, 10, 30, 40],
        "confidence": 0.91,
    }
    findings, _ = engine.run_inspection_from_contracts(
        _drawing(), {"IMG-1": _image("IMG-1", [component])}, {"IMG-1": photo}
    )

    assert findings[0].type == "missing"
    assert findings[0].status == "inconclusive"
    assert findings[0].observed_text is None


def test_direct_run_inspection_contract_remains_unchanged(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    findings, flags = engine.run_inspection([], {}, {})
    assert findings == []
    assert flags == {}
