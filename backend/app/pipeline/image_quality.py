"""Deterministic image-quality checks for cabinet inspection photos."""
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from backend.app.pipeline.thresholds import load_thresholds


def _laplacian_variance(gray: Image.Image) -> float:
    """Compute the population variance of the four-neighbour Laplacian."""
    width, height = gray.size
    if width < 3 or height < 3:
        return 0.0

    pixels = gray.load()
    total = 0
    total_squared = 0
    count = (width - 2) * (height - 2)
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            response = (
                pixels[x - 1, y]
                + pixels[x + 1, y]
                + pixels[x, y - 1]
                + pixels[x, y + 1]
                - 4 * pixels[x, y]
            )
            total += response
            total_squared += response * response
    mean = total / count
    return total_squared / count - mean * mean


def check_photo(path: str | Path, thresholds: dict[str, float] | None = None) -> list[str]:
    """Return quality flags for a readable JPEG or PNG image.

    Missing paths raise ``FileNotFoundError``. Existing but invalid or
    unreadable files raise ``ValueError`` so callers cannot mistake failure to
    inspect an image for a clean quality result.
    """
    settings = load_thresholds(thresholds)
    image_path = Path(path)
    try:
        with Image.open(image_path) as source:
            source.load()
            gray = source.convert("L")
    except FileNotFoundError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"Unable to read inspection image: {image_path}") from exc

    flags: list[str] = []
    width, height = gray.size
    if width < settings["min_photo_width"]:
        flags.append("low_resolution")

    sharpness = _laplacian_variance(gray)
    if sharpness < settings["min_sharpness"]:
        flags.append("low_sharpness")

    histogram = gray.histogram()
    nearly_white_fraction = sum(histogram[251:]) / (width * height)
    if nearly_white_fraction > settings["max_overexposed_fraction"]:
        flags.append("overexposed")
    return flags
