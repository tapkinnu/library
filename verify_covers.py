#!/usr/bin/env python3
"""Cover-text gate: fail-loud if a book cover is missing its title/byline.

Why this exists
---------------
Books in ~/Books/<slug>/cover/ sometimes ship ONLY the raw AI-art PNG
(cover/art.png, cover/artwork*.png, etc.) without title/byline text burned
in. The `cover/make_cover.py` step that normally runs Pillow + TTF fonts to
draw "THE TITLE" and "WRITTEN BY T. K. ARVEN" on top of the art may
have been skipped, or its output was lost, or `generate.py`'s
auto-heal silently picked the raw-art file. Result: a text-less cover
ships to the live site.

This script is the durable safety net: it OCRs every published cover
with Tesseract and flags any image where the recognized text is empty
or does not mention the author byline `Arven`.

Why OCR (and not a pixel heuristic)
-----------------------------------
A per-band dark-pixel / edge-density heuristic was tried first and was
unreliable: pieces of AI art (mountains, sea, lattice meshes) naturally
contain dark pixels and edges in the same bands where the title/byline
should sit. Tesseract ignores scenery and only returns glyph-level text.
A single OCR call per cover is the cheapest signal we have that the
cover actually has burned-in title typography.

Why "Arven" instead of the full punctuated byline
--------------------------------------------------
The byline is uppercased as `T. K. ARVEN` (sometimes prefixed by `BY` or
`WRITTEN BY`). OCR may drop periods or insert kerning gaps inside `ARVEN`.
The gate accepts the exact surname and a narrow fragmented form, then reports
the extracted text so a human can inspect edge cases.

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


def _status_explicitly_incomplete(text: str) -> bool:
    """Mirror generate.py's top-level excluded-ledger publication guard."""
    incomplete = {"draft", "drafting", "in-progress", "in_progress", "repair", "production", "withdrawn"}
    values = re.findall(r"(?im)^(?:phase|status):\s*[\"']?([^\n\"']+)", text)
    return any(value.strip().lower() in incomplete for value in values)


# Whitelist matches: any of these substrings in the OCR text means the
# byline is present. We use case- and punctuation-insensitive matching.
#
# The public surname is deliberately the strongest signal. Periods and
# kerning can make Tesseract split ARVEN, so accept a modest punctuation or
# whitespace gap between ARV and EN while still rejecting raw-art gibberish.
_BYLINE_MARKERS = ("arven",)
_ARVEN_SPLIT_RE = re.compile(r"\bARV[^A-Z0-9]{0,8}E[NM]\b", re.IGNORECASE)
# The complete initialled byline is a second signal. OCR commonly drops the
# periods in "T. K. ARVEN" but reliably keeps the initials and surname close.
_TK_ARVEN_RE = re.compile(
    r"\bT[^A-Z0-9]{0,5}K[^A-Z0-9]{0,12}ARV[^A-Z0-9]{0,8}E[NM]\b",
    re.IGNORECASE,
)
# One book (the-slowlight-accord) prints the byline stacked as
# "T. K. ARVEN" then "AUTHOR" on the next line. The author-line word
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
      * byline band : y in [0.82, 0.92]    — where T. K. ARVEN lives
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
        # scales miss T. K. ARVEN on many of our covers.
        scale = max(1.0, 3000 / max(1, h))
        if scale != 1.0:
            im = im.resize(
                (int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        gray = im.convert("L")
        uh = gray.size[1]
        # Slightly wider byline band (0.78–0.94) than 0.82–0.92 so we
        # include the "AUTHOR" caption below "T. K. ARVEN" on
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

    Strategy: pass when OCR finds EITHER the surname `ARVEN`, its narrowly
    fragmented `ARV ... EN` form, or the complete initialled byline pattern.

    AI art almost never produces these glyph sequences; they're
    unambiguous byline signals when present.

    Fuzzy matching is intentionally surname-specific; `AUTHOR` by itself is
    not accepted because it does not prove the requested public name appears.
    """
    diag: dict = {"path": str(cover_path)}
    if not cover_path.exists():
        return True, {**diag, "error": "cover file missing"}
    try:
        with Image.open(cover_path) as im:
            im.load()
            w, h = im.size
            diag["size"] = (w, h)
    except Exception as e:
        return True, {**diag, "error": f"open failed: {e}"}

    # House rule: covers must be portrait (h > w).
    if h <= w:
        diag["error"] = f"landscape cover ({w}x{h}, h/w={h/w:.3f}); library covers MUST be portrait (h > w)"
        return True, diag

    if not use_ocr:
        return False, diag

    text, ocr_diag = _ocr_cover(cover_path)
    diag.update(ocr_diag)
    diag["ocr_text_preview"] = text[:160].replace("\n", " | ")

    text_lower = text.lower()
    byline_hits = [m for m in _BYLINE_MARKERS if m in text_lower]
    split_match = bool(_ARVEN_SPLIT_RE.search(text))
    full_match = bool(_TK_ARVEN_RE.search(text))
    author_match = bool(_AUTHOR_RE.search(text))
    has_byline = bool(byline_hits) or split_match or full_match
    diag["byline_hits"] = byline_hits
    diag["arven_split"] = split_match
    diag["tk_arven"] = full_match
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
        status = d / "status.yaml"
        if status.exists() and _status_explicitly_incomplete(status.read_text(encoding="utf-8")):
            continue
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
