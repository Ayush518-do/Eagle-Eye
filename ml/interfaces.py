"""Shared entry points between the ML parts (1 and 2) and the backend (part 3).

Return formats are defined in docs/contracts.md. The backend calls only these
functions, so models can change without touching backend code.
"""


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


def read_tags(image_path: str) -> dict:
    """Part 2: cabinet photo -> contract B with kind='tag_label'."""
    raise ModelUnavailableError("Tag reader not implemented yet (Part 2).")
