"""Dependency-free parsing for the rating text forms in contract v0.2."""

import re


_AMP_RATING = re.compile(r"([0-9]+) ?A")
_BREAKER_RATING = re.compile(r"C([0-9]+)")
_DC_VOLTAGE = re.compile(r"([0-9]+)VDC")


def normalise_rating(text: str | None) -> tuple[str, float] | None:
    """Parse only the rating forms documented in the inspection-engine task."""
    if not isinstance(text, str):
        return None

    match = _AMP_RATING.fullmatch(text)
    if match:
        return "A", float(match.group(1))

    match = _BREAKER_RATING.fullmatch(text)
    if match:
        return "A", float(match.group(1))

    match = _DC_VOLTAGE.fullmatch(text)
    if match:
        return "V", float(match.group(1))

    return None
