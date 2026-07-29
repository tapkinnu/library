#!/usr/bin/env python3
"""Convert a finished legacy 2:3 cover to the library's 9:16 portrait standard."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw

TARGET = (576, 1024)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    src = Path(args.source)
    out = Path(args.out)
    im = Image.open(src).convert("RGB")
    target_ratio = TARGET[0] / TARGET[1]
    source_ratio = im.width / im.height
    if source_ratio > target_ratio:
        crop_w = round(im.height * target_ratio)
        left = (im.width - crop_w) // 2
        im = im.crop((left, 0, left + crop_w, im.height))
    else:
        crop_h = round(im.width / target_ratio)
        top = (im.height - crop_h) // 2
        im = im.crop((0, top, im.width, top + crop_h))
    im = im.resize(TARGET, Image.Resampling.LANCZOS)
    # Re-establish a clean trim frame after removing the old 2:3 side edges.
    draw = ImageDraw.Draw(im)
    draw.rectangle((1, 1, TARGET[0] - 2, TARGET[1] - 2), outline=(10, 22, 38), width=4)
    draw.rectangle((6, 6, TARGET[0] - 7, TARGET[1] - 7), outline=(173, 87, 67), width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "PNG", optimize=True)
    print(f"WROTE {out} {out.stat().st_size} bytes {TARGET[0]}x{TARGET[1]}")


if __name__ == "__main__":
    main()
