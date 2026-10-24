import pytest

from backend.app.pipeline.compare import compare, overall_status
from backend.app.schemas import ExpectedItem, Observation


def tag(oid, text, conf, source="ocr"):
    return Observation(observation_id=oid, source=source, kind="tag_label", class_name="tag_label",
                       bbox=[10, 10, 50, 30], confidence=0.9, text=text, text_confidence=conf)


EXPECTED = [ExpectedItem(tag="CB11"), ExpectedItem(tag="CB12"), ExpectedItem(tag="PS11")]


def test_observations_reach_comparison():
    """Regression for the prototype bug: real observations in -> not all inconclusive."""
    f = compare(EXPECTED, {"IMG-1": [tag("o1", "CB11", 0.95), tag("o2", "CB-12", 0.91)]})
    by_tag = {x.tag: x for x in f}
    assert by_tag["CB11"].status == "verified"
    assert by_tag["CB12"].status == "verified"          # punctuation ignored
    assert by_tag["PS11"].status == "inconclusive"      # not read != missing
    assert by_tag["PS11"].type == "missing"
    assert overall_status(f) == "review_required"


def test_low_confidence_needs_review():
    f = compare([ExpectedItem(tag="CB11")], {"IMG-1": [tag("o1", "CB11", 0.40)]})
    assert f[0].status == "needs_review"


def test_unexpected_tag_flagged_for_review():
    f = compare([ExpectedItem(tag="CB11")], {"IMG-1": [tag("o1", "CB11", 0.9), tag("o2", "CB99", 0.9)]})
    extra = [x for x in f if x.type == "unexpected"]
    assert len(extra) == 1 and extra[0].status == "needs_review"


def test_all_verified_is_pass():
    f = compare([ExpectedItem(tag="CB11")], {"IMG-1": [tag("o1", "CB11", 0.99)]})
    assert overall_status(f) == "pass"


def test_synthetic_data_refused():
    with pytest.raises(ValueError):
        compare([ExpectedItem(tag="CB11")], {"IMG-1": [tag("o1", "CB11", 0.9, source="synthetic")]})


def test_bad_bbox_rejected():
    with pytest.raises(ValueError):
        Observation(observation_id="x", source="ocr", kind="tag_label", class_name="t",
                    bbox=[50, 10, 10, 30])
