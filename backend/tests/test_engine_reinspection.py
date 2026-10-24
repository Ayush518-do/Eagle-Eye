from backend.app.pipeline.reinspection import compare_with_previous
from backend.app.pipeline import engine
from backend.app.schemas import Evidence, ExpectedItem, Finding, Observation


def _finding(
    finding_id,
    finding_type,
    tag,
    status,
    *,
    expected_value=None,
    observed_text=None,
    evidence=(),
):
    return Finding(
        finding_id=finding_id,
        type=finding_type,
        tag=tag,
        status=status,
        expected_value=expected_value,
        observed_text=observed_text,
        evidence=list(evidence),
    )


def test_reinspection_resolves_inconclusive_missing_tag_when_newly_verified():
    old = _finding("F-OLD", "missing", "CB-11", "inconclusive")
    current = _finding(
        "F-NEW", "verified", "CB11", "verified", observed_text="CB11",
        evidence=[Evidence(image_id="IMG-1", bbox=[1, 1, 5, 5])],
    )

    result = compare_with_previous([old], [current], assessed_image_ids={"IMG-1"})

    assert len(result) == 1
    assert result[0].finding_id == "F-OLD"
    assert result[0].status == "resolved_after_reinspection"
    assert result[0].evidence == old.evidence


def test_reinspection_keeps_old_finding_open_without_a_verified_match():
    old = _finding("F-OLD", "missing", "PS11", "inconclusive")
    current = _finding("F-NEW", "verified", "PS11", "needs_review")

    result = compare_with_previous([old], [current])

    assert result[0] is old
    assert result[0].status == "inconclusive"
    assert result[1] is current


def test_reinspection_does_not_resolve_rating_mismatch_from_tag_read_alone():
    old = _finding(
        "F-OLD", "rating_mismatch", "CB11", "potential_mismatch",
        expected_value="10 A", observed_text="16 A",
    )
    current = _finding("F-NEW", "verified", "CB11", "verified", observed_text="CB11")

    result = compare_with_previous([old], [current])

    assert result[0] is old
    assert result[0].status == "potential_mismatch"
    assert result[1] is current


def test_reinspection_does_not_resolve_placement_from_tag_read_alone():
    old = _finding(
        "F-OLD", "misplaced", "CB11", "potential_mismatch",
        expected_value="left rail",
    )
    current = _finding(
        "F-NEW", "verified", "CB11", "verified", observed_text="CB11",
        evidence=[Evidence(image_id="IMG-1", bbox=[1, 1, 5, 5])],
    )

    result = compare_with_previous([old], [current], assessed_image_ids={"IMG-1"})

    assert result[0] is old
    assert result[0].status == "potential_mismatch"
    assert result[1] is current


def test_reinspection_resolves_rating_only_when_that_finding_is_verified():
    old = _finding(
        "F-OLD", "rating_mismatch", "CB11", "potential_mismatch",
        expected_value="10 A", observed_text="16 A",
    )
    current = _finding(
        "F-NEW", "rating_mismatch", "CB-11", "verified",
        expected_value="10 A", observed_text="10 A",
        evidence=[Evidence(image_id="IMG-1", bbox=[1, 1, 5, 5])],
    )

    result = compare_with_previous([old], [current], assessed_image_ids={"IMG-1"})

    assert len(result) == 1
    assert result[0].status == "resolved_after_reinspection"


def test_reinspection_is_order_independent_preserves_persistent_and_adds_new():
    old_missing = _finding("F-OLD-1", "missing", "CB11", "inconclusive")
    old_unexpected = _finding("F-OLD-2", "unexpected", "X1", "needs_review")
    verified = _finding("F-NEW-1", "verified", "CB11", "verified")
    new_missing = _finding("F-NEW-2", "missing", "PS11", "inconclusive")

    verified.evidence = [Evidence(image_id="IMG-1", bbox=[1, 1, 5, 5])]
    result = compare_with_previous(
        [old_missing, old_unexpected], [new_missing, verified],
        assessed_image_ids={"IMG-1"},
    )
    reordered_result = compare_with_previous(
        [old_unexpected, old_missing], [verified, new_missing],
        assessed_image_ids={"IMG-1"},
    )

    assert [item.finding_id for item in result] == ["F-OLD-1", "F-OLD-2", "F-NEW-2"]
    assert result[0].status == "resolved_after_reinspection"
    assert result[1].status == "needs_review"
    assert result[2] is new_missing
    assert {
        item.tag: (item.finding_id, item.status) for item in result
    } == {
        item.tag: (item.finding_id, item.status) for item in reordered_result
    }


def test_reinspection_deduplicates_same_persistent_finding_across_run_ids():
    old = _finding("F-OLD", "missing", "CB11", "inconclusive")
    same_issue_new_id = _finding("F-NEW", "missing", "CB-11", "inconclusive")

    result = compare_with_previous([old], [same_issue_new_id])

    assert result == [old]


def test_reinspection_deduplicates_repeated_new_findings():
    first = _finding("F-1", "unexpected", "X1", "needs_review")
    repeated = _finding("F-2", "unexpected", "X1", "needs_review")

    result = compare_with_previous([], [first, repeated])

    assert result == [first]


