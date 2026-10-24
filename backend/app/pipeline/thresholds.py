"""Load and validate the inspection thresholds stored in config/thresholds.yaml."""
import math
from pathlib import Path
from typing import Any


_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "thresholds.yaml"
_REQUIRED_KEYS = {
    "min_text_confidence",
    "min_detector_confidence",
    "min_photo_width",
    "min_sharpness",
    "max_overexposed_fraction",
}


def load_thresholds(overrides: dict[str, Any] | None = None) -> dict[str, float]:
    """Read this project's simple scalar YAML threshold map and apply overrides."""
    values: dict[str, float] = {}
    try:
        lines = _CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError(f"Unable to read inspection thresholds at {_CONFIG_PATH}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Invalid threshold entry on line {line_number}: {raw_line!r}")
        key, raw_value = (part.strip() for part in line.split(":", 1))
        if not key or not raw_value:
            raise ValueError(f"Invalid threshold entry on line {line_number}: {raw_line!r}")
        if key in values:
            raise ValueError(f"Duplicate threshold {key!r} on line {line_number}")
        if key not in _REQUIRED_KEYS:
            raise ValueError(f"Unknown threshold {key!r} on line {line_number}")
        try:
            values[key] = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Threshold {key!r} on line {line_number} must be numeric") from exc

    missing_keys = _REQUIRED_KEYS - values.keys()
    if missing_keys:
        raise ValueError(f"Threshold file is missing required keys: {', '.join(sorted(missing_keys))}")

    if overrides is not None:
        if not isinstance(overrides, dict):
            raise TypeError("thresholds must be a mapping of threshold names to numeric values")
        for key, value in overrides.items():
            if key not in _REQUIRED_KEYS:
                raise ValueError(f"Unknown threshold {key!r}")
            if isinstance(value, bool):
                raise ValueError(f"Threshold {key!r} must be numeric")
            try:
                values[key] = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Threshold {key!r} must be numeric") from exc

    for key, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"Threshold {key!r} must be finite")
    for key in ("min_text_confidence", "min_detector_confidence", "max_overexposed_fraction"):
        if not 0 <= values[key] <= 1:
            raise ValueError(f"Threshold {key!r} must be between 0 and 1")
    for key in ("min_photo_width", "min_sharpness"):
        if values[key] < 0:
            raise ValueError(f"Threshold {key!r} must not be negative")
    if values["min_photo_width"] < 1:
        raise ValueError("Threshold 'min_photo_width' must be at least 1")
    return values
