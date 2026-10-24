"""Photo validation: what is checked before a photo is accepted.

PNG  - signature, every chunk's CRC, IHDR values, IDAT/IEND present, and the compressed pixel
       stream inflates to exactly the size the header promises (standard library only).
JPEG - a strict walk through the file's markers (frame header, every scan, the end-of-image
       marker, no invalid marker inside the compressed scan data), then a full decode with Pillow
       (`Image.load()`), and the decoded format and size must agree with what was detected.

Decoding means the file is a complete, decodable image. It does not mean the photo is sharp, shows
a real electrical cabinet, or has not been altered. Quality (blur, glare) is not measured: stored
images carry the flag `quality_not_measured`, so an empty list is never read as "no problems".

Known limit: libjpeg conceals many errors inside a complete scan (zeroed, garbage or bit-flipped
pixel data still decodes, to a distorted picture). Neither Pillow nor this module can detect that,
because a JPEG carries no checksum. Truncation, missing or invalid markers, wrong dimensions and
non-JPEG data are detected.

Size limits (pixel count and decoded bytes) stop a small hostile file from forcing a huge
allocation: they are checked from the headers before any pixel is decoded.
"""
import io
import struct
import zlib

from PIL import Image

from backend.app.services.storage import UploadRejected

QUALITY_NOT_MEASURED = "quality_not_measured"
# Pillow's own default decompression-bomb threshold (1 GiB / 4 / 3 bytes): about 9400 x 9400 pixels,
# far above any camera used for cabinet photos. Decoding such an image needs roughly 270 MB.
MAX_PIXELS = 89_478_485
MAX_DECODED_BYTES = 256 * 1024 * 1024  # what a PNG's pixel stream may inflate to

_DAMAGED = "The file is damaged or truncated, or is not a readable image."
_TOO_LARGE = f"The image has more than {MAX_PIXELS // 1_000_000} million pixels, which is the limit."
_TOO_LARGE_DECODED = f"The image is too large to check safely (over {MAX_DECODED_BYTES // (1024 * 1024)} MB decoded)."


def image_size(data: bytes, content_type: str) -> tuple[int, int]:
    """Validate a PNG or JPEG and return (width, height). Raises UploadRejected otherwise."""
    if content_type == "image/png":
        size = _check_png(data)
    elif content_type == "image/jpeg":
        size = _check_jpeg(data)
    else:
        raise UploadRejected("Only JPEG and PNG photos are accepted.")
    if size is None or size[0] <= 0 or size[1] <= 0:
        raise UploadRejected(_DAMAGED)
    if size[0] * size[1] > MAX_PIXELS:
        raise UploadRejected(_TOO_LARGE)
    if content_type == "image/jpeg":
        _decode_jpeg(data, size)  # only after the size limit, so a lying header cannot force a big buffer
    return size


# ---------- JPEG: full decode ----------
def _decode_jpeg(data: bytes, expected_size: tuple[int, int]) -> None:
    try:
        # MAX_PIXELS equals Pillow's warning threshold, so Pillow's decompression-bomb warning and
        # error cannot trigger for a file that got this far; if they ever do, the error is caught below.
        with Image.open(io.BytesIO(data), formats=["JPEG"]) as image:
            # Phone photos with extra frames are reported as MPO; the first frame is a JPEG.
            if image.format not in ("JPEG", "MPO") or image.size != expected_size:
                raise UploadRejected(_DAMAGED)
            image.load()  # forces the pixel data to be decoded; a truncated file raises here
    except UploadRejected:
        raise
    except Exception:  # Pillow raises OSError, SyntaxError, ValueError, MemoryError, ... for bad files
        raise UploadRejected(_DAMAGED) from None


