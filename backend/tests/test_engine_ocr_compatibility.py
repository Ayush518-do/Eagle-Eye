from PIL import Image

from backend.app.pipeline import engine
from ml import interfaces
from ml.ocr import read_tags as ocr_read_tags


def test_public_ocr_interface_output_flows_through_contract_adapter(
    tmp_path, monkeypatch
):
    image_path = tmp_path / "cabinet-photo.png"
    Image.new("RGB", (120, 80), "white").save(image_path)

    class FakeOcr:
        def __call__(self, path):
            points = [[5, 6], [35, 6], [35, 18], [5, 18]]
            return [(points, "C811", 0.96)], 0.01

    monkeypatch.setattr(ocr_read_tags, "_get_engine", lambda: FakeOcr())
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])

    image_contract = interfaces.read_tags(
        str(image_path), expected_tags=["CB11"], image_id="IMG-101"
    )
    assert image_contract["observations"][0]["text"] == "CB11"
    assert image_contract["observations"][0]["raw_text"] == "C811"

    findings, image_flags = engine.run_inspection_from_contracts(
        {"contract_version": "0.2", "parser_version": "synthetic-test", "items": [{"tag": "CB11"}]},
        {"IMG-101": image_contract},
        {"IMG-101": image_path},
    )

    assert image_flags == {"IMG-101": []}
    assert findings[0].status == "verified"
    assert findings[0].observed_text == "CB11"
    assert findings[0].ocr_confidence == 0.96
    assert findings[0].evidence[0].image_id == "IMG-101"
    assert findings[0].evidence[0].bbox == [5.0, 6.0, 35.0, 18.0]


def test_ambiguous_ocr_text_does_not_verify_either_expected_tag(tmp_path, monkeypatch):
    image_path = tmp_path / "ambiguous-photo.png"
    Image.new("RGB", (120, 80), "white").save(image_path)

    class FakeOcr:
        def __call__(self, path):
            points = [[5, 6], [35, 6], [35, 18], [5, 18]]
            return [(points, "CB1?", 0.99)], 0.01

    monkeypatch.setattr(ocr_read_tags, "_get_engine", lambda: FakeOcr())
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    image_contract = interfaces.read_tags(
        str(image_path), expected_tags=["CB11", "CB12"], image_id="IMG-AMB"
    )

    findings, _ = engine.run_inspection_from_contracts(
        {"contract_version": "0.2", "parser_version": "synthetic-test", "items": [{"tag": "CB11"}, {"tag": "CB12"}]},
        {"IMG-AMB": image_contract},
        {"IMG-AMB": image_path},
    )

    by_tag = {finding.tag: finding for finding in findings}
    assert by_tag["CB11"].status == "inconclusive"
    assert by_tag["CB12"].status == "inconclusive"
    ambiguous = by_tag["CB1?"]
    assert ambiguous.type == "unexpected"
    assert ambiguous.status == "needs_review"


def test_low_or_missing_ocr_confidence_stays_needs_review(tmp_path, monkeypatch):
    image_path = tmp_path / "low-confidence.png"
    Image.new("RGB", (120, 80), "white").save(image_path)
    class FakeOcr:
        def __call__(self, path):
            return [
                ([[5, 6], [35, 6], [35, 18], [5, 18]], "CB11", 0.40),
                ([[40, 6], [70, 6], [70, 18], [40, 18]], "CB11", None),
            ], 0.01

    monkeypatch.setattr(ocr_read_tags, "_get_engine", lambda: FakeOcr())
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    image_contract = interfaces.read_tags(
        str(image_path), expected_tags=["CB11"], image_id="IMG-LOW"
    )
    assert [obs["text_confidence"] for obs in image_contract["observations"]] == [0.40, None]

    findings, _ = engine.run_inspection_from_contracts(
        {"contract_version": "0.2", "parser_version": "synthetic-test", "items": [{"tag": "CB11"}]},
        {"IMG-LOW": image_contract},
        {"IMG-LOW": image_path},
    )

    assert findings[0].status == "needs_review"
    assert findings[0].ocr_confidence == 0.40
