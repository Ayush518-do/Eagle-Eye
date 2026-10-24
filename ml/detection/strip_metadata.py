"""Make working copies of photos with hidden metadata removed (GPS location, camera serial).

Usage:
    python -m ml.detection.strip_metadata data/private/raw data/private/clean

Originals are never modified. Pixel data is copied unchanged; only metadata is dropped.
JPEGs are re-saved at quality 95, which slightly changes pixels; use PNG output with --png to avoid that.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def strip(src: Path, dst_dir: Path, png: bool = False) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # keep the photo the right way up before dropping EXIF
        clean = Image.new(im.mode, im.size)
        clean.putdata(list(im.getdata()))
        out = dst_dir / (src.stem + (".png" if png else src.suffix.lower()))
        if out.exists():
            raise FileExistsError(f"Refusing to overwrite {out}")
        clean.save(out, **({} if png or out.suffix == ".png" else {"quality": 95}))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--png", action="store_true")
    a = ap.parse_args()
    for p in sorted(a.src.iterdir()):
        if p.suffix.lower() in IMAGE_EXT:
            print("wrote", strip(p, a.dst, a.png))


if __name__ == "__main__":
    main()
