#!/usr/bin/env python3
"""Professional portrait-cover typesetter for the multi-author library.

The AI artwork must be text-free. This tool adds crisp, reproducible typography,
a restrained title field, and a strong lower fade that suppresses accidental
AI glyphs near the trim edge. It is deliberately independent of the website
card CSS: the exported PNG must be publication-ready on its own.
"""
from __future__ import annotations

import argparse
import itertools
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CREAM = (244, 239, 226)
NAVY = (8, 18, 35)
TERRA = (190, 102, 70)
MUTED = (191, 201, 214)
TARGET = (576, 1024)
FONT_ROOT = Path("/usr/share/fonts/truetype")
FONTS = {
    "dejavu-sans": ("dejavu/DejaVuSans.ttf", "dejavu/DejaVuSans-Bold.ttf", "dejavu/DejaVuSans-Oblique.ttf"),
    "dejavu-serif": ("dejavu/DejaVuSerif.ttf", "dejavu/DejaVuSerif-Bold.ttf", "dejavu/DejaVuSerif-Italic.ttf"),
    "liberation-sans": ("liberation/LiberationSans-Regular.ttf", "liberation/LiberationSans-Bold.ttf", "liberation/LiberationSans-Italic.ttf"),
    "liberation-serif": ("liberation/LiberationSerif-Regular.ttf", "liberation/LiberationSerif-Bold.ttf", "liberation/LiberationSerif-Italic.ttf"),
    "ubuntu": ("ubuntu/Ubuntu-R.ttf", "ubuntu/Ubuntu-B.ttf", "ubuntu/Ubuntu-RI.ttf"),
    "ubuntu-condensed": ("ubuntu/Ubuntu-C.ttf", "ubuntu/Ubuntu-C.ttf", "ubuntu/Ubuntu-C.ttf"),
    "free-serif": ("freefont/FreeSerif.ttf", "freefont/FreeSerifBold.ttf", "freefont/FreeSerifItalic.ttf"),
}


def font(family: str, weight: str, size: int) -> ImageFont.FreeTypeFont:
    if family not in FONTS:
        raise SystemExit(f"Unknown font family {family!r}; choose from {', '.join(sorted(FONTS))}")
    index = {"regular": 0, "bold": 1, "italic": 2}[weight]
    path = FONT_ROOT / FONTS[family][index]
    if not path.exists():
        raise SystemExit(f"Missing font: {path}")
    return ImageFont.truetype(str(path), size)


def center_crop(im: Image.Image, target=TARGET) -> Image.Image:
    tw, th = target
    scale = max(tw / im.width, th / im.height)
    size = (round(im.width * scale), round(im.height * scale))
    im = im.resize(size, Image.Resampling.LANCZOS)
    left = (im.width - tw) // 2
    top = (im.height - th) // 2
    return im.crop((left, top, left + tw, top + th))


def add_vertical_fade(base: Image.Image, y0: int, y1: int, peak_alpha: int,
                      color=NAVY, reverse: bool = False) -> Image.Image:
    """Composite a smooth fade. Normal grows opaque downward; reverse upward."""
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    span = max(1, y1 - y0)
    for y in range(max(0, y0), min(base.height, y1 + 1)):
        t = (y - y0) / span
        if reverse:
            t = 1.0 - t
        # Smoothstep avoids visible band boundaries.
        t = t * t * (3.0 - 2.0 * t)
        a = round(peak_alpha * t)
        od.line((0, y, base.width, y), fill=(*color, a))
    return Image.alpha_composite(base.convert("RGBA"), overlay)


def add_title_field(base: Image.Image, top: int, bottom: int) -> Image.Image:
    """A soft navy veil behind the title, strongest at the block centre."""
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    centre = (top + bottom) / 2
    half = max(1.0, (bottom - top) / 2)
    for y in range(max(0, top), min(base.height, bottom + 1)):
        distance = abs(y - centre) / half
        a = round(152 * max(0.0, 1.0 - distance ** 1.7))
        od.line((0, y, base.width, y), fill=(*NAVY, a))
    return Image.alpha_composite(base.convert("RGBA"), overlay)


def partitions(words: list[str], count: int):
    for cuts in itertools.combinations(range(1, len(words)), count - 1):
        starts = (0,) + cuts
        ends = cuts + (len(words),)
        yield [" ".join(words[a:b]) for a, b in zip(starts, ends)]


