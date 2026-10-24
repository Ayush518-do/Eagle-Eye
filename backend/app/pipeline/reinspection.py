"""Conservative comparison of findings across two inspections."""

from collections.abc import Iterable
import json
from uuid import uuid4

from backend.app.schemas import Finding


def _normalise_tag(tag: str | None) -> str | None:
    if not tag:
        return None
    return "".join(character for character in tag.upper() if character.isalnum())


def _finding_identity(finding: Finding) -> tuple[str, str | None, str | None, str | None]:
    """Identity from semantic fields; list position and finding_id are per-run."""
    return (
        finding.type,
        _normalise_tag(finding.tag),
        finding.expected_value,
        finding.observed_text,
    )


def _canonical_finding_key(finding: Finding) -> str:
    """Stable tie-breaker for malformed duplicate IDs; not semantic matching."""
    return json.dumps(finding.model_dump(exclude={"finding_id"}), sort_keys=True, default=str)


def _is_verified_resolution(
    old: Finding,
    new: Finding,
    assessed_image_ids: set[str] | None,
) -> bool:
    """Return true only when new evidence verifies the same resolvable issue."""
    if (
        new.status != "verified"
        or not new.evidence
        or assessed_image_ids is None
        or not old.tag
        or _normalise_tag(old.tag) != _normalise_tag(new.tag)
        or any(evidence.image_id not in assessed_image_ids for evidence in new.evidence)
    ):
        return False

    # A verified tag read resolves an earlier inconclusive absence or unexpected
    # tag. It does not establish a rating or placement check, so those findings
    # require an explicitly verified finding of their own type.
    if old.type in {"missing", "unexpected"}:
        return new.type == "verified"
    if old.type in {"rating_mismatch", "misplaced"}:
        return (
            new.type == old.type
            and new.expected_value == old.expected_value
        )
    return False


def compare_with_previous(
    old_findings: Iterable[Finding],
    new_findings: Iterable[Finding],
    *,
    assessed_image_ids: set[str] | None = None,
) -> list[Finding]:
    """Keep prior findings, resolve only verified issues, and append new ones.

    Findings without a stable tag identity remain open. A current inspection's
    per-run ``finding_id`` and list ordering are not used for matching. The
    optional assessment IDs must come from the current engine quality pass;
    omitting them makes this helper fail closed and leaves prior issues open.
    """
    previous = list(old_findings)
    current = list(new_findings)
    matched_current: set[int] = set()
    identities = {_finding_identity(finding) for finding in previous}
    result: list[Finding] = []

    # Preserve valid prior IDs. If malformed input reuses an ID, choose a
    # canonical semantic owner so reordering does not change which issue keeps it.
    old_ids = {finding.finding_id for finding in previous}
    duplicate_old_ids = {
        finding_id for finding_id in old_ids
        if sum(item.finding_id == finding_id for item in previous) > 1
    }
    canonical_owner = {
        finding_id: min(
            (item for item in previous if item.finding_id == finding_id),
            key=_canonical_finding_key,
        )
        for finding_id in duplicate_old_ids
    }
    used_ids: set[str] = set()
    allocated_previous: list[Finding] = []
    for old in previous:
        if old.finding_id not in used_ids and (
            old.finding_id not in duplicate_old_ids or old is canonical_owner[old.finding_id]
        ):
            allocated = old
        else:
            allocated = old.model_copy(update={"finding_id": _new_finding_id(used_ids | old_ids)})
        used_ids.add(allocated.finding_id)
        allocated_previous.append(allocated)

    candidates_by_old = {
        old_index: [
            new_index
            for new_index, new in enumerate(current)
            if _is_verified_resolution(old, new, assessed_image_ids)
        ]
        for old_index, old in enumerate(allocated_previous)
    }
    owners_by_new: dict[int, list[int]] = {}
    for old_index, candidates in candidates_by_old.items():
        for new_index in candidates:
            owners_by_new.setdefault(new_index, []).append(old_index)
    resolving_pairs = {
        old_index: candidates[0]
        for old_index, candidates in candidates_by_old.items()
        if len(candidates) == 1 and len(owners_by_new[candidates[0]]) == 1
    }
    ambiguous_current = {
        new_index
        for old_index, candidates in candidates_by_old.items()
        if len(candidates) > 1
        for new_index in candidates
    } | {
        new_index
        for new_index, owners in owners_by_new.items()
        if len(owners) > 1
    }
    output_current = list(current)
    for index in ambiguous_current:
        finding = output_current[index]
        reason = finding.reason
        ambiguity_note = "Reinspection evidence is ambiguous; the earlier finding remains unresolved."
        output_current[index] = finding.model_copy(update={
            "status": "needs_review",
            "reason": f"{reason} {ambiguity_note}".strip() if reason else ambiguity_note,
        })

    for old_index, old in enumerate(allocated_previous):
        resolving_index = resolving_pairs.get(old_index)
        if resolving_index is not None:
            matched_current.add(resolving_index)
            identities.add(_finding_identity(current[resolving_index]))
            result.append(old.model_copy(update={"status": "resolved_after_reinspection"}))
        else:
            result.append(old)

    for index, new in enumerate(output_current):
        if index in matched_current:
            continue
        identity = _finding_identity(new)
        if identity not in identities:
            new_id = new.finding_id
            if new_id in used_ids:
                new = new.model_copy(update={"finding_id": _new_finding_id(used_ids | old_ids)})
            used_ids.add(new.finding_id)
            result.append(new)
            identities.add(identity)

    return result


def _new_finding_id(occupied: set[str]) -> str:
    """Allocate a unique ID without using it to infer semantic identity."""
    while True:
        candidate = f"F-RI-{uuid4().hex}"
        if candidate not in occupied:
            return candidate
