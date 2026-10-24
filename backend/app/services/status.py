"""Current finding status and overall status, derived from stored history.

`findings` rows keep the engine's original status forever. The current status of a finding is the
decision of its latest review event, or the original status when it has none. The inspection's
overall status is recomputed from the current statuses; it is never stored back over the engine's
original `inspections.overall_status`.

Rules (the engine's `overall_status()` in pipeline/compare.py is not used here because it counts
every confirmed finding as fine, which would turn a confirmed discrepancy into a pass):
- mismatch: `potential_mismatch`, or `confirmed_by_reviewer` on a finding that reports a
  discrepancy (any type except `verified`).
- ok: `verified`; `resolved_after_reinspection`; `confirmed_by_reviewer` on a `verified` finding
  (the reviewer agrees the part matches); `rejected_by_reviewer` on a reported discrepancy that
  the engine actually asserted (original status other than `inconclusive`).
- everything else is open. A rejected `inconclusive` finding stays open: nobody saw the part, so
  only a reinspection may clear it.
`pass` needs at least one finding and every finding ok; any mismatch gives `mismatch_detected`;
otherwise `review_required`.
"""
from typing import Optional


def current_status(original: str, latest_decision: Optional[str]) -> str:
    return latest_decision or original


def overall_status(findings: list[tuple[str, str, str]]) -> str:
    """`findings` holds (type, original_status, current_status) per finding."""
    verdicts = [_verdict(*f) for f in findings]
    if "mismatch" in verdicts:
        return "mismatch_detected"
    if verdicts and all(v == "ok" for v in verdicts):
        return "pass"
    return "review_required"


def _verdict(type_: str, original: str, current: str) -> str:
    if current == "potential_mismatch":
        return "mismatch"
    if current == "confirmed_by_reviewer":
        return "ok" if type_ == "verified" else "mismatch"
    if current in ("verified", "resolved_after_reinspection"):
        return "ok"
    if current == "rejected_by_reviewer" and type_ != "verified" and original != "inconclusive":
        return "ok"
    return "open"
