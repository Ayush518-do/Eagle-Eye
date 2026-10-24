"""Replace the expected items of a design revision (Contract A), all or nothing.

This is the data-layer rule behind `POST /api/design-revisions/{id}/expected-items`; the
endpoint itself is not built yet. The caller owns the transaction and commits.

Rules:
- The new list replaces the old one; items are never appended to it.
- Replacement is atomic: if any new item cannot be stored, the session is rolled back and the
  old list is untouched. (SQLite savepoints are not used; the driver does not honour them reliably.)
- `drawing_file_sha256`, when given, must equal the PDF hash stored on the revision.
- `parser_version`, when given, replaces the stored value; when omitted (a manual list),
  the stored value is kept.
"""
from typing import Optional

from sqlalchemy import delete, literal_column, select
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas import CONTRACT_VERSION, ExpectedItem, ExpectedItemsSubmission


class ExpectedItemsError(Exception):
    """A client error. `status_code` and `detail` follow the API's {"detail": ...} convention."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _row(revision_id: str, item: ExpectedItem) -> models.ExpectedItem:
    rating = item.rating
    return models.ExpectedItem(
        design_revision_id=revision_id,
        tag=item.tag.strip(),  # surrounding whitespace is dropped, case is kept
        part_number=item.part_number,
        description=item.description,
        quantity=item.quantity,
        rating_value=rating.value if rating else None,
        rating_needs_review=rating.needs_review if rating else False,
        rating_source=rating.source if rating else None,
        rating_page=rating.page if rating else None,
        source_page=item.source_page,
    )


def replace_expected_items(
    session: Session,
    design_revision_id: str,
    items: list[ExpectedItem],
    *,
    parser_version: Optional[str] = None,
    drawing_file_sha256: Optional[str] = None,
) -> list[models.ExpectedItem]:
    revision = session.get(models.DesignRevision, design_revision_id)
    if revision is None:
        raise ExpectedItemsError(404, "Design revision not found.")

    if drawing_file_sha256 is not None:
        if not revision.drawing_sha256:
            # Never report a check as passed when there is nothing to check against.
            raise ExpectedItemsError(
                409, "This design revision has no stored drawing hash, so drawing_file_sha256 "
                     "cannot be verified.")
        if drawing_file_sha256.strip().lower() != revision.drawing_sha256.lower():
            raise ExpectedItemsError(
                409, "drawing_file_sha256 does not match the drawing uploaded for this design revision.")

    if parser_version is not None and not parser_version.strip():
        raise ExpectedItemsError(400, "parser_version must not be blank when it is given.")

    if any(not item.tag.strip() for item in items):  # checked before anything is deleted
        raise ExpectedItemsError(400, "Tags must not be blank.")
    repeated = duplicate_tags(items)
    if repeated:
        raise ExpectedItemsError(400, "Duplicate tags in this submission: " + ", ".join(repeated) + ".")

    try:
        session.execute(delete(models.ExpectedItem).where(
            models.ExpectedItem.design_revision_id == design_revision_id))
        rows = [_row(design_revision_id, item) for item in items]
        session.add_all(rows)
        if parser_version is not None:
            revision.parser_version = parser_version.strip()
        session.flush()
    except Exception:
        session.rollback()  # the delete and any partial insert are undone; the old list stays
        raise
    return rows


def duplicate_tags(items: list[ExpectedItem]) -> list[str]:
    """Tags that occur more than once after trimming and ignoring case (first spelling, in order)."""
    seen: dict[str, str] = {}
    repeated: set[str] = set()
    for item in items:
        shown = item.tag.strip()
        key = shown.casefold()
        if key in seen:
            repeated.add(key)
        else:
            seen[key] = shown
    return [shown for key, shown in seen.items() if key in repeated]  # order of first appearance


def replace_from_submission(
    session: Session, design_revision_id: str, submission: ExpectedItemsSubmission
) -> list[models.ExpectedItem]:
    """What the endpoint calls. Validates the contract version, then replaces the list.
    The caller commits on success; on any error nothing has been committed."""
    if submission.contract_version != CONTRACT_VERSION:
        raise ExpectedItemsError(
            400, f"Unsupported contract_version {submission.contract_version!r}; "
                 f"this server supports {CONTRACT_VERSION!r}.")
    return replace_expected_items(
        session, design_revision_id, submission.items,
        parser_version=submission.parser_version,
        drawing_file_sha256=submission.drawing_file_sha256,
    )


def list_expected_items(session: Session, design_revision_id: str) -> list[models.ExpectedItem]:
    return list(session.scalars(
        select(models.ExpectedItem).where(models.ExpectedItem.design_revision_id == design_revision_id)
        .order_by(literal_column("rowid"))))  # insertion order
