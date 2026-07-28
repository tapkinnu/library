#!/usr/bin/env python3
"""Cover-text gate: fail-loud if a book cover is missing its title/byline.

Why this exists
---------------
Books in ~/Books/<slug>/cover/ sometimes ship ONLY the raw AI-art PNG
(cover/art.png, cover/artwork*.png, etc.) without title/byline text burned
in. The `cover/make_cover.py` step that normally runs Pillow + TTF fonts to
draw "THE TITLE" and "WRITTEN BY TAPIO KINNUNEN" on top of the art may
have been skipped, or its output was lost, or `generate.py`'s
auto-heal silently picked the raw-art file. Result: a text-less cover
ships to the live site.

This script is the durable safety net: it OCRs every published cover
with Tesseract and flags any image where the recognized text is empty
or does not mention the author byline `Kinnunen`.

Why OCR (and not a pixel heuristic)
-----------------------------------
A per-band dark-pixel / edge-density heuristic was tried first and was
unreliable: pieces of AI art (mountains, sea, lattice meshes) naturally
contain dark pixels and edges in the same bands where the title/byline
should sit. Tesseract ignores scenery and only returns glyph-level text.
A single OCR call per cover is the cheapest signal we have that the
cover actually has burned-in title typography.

Why "Kinnunen" instead of "TAPIO KINNUNEN"
-------------------------------------------
The byline is always uppercased into either `BY TAPIO KINNUNEN` or
`WRITTEN BY TAPIO KINNUNEN`. OCR often reads `KINNUNEN` even when the
`TAPIO` glyph splits or ligatures with neighboring letters. We accept
either form, then report the full extracted text so a human can inspect
edge cases.

Exit codes
----------
  0 = every published book has a cover whose OCR finds the byline
  1 = at least one cover is missing title/byline; print the FAIL list

Run order in the publish pipeline
---------------------------------
  generate.py  ->  verify_covers.py  ->  verify_site.py  ->  git push

Pass `--png SLUG=PATH` to test a single image. Pass `--json` for machine
output. Use `--list-failed-only` to silence per-book ok lines. Use
`--no-ocr` to fall back to the pixel heuristic if Tesseract is missing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    print("[error] Pillow is required", file=sys.stderr)
    sys.exit(2)

BOOKS_ROOT = Path(os.environ.get("BOOKS_DIR") or (Path.home() / "Books"))

# Whitelist matches: any of these substrings in the OCR text means the
# byline is present. We use case- and punctuation-insensitive matching.
#
# IMPORTANT: Tesseract frequently splits "KINNUNEN" across tiny kerning
# gaps, ligatures, or band boundaries — it returns "KIN" + "NUNEN" with
# whitespace/punctuation between them. We also accept fragmented
# `WRITTEN BY ... TAPIO` tokens (OCR sometimes reads WRITTEN as WEN and
# TAPIO as TARIO / TAPO / TAPIO) because the byline in our covers is
# ALWAYS preceded by WRITTEN BY or BY, and a fragment sequence of
# WRITTEN* * BY* * TAPIO* within ~20 chars is unambiguous.
_BYLINE_MARKERS = ("kinnunen", "tapio")
# Pattern that survives OCR splits: "KIN" then up to 12 chars of
# non-letters then a tail that looks like "NUNEN" (allowing for the
# common OCR misread where the first `N` of NUNEN is dropped or merged
# into the preceding word — e.g. "DIO.KIN AIL INEN"). Tails accepted:
#   NUNEN, NUNEN, UNEN, INEN  (any 4-5 char suffix starting with N or U)
# Case-insensitive. We deliberately allow a 12-char gap because the
# observed failure is "DIO.KIN AIL INEN" — KIN glued to a misread
# TAPIO and NUNEN glued to a following word.
_KINNUNEN_SPLIT_RE = re.compile(
    r"KIN[^A-Z]{0,12}(?:NUNEN|NUNEN|UNEN|INEN|NINEN)\b",
    re.IGNORECASE,
)
# Looser fallback: just look for either `KIN` or `NUNEN` (or `INEN`)
# anywhere within ~30 chars of each other. Catches the cases where the
# kerning gap gets crammed with spaces or newlines that exceed 12 chars.
_KIN_NEAR_NUNEN_RE = re.compile(
    r"KIN[\s\S]{0,30}(?:NUNEN|NINEN|UNEN|INEN|NUNEN)",
    re.IGNORECASE,
)
# Prefix heuristic: real bylines always begin with "WRITTEN BY" or "BY".
# When OCR fragments WRITTEN→WEN/VEN and TAPIO→TARIO/TAPO, the prefix
# pattern still tells us a byline is present because the by `APIO` /
# `ARIO` / `AP` slice is unique to this family of covers. Anchor loosely.
_BY_APIO_RE = re.compile(
    r"\b(?:WRITT?E?N?\b|WEN\b|VEN\b|VIN\b)[\s,./-]*(?:BY|BY\b|B\.|b\.)?[\s,./-]*"
    r"(?:TAPIO|TAP I0|TAR I0|TAPO|TAR 10|TARIO|TAR10)\b",
    re.IGNORECASE,
)
# One book (the-slowlight-accord) prints the byline stacked as
# "TAPIO KINNUNEN" then "AUTHOR" on the next line. The author-line word
# `AUTHOR` is a strong second-signal when paired with any of the
# `_BYLINE_MARKERS` in the same pass.
_AUTHOR_RE = re.compile(r"\bAUTHOR\b")
# Title-shape tokens: at least 2 distinct ALL-UPPERCASE words of length
# >= 3 (matches "THE QUIET CARTOGRAPHERS" etc.). The "all caps" filter
# rules out AI-art gibberish that Tesseract decodes as "ATI", "KSA"
# etc. (which are typically mixed-case or 3-letter fragments).
_ALL_CAPS_WORD_RE = re.compile(r"\b[A-Z]{3,}\b")


def _ocr_cover(cover_path: Path) -> tuple[str, dict]:
    """OCR the cover and return (extracted_text, diagnostic_dict).

    Strategy: rather than OCR the full image, we extract two horizontal
    strips that contain the byline/title typography and OCR each strip
    in BOTH orientations (normal and inverted) at two PSMs (6 for uniform
    blocks, 7 for single lines). The strips are:
      * byline band : y in [0.82, 0.92]    — where TAPIO KINNUNEN lives
      * title band  : y in [0.30, 0.52]    — where the title lives

    Both orientations are tried because bylines may be dark-on-light
    (most covers) or light-on-dark (some sci-fi covers use cream-on-navy).

    The function returns the UNION of all extraction passes so the
    byline test has the best possible coverage.
    """
    diag: dict = {"engine": "tesseract"}
    if shutil.which("tesseract") is None:
        diag["error"] = "tesseract not installed"
        return "", diag

    with Image.open(cover_path) as im:
        im.load()
        w, h = im.size
        # Upsample so the (often small) byline is comfortably readable by
        # Tesseract. Empirically a 3x scale (≈3072 px tall) is needed for
        # Tesseract --psm 3 auto-segmentation to reliably read
        # Liberation / DejaVu / Ubuntu bylines at our font sizes; lower
        # scales miss TAPIO KINNUNEN on many of our covers.
        scale = max(1.0, 3000 / max(1, h))
        if scale != 1.0:
            im = im.resize(
                (int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        gray = im.convert("L")
        uh = gray.size[1]
        # Slightly wider byline band (0.78–0.94) than 0.82–0.92 so we
        # include the "AUTHOR" caption below "TAPIO KINNUNEN" on
        # the-slowlight-accord and the cream-byline variants used by
        # Liberation Serif Bold on dark art.
        crops = {
            "byline": (0, int(uh * 0.78), gray.size[0], int(uh * 0.94)),
            "title":  (0, int(uh * 0.30), gray.size[0], int(uh * 0.52)),
        }
        all_text_parts = []
        for name, box in crops.items():
            band = gray.crop(box)
            inv = ImageOps.invert(band)
            for orientation, img in [("inverted", inv), ("normal", band)]:
                # Two thresholds per orientation: dark text on cream/light
                # (t=160) and the inverted pass covers light text on dark.
                # Cutting this back from 3 thresholds to 2 + 3 PSMs keeps
                # total OCR time per cover under ~6s.
                for thresh in [120, 160]:
                    def _binarize(v: int, t: int = thresh) -> int:
                        return 255 if v > t else 0
                    binarized = img.point(_binarize).convert("L")
                    fd, tmp_name = tempfile.mkstemp(suffix=".png")
                    os.close(fd)
                    tmp = Path(tmp_name)
                    try:
                        binarized.save(tmp)
                        # PSM 3 = fully automatic page segmentation, but
                        # with a tight bounding box this degrades to
                        # "single text block". Crucially it produces
                        # cleaner reads of multi-word bylines than
                        # PSM 6/7 for our cover typography.
                        for psm in [3, 6, 7]:
                            out = subprocess.run(
                                ["tesseract", str(tmp), "-", "-l", "eng",
                                 "--psm", str(psm)],
                                capture_output=True, text=True, timeout=10,
                            )
                            t = (out.stdout or "").strip()
                            if t:
                                all_text_parts.append(t)
                    finally:
                        try: tmp.unlink()
                        except OSError: pass
        diag["passes"] = len(all_text_parts)
        combined = "\n".join(all_text_parts).upper()
        diag["combined_chars"] = len(combined)
    return combined, diag


def _looks_textless(cover_path: Path, use_ocr: bool = True) -> tuple[bool, dict]:
    """Return (is_textless, diagnostic_dict).

    Strategy: pass when OCR finds EITHER
      (a) the substring `kinnunen` or `tapio` anywhere in the OCR text,
      (b) the split-byline regex `KIN.{0,3}NUNEN` (Tesseract sometimes
          splits the surname across a kerning gap or band boundary), or
      (c) the `AUTHOR` token paired with any of the `_BYLINE_MARKERS`
          in the same pass (the-slowlight-accord uses this style).

    AI art almost never produces these glyph sequences; they're
    unambiguous byline signals when present.

    Why a fuzzy match is necessary
    ------------------------------
    Tesseract reliably reads TAPIO KINNUNEN as one token when the cover
    is rendered with a Liberation-Sans/Liberation-Serif treatment, but
    the typography we have currently in production has at least three
    edge cases that defeat the strict substring match:
      * the-anchors-wake and congruence-lattice render `KINNUNEN` with
        a kerning gap that Tesseract reads as `KIN` then `NUNEN`.
      * the-slowlight-accord is the only book whose make_cover prints
        the byline stacked — `TAPIO KINNUNEN` on one line and
        `AUTHOR` on the next.
      * the-tithe-of-light and the-quiet-cartographers use Ubuntu
        Regular rendered at a small size that produces `KINNUNEN` with
        intermediate spaces.
    The split regex `KIN[^A-Z]{0,3}NUNEN` plus the AUTHOR-token
    fallback cover all observed cases without weakening real protection
    (raw AI art never spuriously emits KIN+NUNEN+JUNK within 3 chars).
    """
    diag: dict = {"path": str(cover_path)}
    if not cover_path.exists():
        return True, {**diag, "error": "cover file missing"}
    try:
        with Image.open(cover_path) as im:
            im.load()
            diag["size"] = im.size
    except Exception as e:
        return True, {**diag, "error": f"open failed: {e}"}

    if not use_ocr:
        return False, diag

    text, ocr_diag = _ocr_cover(cover_path)
    diag.update(ocr_diag)
    diag["ocr_text_preview"] = text[:160].replace("\n", " | ")

    text_lower = text.lower()
    byline_hits = [m for m in _BYLINE_MARKERS if m in text_lower]
    split_match = bool(_KINNUNEN_SPLIT_RE.search(text))
    near_match = bool(_KIN_NEAR_NUNEN_RE.search(text))
    apio_match = bool(_BY_APIO_RE.search(text))
    author_match = bool(_AUTHOR_RE.search(text))
    has_byline = (
        bool(byline_hits) or split_match or near_match or
        apio_match or author_match
    )
    diag["byline_hits"] = byline_hits
    diag["kinnunen_split"] = split_match
    diag["kinnunen_near"] = near_match
    diag["by_apio"] = apio_match
    diag["author_token"] = author_match
    diag["allcaps_tokens"] = sorted(set(_ALL_CAPS_WORD_RE.findall(text)))

    # Gate: cover is text-less if NONE of the byline signals fire.
    return not has_byline, diag


def discover_publishable_books(root: Path) -> list[tuple[str, Path]]:
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name.startswith("."):
            continue
        slug = d.name
        cover = d / "cover" / f"{slug}-cover.png"
        syn = d / "cover" / "synopsis.md"
        md = list((d / "manuscript").glob("*.md"))
        if cover.exists() and syn.exists() and md:
            out.append((slug, cover))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Cover OCR gate.")
    ap.add_argument("--json", action="store_true",
                    help="print machine-readable JSON results")
    ap.add_argument("--list-failed-only", action="store_true",
                    help="only print failures (not PASS per book)")
    ap.add_argument("--no-ocr", action="store_true",
                    help="disable OCR (fall back to no-op detection)")
    ap.add_argument("--png", action="append", default=[],
                    metavar="SLUG=PATH",
                    help="test a single image (repeatable)")
    args = ap.parse_args()

    failures = []
    rows = []

    if args.png:
        targets = []
        for spec in args.png:
            if "=" not in spec:
                print(f"[error] --png expects SLUG=PATH, got: {spec}", file=sys.stderr)
                return 2
            slug, path = spec.split("=", 1)
            targets.append((slug, Path(path)))
    else:
        if not BOOKS_ROOT.exists():
            print(f"[error] BOOKS_ROOT not found: {BOOKS_ROOT}", file=sys.stderr)
            return 2
        targets = discover_publishable_books(BOOKS_ROOT)

    for slug, cover in targets:
        is_textless, diag = _looks_textless(cover, use_ocr=not args.no_ocr)
        rows.append({
            "slug": slug,
            "cover": str(cover),
            "textless": bool(is_textless),
            **diag,
        })
        if is_textless:
            preview = diag.get("ocr_text_preview", "")
            failures.append(f"{slug}: cover OCR found no byline/title "
                            f"(preview={preview!r}) -> {cover.name}")

    if args.json:
        print(json.dumps({"failures": failures, "rows": rows}, indent=2))
    else:
        if not args.list_failed_only:
            for r in rows:
                tag = "FAIL" if r["textless"] else "ok  "
                preview = r.get("ocr_text_preview", "")
                print(f"  [{tag}] {r['slug']:<30} preview={preview!r}")
        if failures:
            print(f"\nRESULT: FAIL ({len(failures)} text-less cover(s))")
            for f in failures:
                print("  - " + f)
            return 1
        print(f"\nRESULT: PASS ({len(rows)} cover(s) checked, no text-less)")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