def choose_title_lines(draw: ImageDraw.ImageDraw, title: str, family: str,
                       max_width: int, max_lines: int = 3):
    if "|" in title:
        forced = [x.strip() for x in title.split("|") if x.strip()]
        candidates = [forced]
    else:
        words = title.split()
        candidates = []
        for count in range(1, min(max_lines, len(words)) + 1):
            candidates.extend(partitions(words, count))

    best = None
    for lines in candidates:
        # Avoid typographic widows such as a lone OF/THE on a line.
        if len(lines) > 1 and any(len(line.split()) == 1 and len(line) <= 3 for line in lines):
            continue
        size = 68
        while size >= 34:
            fnt = font(family, "bold", size)
            widths = [draw.textlength(line, font=fnt) for line in lines]
            if max(widths) <= max_width:
                break
            size -= 2
        else:
            continue
        imbalance = (max(widths) - min(widths)) / max_width if len(widths) > 1 else 0
        # Prefer large, balanced lettering; slight penalty for extra lines.
        score = size - 4.0 * (len(lines) - 1) - 5.0 * imbalance
        if best is None or score > best[0]:
            best = (score, lines, fnt, size)
    if best is None:
        raise SystemExit(f"Could not fit title: {title}")
    return best[1], best[2], best[3]


def draw_centered(draw, text, y, fnt, fill, shadow=True):
    box = draw.textbbox((0, 0), text, font=fnt)
    x = (TARGET[0] - (box[2] - box[0])) / 2
    if shadow:
        draw.text((x + 2, y + 3), text, font=fnt, fill=(*NAVY, 210))
    draw.text((x, y), text, font=fnt, fill=fill)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--byline", required=True, help="resolved per-book byline; never inferred")
    ap.add_argument("--kicker", default="A SCIENCE FICTION NOVEL")
    ap.add_argument("--title-y", type=float, default=0.16,
                    help="top of title block as a fraction of cover height")
    ap.add_argument("--title-font", default="dejavu-serif", choices=sorted(FONTS))
    ap.add_argument("--title-weight", default="bold", choices=("regular", "bold", "italic"),
                    help="accepted for wrapper compatibility; titles are rendered bold for legibility")
    ap.add_argument("--title-case", default="upper", choices=("upper", "title", "asis"))
    ap.add_argument("--byline-font", default="dejavu-sans", choices=sorted(FONTS))
    ap.add_argument("--byline-weight", default="bold", choices=("regular", "bold", "italic"))
    ap.add_argument("--max-lines", type=int, default=3)
    args = ap.parse_args()

    src = Path(args.art)
    out = Path(args.out)
    if not src.exists():
        raise SystemExit(f"Missing raw art: {src}")
    raw = Image.open(src).convert("RGB")
    if raw.height <= raw.width:
        raise SystemExit(f"Raw art must be portrait; got {raw.width}x{raw.height}")
    im = center_crop(raw).convert("RGBA")

    # Permanent typography-safe fields. The lower fade is intentionally nearly
    # opaque at trim: it removes accidental AI pseudo-lettering as well as
    # preserving the author credit over any artwork.
    im = add_vertical_fade(im, 0, 145, 172, reverse=True)
    im = add_vertical_fade(im, 760, 1024, 255)
    # The final trim band is fully opaque. Raw AI art occasionally contains
    # pseudo-lettering here; translucency can leave it faintly legible.
    trim_overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(trim_overlay).rectangle((0, 958, TARGET[0], TARGET[1]), fill=(*NAVY, 255))
    im = Image.alpha_composite(im, trim_overlay)

    probe = ImageDraw.Draw(im)
    title = args.title.upper() if args.title_case == "upper" else (
        args.title.title() if args.title_case == "title" else args.title)
    lines, title_font, title_size = choose_title_lines(
        probe, title, args.title_font, int(TARGET[0] * 0.84), args.max_lines)
    line_gap = round(title_size * 0.18)
    line_h = round(title_size * 1.03)
    block_h = len(lines) * line_h + (len(lines) - 1) * line_gap
    title_top = round(TARGET[1] * args.title_y)
    field_top = max(96, title_top - 38)
    field_bottom = min(760, title_top + block_h + 60)
    im = add_title_field(im, field_top, field_bottom)

    draw = ImageDraw.Draw(im)
    kicker_font = font("dejavu-sans", "regular", 18)
    draw_centered(draw, args.kicker.upper(), 48, kicker_font, MUTED, shadow=True)

    y = title_top
    for line in lines:
        draw_centered(draw, line, y, title_font, CREAM, shadow=True)
        y += line_h + line_gap
    rule_y = min(field_bottom - 24, y + 10)
    draw.line((TARGET[0] * 0.34, rule_y, TARGET[0] * 0.66, rule_y), fill=TERRA, width=4)

    # Author block: one unambiguous name, no redundant BY/AUTHOR label.
    byline_font = font(args.byline_font, args.byline_weight, 24)
    draw_centered(draw, args.byline.upper(), 898, byline_font, CREAM, shadow=True)
    draw.line((TARGET[0] * 0.41, 942, TARGET[0] * 0.59, 942), fill=(*TERRA, 230), width=2)

    out.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(out, "PNG", optimize=True)
    print(f"WROTE {out} {out.stat().st_size} bytes {TARGET[0]}x{TARGET[1]}")


if __name__ == "__main__":
    main()
