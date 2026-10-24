from datetime import datetime, timezone

from PIL import Image
import pytest

from backend.app.pipeline.engine import run_inspection_from_contracts, run_reinspection
from backend.app.reports.assembly import assemble_inspection_result
from backend.app.reports.html_report import generate_html_report, render_html_report
from backend.app.schemas import Evidence, Finding, ImageInfo, InspectionResult


def _inspection(findings=(), *, status="review_required", images=()):
    return InspectionResult(
        inspection_id="INS-1",
        cabinet_id="CAB-1",
        design_revision_id="REV-A",
        created_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
        overall_status=status,
        images=list(images),
        findings=list(findings),
        counts={},
    )


def _finding(
    finding_id,
    *,
    tag="CB11",
    status="needs_review",
    finding_type="verified",
    expected="10 A",
    observed="16 A",
    evidence=(),
    reason=None,
):
    return Finding(
        finding_id=finding_id,
        type=finding_type,
        tag=tag,
        expected_value=expected,
        observed_text=observed,
        ocr_confidence=0.93,
        status=status,
        reason=reason,
        evidence=list(evidence),
    )


def test_report_renders_empty_findings_and_does_not_claim_pass():
    report = render_html_report(_inspection([], status="pass"), {})

    assert "No findings were recorded." in report
    assert "Overall status:</strong> Review Required" in report
    assert "Inspection assistance only." in report


def test_report_renders_multiple_findings_quality_flags_and_evidence_crops(tmp_path):
    photo = tmp_path / "synthetic-photo.png"
    Image.new("RGB", (40, 30), "green").save(photo)
    findings = [
        _finding(
            "F-1",
            status="potential_mismatch",
            finding_type="rating_mismatch",
            evidence=[Evidence(image_id="IMG-1", bbox=[5, 6, 20, 22])],
        ),
        _finding(
            "F-2",
            tag="PS11",
            status="needs_review",
            observed=None,
            evidence=[Evidence(image_id="IMG-1", bbox=[20, 5, 40, 30])],
        ),
    ]
    image = ImageInfo(
        image_id="IMG-1",
        url="/api/images/IMG-1",
        width=40,
        height=30,
        quality_flags=["low_sharpness", "overexposed"],
    )

    report = render_html_report(
        _inspection(findings, status="review_required", images=[image]),
        {"IMG-1": photo},
    )

    assert report.count("<tr><td>") == 2
    assert "Potential mismatch" in report
    assert "Needs review" in report
    assert "Photo may be blurry." in report
    assert "Glare or overexposure may hide details." in report
    assert report.count("data:image/png;base64,") == 2
    assert "Expected</th><th>Read</th><th>OCR</th>" in report


def test_report_marks_missing_evidence_and_unavailable_image_explicitly(tmp_path):
    unlisted_photo = tmp_path / "unlisted.png"
    Image.new("RGB", (8, 8), "white").save(unlisted_photo)
    findings = [
        _finding("F-1", evidence=[]),
        _finding(
            "F-2",
            evidence=[Evidence(image_id="IMG-GONE", bbox=[0, 0, 5, 5])],
        ),
    ]

    report = render_html_report(
        _inspection(findings),
        {"IMG-GONE": unlisted_photo},
    )

    assert "No evidence attached." in report
    assert "Evidence image unavailable." in report
    assert "data:image/png;base64," not in report


def test_report_escapes_untrusted_metadata_and_finding_text():
    finding = _finding(
        "F-1",
        tag='<script>alert("tag")</script>',
        reason='<img src=x onerror="alert(1)">',
        observed='<script>alert("read")</script>',
    )
    inspection = _inspection([finding]).model_copy(
        update={
            "inspection_id": '<script>alert("id")</script>',
            "cabinet_id": '<svg onload="alert(1)">',
        }
    )

    report = render_html_report(inspection, {})

    assert "<script>" not in report
    assert "<svg " not in report
    assert "&lt;script&gt;" in report
    assert "&lt;svg" in report
    assert "&lt;img" in report


