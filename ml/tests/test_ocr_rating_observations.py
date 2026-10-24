from PIL import Image

from ml import interfaces
from ml.ocr import read_tags


def _points(x, y):
    return [[x, y], [x + 20, y], [x + 20, y + 10], [x, y + 10]]


def test_read_tags_distinguishes_explicit_rating_text_from_tag_labels(tmp_path, monkeypatch):
    image_path = tmp_path / "ocr-output.png"
    Image.new("RGB", (120, 80), "white").save(image_path)

    class FakeOcr:
        def __call__(self, path):
            def box(x, y):
                return [[x, y], [x + 20, y], [x + 20, y + 10], [x, y + 10]]

            return [
                (box(5, 5), "CB11", 0.99),
                (box(30, 5), "16 A", 0.91),
                (box(60, 5), "24VDC", 0.92),
                (box(90, 5), "Alarm", 0.80),
            ], 0.01

    monkeypatch.setattr(read_tags, "_get_engine", lambda: FakeOcr())
    result = read_tags.read_tags(str(image_path), expected=["CB11"])
    observations = result["observations"]

    assert result["contract_version"] == "0.2"
    assert [
        (observation["kind"], observation["text"], observation["raw_text"])
        for observation in observations
    ] == [
        ("tag_label", "CB11", "CB11"),
        ("rating", None, "16 A"),
        ("rating", None, "24VDC"),
        ("tag_label", "Alarm", "Alarm"),
    ]


def test_public_interface_matches_expected_tags_and_preserves_uncertainty(tmp_path, monkeypatch):
    image_path = tmp_path / "photo.png"
    Image.new("RGB", (120, 80), "white").save(image_path)

    class FakeOcr:
        def __call__(self, path):
            return [
                (_points(1, 2), "CB11", 0.99),       # exact expected tag
                (_points(25, 2), "C811", 0.95),     # unique lookalike correction
                (_points(49, 2), "CB1?", 0.40),     # equally close to CB11 and CB12
                (_points(73, 2), "Alarm", 0.80),    # unrelated text
                (_points(97, 2), "24VDC", None),    # explicit rating, absent OCR score
            ], 0.01

    monkeypatch.setattr(read_tags, "_get_engine", lambda: FakeOcr())
    result = interfaces.read_tags(
        str(image_path),
        expected_tags=["CB11", "CB12"],
        image_id="IMG-EXPECTED",
    )
    observations = result["observations"]

    assert result["contract_version"] == "0.2"
    assert result["image_id"] == "IMG-EXPECTED"
    assert result["image_size"] == [120, 80]
    assert observations[0]["kind"] == "tag_label"
    assert observations[0]["text"] == observations[0]["raw_text"] == "CB11"
    assert observations[1]["kind"] == "tag_label"
    assert observations[1]["text"] == "CB11"
    assert observations[1]["raw_text"] == "C811"
    assert observations[2]["kind"] == "tag_label"
    assert observations[2]["text"] == observations[2]["raw_text"] == "CB1?"
    assert observations[2]["text_confidence"] == 0.40
    assert observations[3]["text"] == observations[3]["raw_text"] == "Alarm"
    assert observations[4]["kind"] == "rating"
    assert observations[4]["text"] is None
    assert observations[4]["raw_text"] == "24VDC"
    assert observations[4]["text_confidence"] is None
    assert observations[1]["bbox"] == [25.0, 2.0, 45.0, 12.0]


def test_public_interface_remains_compatible_with_one_argument_call(tmp_path, monkeypatch):
    image_path = tmp_path / "legacy-call.png"
    Image.new("RGB", (40, 30), "white").save(image_path)

    class FakeOcr:
        def __call__(self, path):
            return [(_points(2, 3), "CB11", 0.91)], 0.01

    monkeypatch.setattr(read_tags, "_get_engine", lambda: FakeOcr())
    result = interfaces.read_tags(str(image_path))

    assert result["image_id"] == "legacy-call"
    assert result["observations"][0]["text"] == "CB11"


def test_public_interface_propagates_missing_image_errors(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        interfaces.read_tags(str(tmp_path / "missing.png"), expected_tags=["CB11"])