def test_reinspection_does_not_resolve_without_evidence_or_assessment():
    old = _finding("F-OLD", "missing", "CB11", "inconclusive")
    no_evidence = _finding("F-NEW", "verified", "CB11", "verified")
    with_evidence = _finding(
        "F-NEW", "verified", "CB11", "verified",
        evidence=[Evidence(image_id="IMG-1", bbox=[1, 1, 5, 5])],
    )

    assert compare_with_previous([old], [no_evidence])[0].status == "inconclusive"
    result = compare_with_previous([old], [with_evidence])
    assert result[0].status == "inconclusive"
    assert compare_with_previous(
        [old], [with_evidence], assessed_image_ids={"OTHER-IMAGE"}
    )[0].status == "inconclusive"
    assert compare_with_previous(
        [old], [with_evidence], assessed_image_ids={"IMG-1"}
    )[0].status == "resolved_after_reinspection"


def test_reinspection_marks_multiple_verified_candidates_for_review():
    old = _finding("F-OLD", "missing", "CB11", "inconclusive")
    first = _finding(
        "F-1", "verified", "CB11", "verified", observed_text="CB11",
        evidence=[Evidence(image_id="IMG-1", bbox=[1, 1, 5, 5])],
    )
    second = _finding(
        "F-2", "verified", "CB-11", "verified", observed_text="CB-11",
        evidence=[Evidence(image_id="IMG-2", bbox=[1, 1, 5, 5])],
    )

    result = compare_with_previous(
        [old], [first, second], assessed_image_ids={"IMG-1", "IMG-2"}
    )

    assert result[0].status == "inconclusive"
    assert [finding.status for finding in result[1:]] == ["needs_review", "needs_review"]
    assert all("ambiguous" in finding.reason for finding in result[1:])


def test_duplicate_old_ids_are_made_unique_independent_of_input_order():
    missing = _finding("F-DUP", "missing", "CB11", "inconclusive")
    unexpected = _finding("F-DUP", "unexpected", "X1", "needs_review")

    first = compare_with_previous([missing, unexpected], [])
    second = compare_with_previous([unexpected, missing], [])
    first_by_tag = {item.tag: item.finding_id for item in first}
    second_by_tag = {item.tag: item.finding_id for item in second}

    assert len({item.finding_id for item in first}) == 2
    assert len({item.finding_id for item in second}) == 2
    assert first_by_tag["CB11"] == second_by_tag["CB11"] == "F-DUP"
    assert first_by_tag["X1"].startswith("F-RI-")
    assert second_by_tag["X1"].startswith("F-RI-")


def test_new_finding_ids_are_remapped_on_collisions_and_unique():
    old = _finding("F-001", "missing", "CB11", "inconclusive")
    colliding = _finding("F-001", "unexpected", "X1", "needs_review")
    repeated = _finding("F-001", "unexpected", "X2", "needs_review")

    result = compare_with_previous([old], [colliding, repeated])
    ids = [item.finding_id for item in result]

    assert ids[0] == "F-001"
    assert len(ids) == len(set(ids)) == 3
    assert all(value.startswith("F-RI-") for value in ids[1:])


def test_run_reinspection_integrates_prior_findings_through_engine_entrypoint(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    previous = [_finding("F-OLD", "missing", "CB11", "inconclusive")]
    tag_observation = Observation(
        observation_id="OBS-1",
        source="manual",
        kind="tag_label",
        class_name="tag_label",
        bbox=[10, 10, 30, 25],
        text="CB11",
        text_confidence=0.95,
    )

    findings, image_flags = engine.run_reinspection(
        previous,
        [ExpectedItem(tag="CB11")],
        {"IMG-1": [tag_observation]},
        {"IMG-1": "synthetic-test-image.png"},
    )

    assert image_flags == {"IMG-1": []}
    assert len(findings) == 1
    assert findings[0].finding_id == "F-OLD"
    assert findings[0].status == "resolved_after_reinspection"


def test_run_reinspection_keeps_previous_issue_open_when_photo_is_blurry(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: ["low_sharpness"])
    previous = [_finding("F-OLD", "missing", "CB11", "inconclusive")]
    tag_observation = Observation(
        observation_id="OBS-1",
        source="manual",
        kind="tag_label",
        class_name="tag_label",
        bbox=[10, 10, 30, 25],
        text="CB11",
        text_confidence=0.95,
    )

    findings, image_flags = engine.run_reinspection(
        previous,
        [ExpectedItem(tag="CB11")],
        {"IMG-1": [tag_observation]},
        {"IMG-1": "synthetic-test-image.png"},
    )

    assert image_flags == {"IMG-1": ["low_sharpness"]}
    assert findings[0] is previous[0]
    assert findings[0].status == "inconclusive"
    assert findings[1].status == "needs_review"


def test_run_reinspection_does_not_resolve_when_evidence_image_was_not_assessed(monkeypatch):
    monkeypatch.setattr(engine, "check_photo", lambda path, thresholds: [])
    previous = [_finding("F-OLD", "missing", "CB11", "inconclusive")]
    tag_observation = Observation(
        observation_id="OBS-UNASSESSED",
        source="manual",
        kind="tag_label",
        class_name="tag_label",
        bbox=[10, 10, 30, 25],
        text="CB11",
        text_confidence=0.95,
    )

    findings, image_flags = engine.run_reinspection(
        previous,
        [ExpectedItem(tag="CB11")],
        {"IMG-EVIDENCE": [tag_observation]},
        {"IMG-ASSESSED": "photo.png"},
    )

    assert image_flags == {"IMG-ASSESSED": []}
    assert findings[0].status == "inconclusive"
    assert findings[1].status == "needs_review"
    assert "could not be assessed" in findings[1].reason
