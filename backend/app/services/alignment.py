"""Ghost overlay helpers (Contract E): save per-image alignments, render drawing pages,
project expected-item boxes from PDF points into photo pixels.

A 4-point homography maps points on the drawing (PDF points on a given page) to pixels on the
photo. We store the four corresponding corners; the projection matrix is recomputed on each
request so the stored data stays small and easy to inspect.
"""
from __future__ import annotations

from io import BytesIO
from typing import Iterable, Optional

import numpy as np

from backend.app import models

Point = list[float]


def validate_points(points: list[list[float]], where: str) -> list[Point]:
    """Four 2D points with real numbers. Raises ValueError on any defect."""
    if not isinstance(points, list) or len(points) != 4:
        raise ValueError(f"{where} must have exactly 4 points.")
    cleaned: list[Point] = []
    for i, p in enumerate(points):
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError(f"{where}[{i}] must be a pair [x, y].")
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            raise ValueError(f"{where}[{i}] has non-numeric coordinates.")
        if not (np.isfinite(x) and np.isfinite(y)):
            raise ValueError(f"{where}[{i}] has non-finite coordinates.")
        cleaned.append([x, y])
    return cleaned


def _homography(src: list[Point], dst: list[Point]) -> np.ndarray:
    """4-point homography from src to dst. Uses cv2 when available; falls back to numpy."""
    try:
        import cv2  # type: ignore
        src_arr = np.array(src, dtype=np.float32)
        dst_arr = np.array(dst, dtype=np.float32)
        return cv2.getPerspectiveTransform(src_arr, dst_arr)
    except Exception:
        # Minimal 4-point solver: build the 8x8 linear system and solve.
        A = []
        b = []
        for (sx, sy), (dx, dy) in zip(src, dst):
            A.append([sx, sy, 1, 0, 0, 0, -sx * dx, -sy * dx])
            A.append([0, 0, 0, sx, sy, 1, -sx * dy, -sy * dy])
            b.extend([dx, dy])
        h, _, _, _ = np.linalg.lstsq(np.array(A), np.array(b), rcond=None)
        H = np.array([[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]])
        return H


def project_bbox_drawing_to_photo(
    alignment: models.ImageAlignment, bbox: list[float]
) -> Optional[list[float]]:
    """Map a bbox given in PDF points to original-photo pixels. Returns None on failure."""
    if alignment is None or bbox is None or len(bbox) != 4:
        return None
    try:
        H = _homography(alignment.drawing_points, alignment.photo_points)
        corners = np.array(
            [[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]],
            dtype=np.float64,
        )
        ones = np.ones((4, 1))
        homog = np.hstack([corners, ones])
        projected = (H @ homog.T).T
        w = projected[:, 2:3]
        w[w == 0] = 1e-9
        xy = projected[:, :2] / w
        x1 = float(np.min(xy[:, 0]))
        y1 = float(np.min(xy[:, 1]))
        x2 = float(np.max(xy[:, 0]))
        y2 = float(np.max(xy[:, 1]))
        if not (np.isfinite(x1) and np.isfinite(y1) and np.isfinite(x2) and np.isfinite(y2)):
            return None
        if x2 <= x1 or y2 <= y1:
            return None
        return [x1, y1, x2, y2]
    except Exception:
        return None


def render_drawing_page_png(pdf_bytes: bytes, page_index: int, width: int) -> tuple[bytes, tuple[float, float]]:
    """Render page `page_index` (1-based) of `pdf_bytes` to a PNG at the given pixel width.

    Returns (png_bytes, (page_width_points, page_height_points)).
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        if not (1 <= page_index <= len(pdf)):
            raise ValueError(f"Page {page_index} is outside the document (1..{len(pdf)}).")
        page = pdf[page_index - 1]
        try:
            page_w_pts, page_h_pts = page.get_size()
            scale = max(1.0, float(width) / float(page_w_pts))
            bitmap = page.render(scale=scale)
            pil = bitmap.to_pil()
            buf = BytesIO()
            pil.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), (float(page_w_pts), float(page_h_pts))
        finally:
            page.close()
    finally:
        pdf.close()


def ghost_boxes_for_image(
    alignment: Optional[models.ImageAlignment],
    expected_items: Iterable,
    finding_status_by_tag: dict[str, str],
) -> list[dict]:
    """Project expected-item layout bboxes onto one photo. Items without a layout, or on a
    different drawing page than the saved alignment, are left out.
    """
    if alignment is None:
        return []
    out: list[dict] = []
    for item in expected_items:
        layout = getattr(item, "layout", None) or (item.get("layout") if isinstance(item, dict) else None)
        if not layout:
            continue
        page = layout.get("page")
        bbox = layout.get("bbox")
        if page != alignment.drawing_page or not bbox:
            continue
        projected = project_bbox_drawing_to_photo(alignment, bbox)
        if projected is None:
            continue
        tag = getattr(item, "tag", None) or (item.get("tag") if isinstance(item, dict) else None)
        out.append({
            "tag": tag,
            "bbox": projected,
            "status": finding_status_by_tag.get(tag, "needs_review"),
        })
    return out
