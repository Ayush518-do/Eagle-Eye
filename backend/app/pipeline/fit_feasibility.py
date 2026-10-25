"""Missing-component empty slot detection and replacement fit feasibility assessment.

Evaluates whether candidate replacement components from the engineering catalog can
physically and mechanically fit into an empty or missing component position on a DIN rail,
and transparently classifies feasibility (Compatible, Potentially compatible, Incompatible,
or Cannot determine).

SAFETY NOTE: Physical fit feasibility does NOT imply electrical safety or operational
suitability. Protection curves, interrupting ratings, thermal dissipation, and wiring
coordination must always be verified by a qualified electrical engineer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional


FitClassification = Literal[
    "Compatible",
    "Potentially compatible",
    "Incompatible",
    "Cannot determine",
]


@dataclass(frozen=True)
class ComponentSpec:
    part_number: str
    manufacturer: str
    model_name: str
    component_type: str  # e.g. "mcb", "power_supply", "terminal_block", "io_module"
    mounting_type: str  # e.g. "DIN-rail 35mm"
    width_mm: float
    height_mm: float
    depth_mm: float
    pole_count: Optional[int] = None
    rated_voltage: Optional[str] = None
    rated_current_a: Optional[float] = None
    curve: Optional[str] = None
    terminal_clearance_mm: float = 15.0
    description: str = ""


# Standard catalog of approved electrical components based on reference drawings
DEFAULT_CATALOG: dict[str, ComponentSpec] = {
    "A9N2P16C": ComponentSpec(
        part_number="A9N2P16C",
        manufacturer="Schneider Electric",
        model_name="Acti9 C60H-DC",
        component_type="mcb",
        mounting_type="DIN-rail 35mm",
        width_mm=36.0,
        height_mm=81.0,
        depth_mm=73.0,
        pole_count=2,
        rated_voltage="230/400V AC",
        rated_current_a=16.0,
        curve="C",
        terminal_clearance_mm=15.0,
        description="2-pole 16A C-curve miniature circuit breaker",
    ),
    "A9N2P10C": ComponentSpec(
        part_number="A9N2P10C",
        manufacturer="Schneider Electric",
        model_name="Acti9 C60H-DC",
        component_type="mcb",
        mounting_type="DIN-rail 35mm",
        width_mm=36.0,
        height_mm=81.0,
        depth_mm=73.0,
        pole_count=2,
        rated_voltage="230/400V AC",
        rated_current_a=10.0,
        curve="C",
        terminal_clearance_mm=15.0,
        description="2-pole 10A C-curve miniature circuit breaker",
    ),
    "A9N2P06C": ComponentSpec(
        part_number="A9N2P06C",
        manufacturer="Schneider Electric",
        model_name="Acti9 C60H-DC",
        component_type="mcb",
        mounting_type="DIN-rail 35mm",
        width_mm=36.0,
        height_mm=81.0,
        depth_mm=73.0,
        pole_count=2,
        rated_voltage="230/400V AC",
        rated_current_a=6.0,
        curve="C",
        terminal_clearance_mm=15.0,
        description="2-pole 6A C-curve miniature circuit breaker",
    ),
    "S202-C16": ComponentSpec(
        part_number="S202-C16",
        manufacturer="ABB",
        model_name="System pro M compact S200",
        component_type="mcb",
        mounting_type="DIN-rail 35mm",
        width_mm=35.0,
        height_mm=88.0,
        depth_mm=69.0,
        pole_count=2,
        rated_voltage="230/400V AC",
        rated_current_a=16.0,
        curve="C",
        terminal_clearance_mm=15.0,
        description="ABB 2-pole 16A C-curve miniature circuit breaker",
    ),
    "5SY4216-7": ComponentSpec(
        part_number="5SY4216-7",
        manufacturer="Siemens",
        model_name="SENTRON 5SY4",
        component_type="mcb",
        mounting_type="DIN-rail 35mm",
        width_mm=36.0,
        height_mm=90.0,
        depth_mm=76.0,
        pole_count=2,
        rated_voltage="400V AC",
        rated_current_a=16.0,
        curve="C",
        terminal_clearance_mm=15.0,
        description="Siemens 2-pole 16A C-curve MCB 10kA",
    ),
    "VE5127": ComponentSpec(
        part_number="VE5127",
        manufacturer="Emerson",
        model_name="Bulk Power Supply 24VDC 20A",
        component_type="power_supply",
        mounting_type="DIN-rail 35mm",
        width_mm=85.0,
        height_mm=125.0,
        depth_mm=120.0,
        pole_count=None,
        rated_voltage="24V DC",
        rated_current_a=20.0,
        curve=None,
        terminal_clearance_mm=25.0,
        description="Bulk industrial 24V DC 20A power supply module",
    ),
    "QUINT4-PS/24DC/20A": ComponentSpec(
        part_number="2904602",
        manufacturer="Phoenix Contact",
        model_name="QUINT4-PS/24DC/20A",
        component_type="power_supply",
        mounting_type="DIN-rail 35mm",
        width_mm=70.0,
        height_mm=130.0,
        depth_mm=125.0,
        pole_count=None,
        rated_voltage="24V DC",
        rated_current_a=20.0,
        curve=None,
        terminal_clearance_mm=25.0,
        description="Primary-switched power supply QUINT POWER 24V DC / 20A",
    ),
    "3001501": ComponentSpec(
        part_number="3001501",
        manufacturer="Phoenix Contact",
        model_name="UK 3 N",
        component_type="terminal_block",
        mounting_type="DIN-rail 35mm",
        width_mm=5.2,
        height_mm=42.5,
        depth_mm=47.0,
        pole_count=1,
        rated_voltage="800V",
        rated_current_a=32.0,
        curve=None,
        terminal_clearance_mm=5.0,
        description="Feed-through modular terminal block, 2.5 mm2",
    ),
}


@dataclass
class CandidateAssessment:
    candidate_part_number: str
    manufacturer: str
    model_name: str
    classification: FitClassification
    reasons: list[str]
    evaluated_constraints: dict[str, str]
    reference_values: dict[str, Any]
    measured_values: dict[str, Any]
    uncertainty_notes: list[str]
    safety_disclaimer: str = (
        "Physical fit feasibility check only. Physical fit does NOT imply electrical safety, "
        "thermal suitability, or protection coordination. Verify electrical specifications with a "
        "qualified engineer before installation."
    )


@dataclass
class EmptyPositionFitReport:
    finding_id: str
    tag: str
    component_type: str
    expected_part_number: Optional[str]
    slot_status: str  # "unoccupied_verified", "unoccupied_inconclusive", "occluded"
    available_width_mm: Optional[float]
    available_height_mm: Optional[float]
    available_depth_mm: Optional[float]
    mounting_type: str
    scale_calibration: str  # "reference_drawing_bom", "pixel_calibrated", "uncalibrated"
    candidates: list[CandidateAssessment]


def evaluate_candidate_fit(
    expected_spec: Optional[ComponentSpec],
    candidate: ComponentSpec,
    available_width_mm: Optional[float] = None,
    available_height_mm: Optional[float] = None,
    available_depth_mm: Optional[float] = None,
    mounting_type: str = "DIN-rail 35mm",
    has_image_calibration: bool = True,
    image_blurry: bool = False,
) -> CandidateAssessment:
    """Evaluate physical, mechanical, and electrical compatibility constraints for a candidate component."""
    reasons: list[str] = []
    evaluated_constraints: dict[str, str] = {}
    reference_values: dict[str, Any] = {
        "candidate_width_mm": candidate.width_mm,
        "candidate_height_mm": candidate.height_mm,
        "candidate_depth_mm": candidate.depth_mm,
        "candidate_mounting": candidate.mounting_type,
        "candidate_type": candidate.component_type,
    }
    measured_values: dict[str, Any] = {}
    uncertainty_notes: list[str] = []

    if image_blurry:
        uncertainty_notes.append("Supporting photo has low sharpness; visual slot clearance may be uncertain.")

    if not has_image_calibration:
        uncertainty_notes.append("Image pixel-to-mm scale is uncalibrated. Physical checks rely on reference drawing & BOM data.")

    # 1. Component type check
    if expected_spec and expected_spec.component_type != candidate.component_type:
        reasons.append(
            f"Component type mismatch: expected '{expected_spec.component_type}', candidate is '{candidate.component_type}'."
        )
        evaluated_constraints["component_type"] = "FAIL"
        return CandidateAssessment(
            candidate_part_number=candidate.part_number,
            manufacturer=candidate.manufacturer,
            model_name=candidate.model_name,
            classification="Incompatible",
            reasons=reasons,
            evaluated_constraints=evaluated_constraints,
            reference_values=reference_values,
            measured_values=measured_values,
            uncertainty_notes=uncertainty_notes,
        )
    evaluated_constraints["component_type"] = "PASS"

    # 2. Mounting compatibility
    if candidate.mounting_type.lower() != mounting_type.lower():
        reasons.append(
            f"Mounting incompatibility: candidate requires '{candidate.mounting_type}', rail is '{mounting_type}'."
        )
        evaluated_constraints["mounting"] = "FAIL"
        return CandidateAssessment(
            candidate_part_number=candidate.part_number,
            manufacturer=candidate.manufacturer,
            model_name=candidate.model_name,
            classification="Incompatible",
            reasons=reasons,
            evaluated_constraints=evaluated_constraints,
            reference_values=reference_values,
            measured_values=measured_values,
            uncertainty_notes=uncertainty_notes,
        )
    evaluated_constraints["mounting"] = "PASS"

    # 3. Physical width check
    width_limit = available_width_mm or (expected_spec.width_mm if expected_spec else None)
    if width_limit is not None:
        reference_values["slot_width_limit_mm"] = width_limit
        if candidate.width_mm <= width_limit + 1.0:  # 1mm tolerance
            evaluated_constraints["width"] = f"PASS ({candidate.width_mm}mm <= {width_limit}mm)"
        else:
            reasons.append(
                f"Physical width ({candidate.width_mm}mm) exceeds available slot width ({width_limit}mm)."
            )
            evaluated_constraints["width"] = f"FAIL ({candidate.width_mm}mm > {width_limit}mm)"
            return CandidateAssessment(
                candidate_part_number=candidate.part_number,
                manufacturer=candidate.manufacturer,
                model_name=candidate.model_name,
                classification="Incompatible",
                reasons=reasons,
                evaluated_constraints=evaluated_constraints,
                reference_values=reference_values,
                measured_values=measured_values,
                uncertainty_notes=uncertainty_notes,
            )
    else:
        evaluated_constraints["width"] = "UNVERIFIED (slot width not specified in reference)"
        uncertainty_notes.append("Available rail slot width was not explicitly constrained by reference data.")

    # 4. Height & Depth clearance
    if available_height_mm is not None:
        if candidate.height_mm > available_height_mm:
            reasons.append(f"Height ({candidate.height_mm}mm) exceeds rail duct clearance ({available_height_mm}mm).")
            evaluated_constraints["height"] = "FAIL"
            return CandidateAssessment(
                candidate_part_number=candidate.part_number,
                manufacturer=candidate.manufacturer,
                model_name=candidate.model_name,
                classification="Incompatible",
                reasons=reasons,
                evaluated_constraints=evaluated_constraints,
                reference_values=reference_values,
                measured_values=measured_values,
                uncertainty_notes=uncertainty_notes,
            )
        evaluated_constraints["height"] = "PASS"
    else:
        evaluated_constraints["height"] = "PASS (Standard DIN rail duct clearance assumed)"

    if available_depth_mm is not None:
        if candidate.depth_mm > available_depth_mm:
            reasons.append(f"Depth ({candidate.depth_mm}mm) exceeds cabinet door clearance ({available_depth_mm}mm).")
            evaluated_constraints["depth"] = "FAIL"
            return CandidateAssessment(
                candidate_part_number=candidate.part_number,
                manufacturer=candidate.manufacturer,
                model_name=candidate.model_name,
                classification="Incompatible",
                reasons=reasons,
                evaluated_constraints=evaluated_constraints,
                reference_values=reference_values,
                measured_values=measured_values,
                uncertainty_notes=uncertainty_notes,
            )
        evaluated_constraints["depth"] = "PASS"
    else:
        evaluated_constraints["depth"] = "PASS (Standard DIN cabinet enclosure depth assumed)"

    # 5. Pole count and electrical specifications (where expected spec is known)
    if expected_spec:
        if expected_spec.pole_count is not None and candidate.pole_count is not None:
            if expected_spec.pole_count != candidate.pole_count:
                reasons.append(
                    f"Pole count mismatch: expected {expected_spec.pole_count}P, candidate is {candidate.pole_count}P."
                )
                evaluated_constraints["pole_count"] = "FAIL"
                return CandidateAssessment(
                    candidate_part_number=candidate.part_number,
                    manufacturer=candidate.manufacturer,
                    model_name=candidate.model_name,
                    classification="Incompatible",
                    reasons=reasons,
                    evaluated_constraints=evaluated_constraints,
                    reference_values=reference_values,
                    measured_values=measured_values,
                    uncertainty_notes=uncertainty_notes,
                )
            evaluated_constraints["pole_count"] = "PASS"

        if expected_spec.rated_current_a is not None and candidate.rated_current_a is not None:
            reference_values["expected_current_a"] = expected_spec.rated_current_a
            reference_values["candidate_current_a"] = candidate.rated_current_a
            if expected_spec.rated_current_a != candidate.rated_current_a:
                reasons.append(
                    f"Rated current differs: drawing specifies {expected_spec.rated_current_a}A, candidate is {candidate.rated_current_a}A."
                )
                evaluated_constraints["rated_current"] = (
                    f"POTENTIAL (Rated {candidate.rated_current_a}A vs expected {expected_spec.rated_current_a}A)"
                )
            else:
                evaluated_constraints["rated_current"] = f"PASS ({candidate.rated_current_a}A matches drawing)"

    # Determine classification
    if not has_image_calibration or any("UNVERIFIED" in str(v) for v in evaluated_constraints.values()):
        classification: FitClassification = "Potentially compatible"
        reasons.append(
            f"Candidate '{candidate.model_name}' physically fits DIN rail envelope; depth/electrical rating check required."
        )
    elif any("POTENTIAL" in str(v) for v in evaluated_constraints.values()):
        classification = "Potentially compatible"
        reasons.append(
            f"Candidate '{candidate.model_name}' fits mechanical envelope but has rating differences requiring engineering approval."
        )
    else:
        classification = "Compatible"
        reasons.append(
            f"Candidate '{candidate.model_name}' satisfies all evaluated physical, mounting, and specification constraints."
        )

    return CandidateAssessment(
        candidate_part_number=candidate.part_number,
        manufacturer=candidate.manufacturer,
        model_name=candidate.model_name,
        classification=classification,
        reasons=reasons,
        evaluated_constraints=evaluated_constraints,
        reference_values=reference_values,
        measured_values=measured_values,
        uncertainty_notes=uncertainty_notes,
    )


def assess_empty_position(
    finding_id: str,
    tag: str,
    component_type: str = "mcb",
    expected_part_number: Optional[str] = None,
    expected_rating_str: Optional[str] = None,
    image_flags: Optional[list[str]] = None,
    catalog: Optional[dict[str, ComponentSpec]] = None,
) -> EmptyPositionFitReport:
    """Analyze a candidate empty/missing component slot and evaluate replacement options from the catalog."""
    cat = catalog or DEFAULT_CATALOG
    flags = image_flags or []
    is_blurry = "low_sharpness" in flags

    # Find expected component specification if known in catalog
    expected_spec: Optional[ComponentSpec] = None
    if expected_part_number and expected_part_number in cat:
        expected_spec = cat[expected_part_number]
    elif tag.upper().startswith("CB") or tag.upper().startswith("DS"):
        expected_spec = cat.get("A9N2P16C")
    elif tag.upper().startswith("PS"):
        expected_spec = cat.get("VE5127")
    elif tag.upper().startswith("X"):
        expected_spec = cat.get("3001501")

    # Evaluate candidate replacements of the same component family
    target_type = (expected_spec.component_type if expected_spec else component_type).lower()
    candidates: list[CandidateAssessment] = []

    for cand in cat.values():
        if cand.component_type.lower() != target_type:
            continue
        assessment = evaluate_candidate_fit(
            expected_spec=expected_spec,
            candidate=cand,
            available_width_mm=expected_spec.width_mm if expected_spec else None,
            mounting_type=expected_spec.mounting_type if expected_spec else "DIN-rail 35mm",
            has_image_calibration=False,  # transparently mark image calibration as uncalibrated
            image_blurry=is_blurry,
        )
        candidates.append(assessment)

    # Sort: Compatible first, then Potentially compatible, then Incompatible
    order = {"Compatible": 0, "Potentially compatible": 1, "Cannot determine": 2, "Incompatible": 3}
    candidates.sort(key=lambda c: order.get(c.classification, 99))

    return EmptyPositionFitReport(
        finding_id=finding_id,
        tag=tag,
        component_type=target_type,
        expected_part_number=expected_part_number,
        slot_status="unoccupied_inconclusive" if is_blurry else "unoccupied_verified",
        available_width_mm=expected_spec.width_mm if expected_spec else None,
        available_height_mm=expected_spec.height_mm if expected_spec else None,
        available_depth_mm=expected_spec.depth_mm if expected_spec else None,
        mounting_type=expected_spec.mounting_type if expected_spec else "DIN-rail 35mm",
        scale_calibration="reference_drawing_bom",
        candidates=candidates,
    )
