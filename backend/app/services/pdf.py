"""Structural check for drawing PDFs, using only the standard library.

A PDF is accepted when it starts with a `%PDF-x.y` header and ends with `startxref <offset>
%%EOF`, and the offset points at a cross-reference table (`xref`) or a cross-reference stream
object. That catches truncated and cut-off files and non-PDF data with a PDF signature.

Not checked: that the pages parse or render, that the cross-reference table is correct, or that
the content is a real drawing. No PDF library is a declared backend dependency. Strict on
purpose: anything but whitespace after the final `%%EOF`, or junk before the header, is rejected
as damaged, because a file cut off inside a later section would otherwise still look complete.
"""
import re

from backend.app.services.storage import UploadRejected

_HEADER = re.compile(rb"%PDF-\d\.\d")
_TRAILER = re.compile(rb"startxref\s+(\d+)\s+%%EOF[\s\x00]*\Z")
_XREF_TARGET = re.compile(rb"(xref|\d+\s+\d+\s+obj)")
TAIL_BYTES = 2048

DAMAGED = "The drawing is damaged or truncated (it is not a complete PDF file)."


def check_pdf(data: bytes) -> None:
    """Raise UploadRejected if `data` is not structurally a complete PDF."""
    if not _HEADER.match(data[:8]):
        raise UploadRejected(DAMAGED)
    trailer = _TRAILER.search(data[-TAIL_BYTES:])
    if trailer is None:
        raise UploadRejected(DAMAGED)
    offset = int(trailer.group(1))
    if not 0 < offset < len(data) or not _XREF_TARGET.match(data[offset:offset + 60].lstrip()):
        raise UploadRejected(DAMAGED)
