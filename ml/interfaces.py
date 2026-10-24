"""Shared entry points between the ML parts (1 and 2) and the backend (part 3).

Return formats are defined in docs/contracts.md. The backend calls only these
functions, so models can change without touching backend code.
"""

from collections.abc import Iterable


class ModelUnavailableError(RuntimeError):
    """Raised when a model or its weights are not configured.

    Callers must show this message to the user; never replace it with made-up output.
    """


def parse_drawing(pdf_path: str) -> dict:
    """Part 2: drawing PDF -> contract A (expected items)."""
    raise ModelUnavailableError("Drawing parser not implemented yet (Part 2).")


def detect_components(image_path: str) -> dict:
    """Part 1: cabinet photo -> contract B with kind='component'."""
    raise ModelUnavailableError("Component detector not configured yet (Part 1).")


def read_tags(
    image_path: str,
    expected_tags: Iterable[str] | None = None,
    image_id: str | None = None,
) -> dict:
    """Return OCR observations, optionally resolving labels against drawing tags.

    ``expected_tags`` is optional for compatibility with existing one-argument
    callers. Supplying drawing tags enables conservative lookalike matching;
    unresolved and ambiguous text remains uncorrected for review. ``image_id``
    allows the producer to preserve the service's image key instead of deriving
    it from the path stem.
    """
    from ml.ocr.read_tags import read_tags as read_tags_for_image

    return read_tags_for_image(
        image_path,
        expected=expected_tags,
        image_id=image_id,
    )