def test_report_never_shows_pass_when_findings_require_review():
    finding = _finding("F-1", status="needs_review")

    report = render_html_report(_inspection([finding], status="pass"), {})

    assert "Overall status:</strong> Review Required" in report
    assert "Overall status:</strong> Pass" not in report


def test_report_ignores_stale_mismatch_status_for_clean_current_findings():
    finding = _finding("F-1", status="verified")

    report = render_html_report(_inspection([finding], status="mismatch_detected"), {})

    assert "Overall status:</strong> Pass" in report


def test_report_derives_mismatch_and_review_status_from_current_findings():
    mismatch = _finding("F-1", status="potential_mismatch", finding_type="rating_mismatch")
    mismatch_report = render_html_report(
        _inspection([mismatch], status="pass"), {}
    )
    inconclusive = _finding("F-2", status="inconclusive", finding_type="missing")
    inconclusive_report = render_html_report(
        _inspection([inconclusive], status="mismatch_detected"), {}
    )

    assert "Overall status:</strong> Mismatch Detected" in mismatch_report
    assert "Overall status:</strong> Review Required" in inconclusive_report


def test_report_writer_creates_file_and_refuses_to_overwrite(tmp_path):
    destination = tmp_path / "inspection.html"
    inspection = _inspection([])

    assert generate_html_report(inspection, {}, destination) == destination
    assert "No findings were recorded." in destination.read_text(encoding="utf-8")

    try:
        generate_html_report(inspection, {}, destination)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Existing report must not be overwritten")


def test_contract_observations_assemble_and_render_complete_current_inspection(tmp_path):
    photo = tmp_path / "synthetic-current.png"
    image = Image.new("RGB", (100, 80), "white")
    for x in range(10, 80, 10):
        for y in range(10, 70, 10):
            image.paste("black", (x, y, x + 4, y + 4))
    image.save(photo)
    drawing_contract = {
        "contract_version": "0.2",
        "parser_version": "test fixture",
        "items": [{"tag": "CB11"}],
    }
    image_contract = {
        "contract_version": "0.2",
        "image_id": "IMG-1",
        "image_size": [100, 80],
        "observations": [{
            "observation_id": "OBS-1",
            "source": "manual",
            "kind": "tag_label",
            "class_name": "tag_label",
            "bbox": [10, 10, 30, 20],
            "confidence": None,
            "text": "CB11",
            "raw_text": "CB11",
            "text_confidence": 0.99,
        }],
    }
    findings, flags = run_inspection_from_contracts(
        drawing_contract,
        {"IMG-1": image_contract},
        {"IMG-1": photo},
        thresholds={
            "min_photo_width": 1,
            "min_sharpness": 0,
            "max_overexposed_fraction": 1,
        },
    )
    assembled = assemble_inspection_result(
        inspection_id="INS-1",
        cabinet_id="CAB-1",
        design_revision_id="REV-A",
        created_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
        findings=findings,
        image_flags=flags,
        image_paths={"IMG-1": photo},
        image_urls={"IMG-1": "/api/images/IMG-1"},
    )
    report = render_html_report(assembled, {"IMG-1": photo})

    assert assembled.overall_status == "pass"
    assert assembled.counts == {"verified": 1}
    assert (assembled.images[0].width, assembled.images[0].height) == (100, 80)
    assert assembled.images[0].quality_flags == []
    assert "CB11" in report
    assert "data:image/png;base64," in report