# ---------- PNG ----------
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _check_png(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(_PNG_SIGNATURE):
        return None
    pos, n = 8, len(data)
    header = None
    idat = bytearray()
    ended = False
    while pos + 12 <= n:
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > n:
            return None  # chunk runs past the end of the file
        body = data[pos + 8:pos + 8 + length]
        if zlib.crc32(kind + body) != struct.unpack(">I", data[end - 4:end])[0]:
            return None
        if header is None:
            if kind != b"IHDR" or length != 13:
                return None
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IHDR":
            return None
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            ended = True
            break
        pos = end
    if header is None or not ended or not idat:
        return None
    width, height, depth, color, compression, filtering, interlace = header
    if (width <= 0 or height <= 0 or compression != 0 or filtering != 0
            or interlace not in (0, 1) or depth not in _DEPTHS.get(color, ())):
        return None
    if width * height > MAX_PIXELS:
        raise UploadRejected(_TOO_LARGE)
    bits_per_pixel = _CHANNELS[color] * depth
    expected = _png_stream_size(width, height, bits_per_pixel, interlace)
    if expected > MAX_DECODED_BYTES:
        raise UploadRejected(_TOO_LARGE_DECODED)
    inflater = zlib.decompressobj()
    try:
        pixels = inflater.decompress(bytes(idat), expected + 1)
    except zlib.error:
        return None
    if len(pixels) != expected or not inflater.eof or inflater.unused_data:
        return None
    return width, height


def _png_stream_size(width: int, height: int, bits_per_pixel: int, interlace: int) -> int:
    passes = _ADAM7 if interlace else ((0, 0, 1, 1),)
    total = 0
    for x0, y0, dx, dy in passes:
        w = (width - x0 + dx - 1) // dx if width > x0 else 0
        h = (height - y0 + dy - 1) // dy if height > y0 else 0
        if w and h:
            total += h * (1 + (w * bits_per_pixel + 7) // 8)  # one filter byte per row
    return total


# ---------- JPEG: marker structure ----------
_STANDALONE = {0x01, *range(0xD0, 0xD8)}  # markers without a length field
_START_OF_FRAME = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
# Huffman and arithmetic-conditioning tables (DHT, DAC), quantization tables, DNL, restart interval,
# comments and APPn (JFIF, EXIF, ICC, Adobe, ...).
_SEGMENT_MARKERS = {0xC4, 0xCC, 0xDB, 0xDC, 0xDD, 0xFE, *range(0xE0, 0xF0)}


def _check_jpeg(data: bytes) -> tuple[int, int] | None:
    """Walk SOI, segments, every scan and EOI. Returns (width, height) of a complete JPEG."""
    n = len(data)
    if n < 4 or not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    size = None
    scans = 0
    while True:
        if i >= n or data[i] != 0xFF:
            return None
        while i < n and data[i] == 0xFF:  # fill bytes
            i += 1
        if i >= n:
            return None
        marker = data[i]
        i += 1
        if marker == 0xD9:  # end of image: only valid after a frame header and a scan
            return size if size is not None and scans else None
        if marker in _STANDALONE:
            continue
        if marker != 0xDA and marker not in _START_OF_FRAME and marker not in _SEGMENT_MARKERS:
            return None  # reserved or misplaced marker (including a second SOI)
        if i + 2 > n:
            return None
        length = struct.unpack(">H", data[i:i + 2])[0]
        if length < 2 or i + length > n:
            return None
        if marker in _START_OF_FRAME:
            if length < 8 or size is not None:
                return None
            precision, height, width, components = struct.unpack(">BHHB", data[i + 2:i + 8])
            if precision not in (8, 12, 16) or components not in (1, 3, 4) or length != 8 + 3 * components:
                return None
            size = (width, height)
        i += length
        if marker == 0xDA:  # start of scan: skip its compressed data up to the next real marker
            if size is None:
                return None
            start = i
            i = _skip_scan_data(data, i)
            if i is None or i == start:
                return None  # ran off the end, an invalid marker inside the data, or an empty scan
            scans += 1


def _skip_scan_data(data: bytes, i: int) -> int | None:
    """Index of the 0xFF that starts the first marker after the compressed data, or None."""
    n = len(data)
    while True:
        j = data.find(b"\xff", i)
        if j == -1 or j + 1 >= n:
            return None
        following = data[j + 1]
        if following == 0x00 or 0xD0 <= following <= 0xD7:  # stuffed byte, restart marker
            i = j + 2
        elif following == 0xFF:  # fill byte
            i = j + 1
        elif following == 0xD9 or following == 0xDA or following in _SEGMENT_MARKERS:
            return j  # the scan ended at a legitimate marker
        else:
            return None  # reserved marker code inside compressed data