def test_reinspection_assembly_requires_and_preserves_prior_image_records(tmp_path):
    photo = tmp_path / "synthetic-reinspection.png"
    Image.new("RGB", (100, 80), "white").save(photo)
    previous = _finding(
        "F-OLD", tag="CB11", status="inconclusive", finding_type="missing",
        evidence=[Evidence(image_id="IMG-OLD", bbox=[1, 1, 20, 20])],
    )
    from backend.app.schemas import ExpectedItem, Observation

    observation = Observation(
        observation_id="OBS-NEW", source="manual", kind="tag_label",
        class_name="tag_label", bbox=[10, 10, 30, 20], text="CB11",
        text_confidence=0.99,
    )
    findings, flags = run_reinspection(
        [previous], [ExpectedItem(tag="CB11")],
        {"IMG-NEW": [observation]}, {"IMG-NEW": photo},
        thresholds={"min_photo_width": 1, "min_sharpness": 0,
                    "max_overexposed_fraction": 1},
    )
    prior_image = ImageInfo(
        image_id="IMG-OLD", url="/api/images/IMG-OLD", width=100, height=80,
    )

    with pytest.raises(ValueError, match="Evidence references image IDs"):
        assemble_inspection_result(
            inspection_id="INS-2", cabinet_id="CAB-1",
            created_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
            findings=findings, image_flags=flags,
            image_paths={"IMG-NEW": photo},
            image_urls={"IMG-NEW": "/api/images/IMG-NEW"},
        )

    assembled = assemble_inspection_result(
        inspection_id="INS-2", cabinet_id="CAB-1",
        created_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
        findings=findings, image_flags=flags,
        image_paths={"IMG-NEW": photo},
        image_urls={"IMG-NEW": "/api/images/IMG-NEW"},
        prior_images=[prior_image],
    )
    report = render_html_report(
        assembled,
        {"IMG-NEW": photo, "IMG-OLD": photo},
    )

    assert assembled.findings[0].status == "resolved_after_reinspection"
    assert {image.image_id for image in assembled.images} == {"IMG-NEW", "IMG-OLD"}
    assert "IMG-OLD" in report
    assert "data:image/png;base64," in report


@pytest.mark.parametrize(
    "metadata, error, message",
    [
        ({"inspection_id": " ", "cabinet_id": "CAB-1", "created_at": datetime.now(timezone.utc)}, ValueError, "inspection_id"),
        ({"inspection_id": "INS-1", "cabinet_id": "CAB-1", "created_at": "not-a-time"}, TypeError, "created_at"),
    ],
)
def test_result_assembly_rejects_missing_service_metadata(metadata, error, message):
    with pytest.raises(error, match=message):
        assemble_inspection_result(
            **metadata, findings=[], image_flags={}, image_paths={}, image_urls={}
        )


def test_result_assembly_rejects_missing_urls_and_duplicate_finding_ids(tmp_path):
    photo = tmp_path / "synthetic.png"
    Image.new("RGB", (10, 10), "white").save(photo)
    args = dict(
        inspection_id="INS-1", cabinet_id="CAB-1",
        created_at=datetime.now(timezone.utc), findings=[],
        image_flags={"IMG-1": []}, image_paths={"IMG-1": photo}, image_urls={},
    )
    with pytest.raises(ValueError, match="image_urls IDs"):
        assemble_inspection_result(**args)

    for unsafe_url in ("javascript:alert(1)", "//example.invalid/image", "file:///secret"):
        with pytest.raises(ValueError, match="service-authorized"):
            assemble_inspection_result(
                **{**args, "image_urls": {"IMG-1": unsafe_url}}
            )

    unsafe_prior = ImageInfo.model_construct(
        image_id="IMG-OLD", url="javascript:alert(1)", width=10, height=10,
        quality_flags=[],
    )
    with pytest.raises(ValueError, match="service-authorized"):
        assemble_inspection_result(
            **{**args, "image_urls": {"IMG-1": "/api/images/IMG-1"}},
            prior_images=[unsafe_prior],
        )

    duplicate = _finding("F-1", status="verified")
    with pytest.raises(ValueError, match="unique finding_id"):
        assemble_inspection_result(
            **{**args, "image_urls": {"IMG-1": "/api/images/IMG-1"},
               "findings": [duplicate, duplicate]}
        )
