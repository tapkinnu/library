#!/usr/bin/env python3
"""Pre-publish consistency + completeness gate for the book library.

Run AFTER generate.py has rebuilt docs/. Exits non-zero (prints RESULT: FAIL)
if any published book would ship with:
  - a missing Download PDF (docs/books/<slug>/<slug>.pdf absent), or
  - an inconsistent home-card blurb (empty, or starting with a meta label
    such as **Genre:** / **Length:** instead of narrative).

Exits 0 (RESULT: PASS) only when every book passes both checks. The
auto-publish cron uses this as a hard gate: it must NOT push unless PASS.

This guarantees three durable rules:
  1. Every published book ships a downloadable PDF.
  2. Every home-card synopsis blurb is a real narrative, not bare metadata,
     so the library reads consistently no matter how a synopsis file is shaped.
  3. Every synopsis uses the house presentation: one title, the Tapio Kinnunen
     byline, a professional-length blurb, then Format and Length metadata.
"""
import re
import sys
from pathlib import Path

BOOKS_ROOT = Path.home() / "Books"
SITE_DOCS = Path(__file__).resolve().parent / "docs"

# --- blurb parsing mirror of generate.parse_synopsis (kept local so this
#     script has no import coupling to generate.py's internals) ----------
_author_re = re.compile(r"^\*\*(.+?)\*\*$|^\*(.+?)\*$")
_bold_meta_re = re.compile(r"^\*\*(?:[^*]*:\*\*|[^*]+\*\*\s*:)")
_italic_meta_re = re.compile(r"^\*[^*].*?\*\s*$")
_heading_re = re.compile(r"^#{1,6}\s")
_bullet_re = re.compile(r"^\s*[-*]\s")


def _status_explicitly_incomplete(text: str) -> bool:
    """Mirror generate.py's top-level excluded-ledger publication guard."""
    incomplete = {"draft", "drafting", "in-progress", "in_progress", "repair", "production", "withdrawn"}
    values = re.findall(r"(?im)^(?:phase|status):\s*[\"']?([^\n\"']+)", text)
    return any(value.strip().lower() in incomplete for value in values)


def _is_meta(s: str) -> bool:
    if _bullet_re.match(s) or _heading_re.match(s):
        return True
    if _bold_meta_re.match(s):
        return True
    if _italic_meta_re.match(s) and ("words" in s.lower()
                                     or "by tapio" in s.lower()
                                     or "by adrian" in s.lower()):
        return True
    return False


def extract_blurb(syn_text: str) -> str:
    lines = syn_text.splitlines()
    title_idx = None
    for i, ln in enumerate(lines):
        if title_idx is None and ln.startswith("# "):
            title_idx = i
            break
    if title_idx is None:
        return ""
    rest = lines[title_idx + 1:]
    start = 0
    for i, ln in enumerate(rest):
        if _heading_re.match(ln.strip()) and re.search(r"synopsis|premise", ln, re.I):
            start = i + 1
            break
    out, started = [], False
    for ln in rest[start:]:
        s = ln.strip()
        if _is_meta(s):
            break
        if _author_re.match(s):
            continue
        if not s:
            if started:
                out.append(ln)
            continue
        started = True
        out.append(ln)
    return "\n".join(out).strip()


def main():
    failures = []
    books = sorted(p for p in BOOKS_ROOT.iterdir() if p.is_dir())
    checked = 0
    for d in books:
        slug = d.name
        status = d / "status.yaml"
        if status.exists() and _status_explicitly_incomplete(status.read_text(encoding="utf-8")):
            continue
        cover = (list(d.glob("cover/*-cover.png")) or [d / "x"])[0]
        syn = d / "cover" / "synopsis.md"
        md = list(d.glob("manuscript/*.md"))
        if not (cover.exists() and syn.exists() and md):
            continue  # not a publishable book; skipped by generate.py too
        checked += 1
        # (1) PDF uploaded to the site
        site_pdf = SITE_DOCS / "books" / slug / f"{slug}.pdf"
        if not site_pdf.exists():
            failures.append(f"{slug}: PDF missing on site ({site_pdf.name})")
            continue
        # (2) synopsis uses the canonical professional house structure.
        syn_text = syn.read_text(encoding="utf-8")
        nonblank = [ln.strip() for ln in syn_text.splitlines() if ln.strip()]
        h1 = [ln for ln in nonblank if ln.startswith("# ") and not ln.startswith("## ")]
        if len(h1) != 1 or not nonblank or nonblank[0] != h1[0]:
            failures.append(f"{slug}: synopsis must start with exactly one '# Title' heading")
            continue
        if re.search(r"\bsynopsis\b", h1[0], re.I):
            failures.append(f"{slug}: public title must not include the word 'Synopsis'")
            continue
        if nonblank.count("**By Tapio Kinnunen**") != 1:
            failures.append(f"{slug}: synopsis must contain exactly one '**By Tapio Kinnunen**' byline")
            continue
        format_lines = [ln for ln in nonblank if ln.startswith("**Format:**")]
        length_lines = [ln for ln in nonblank if ln.startswith("**Length:**")]
        if len(format_lines) != 1 or len(length_lines) != 1:
            failures.append(f"{slug}: synopsis needs exactly one Format line and one Length line")
            continue
        if nonblank[-2:] != [format_lines[0], length_lines[0]]:
            failures.append(f"{slug}: synopsis must end with Format followed by Length")
            continue
        allowed_formats = {
            "**Format:** Novel", "**Format:** Novella", "**Format:** Novelette",
            "**Format:** Graphic novel", "**Format:** Adults-only graphic novel",
            "**Format:** Adults-only comic",
        }
        if format_lines[0] not in allowed_formats:
            failures.append(f"{slug}: nonstandard Format value: {format_lines[0]!r}")
            continue
        legacy_meta = re.findall(
            r"(?im)^\s*(?:[-*]\s*)?\*\*(?:Author|Genre|Themes?|Tags?|Structure|Setting|Leads?|The Warden):\*\*",
            syn_text,
        )
        if legacy_meta:
            failures.append(f"{slug}: legacy synopsis metadata remains; use only Format and Length")
            continue

        # (3) blurb is a substantial but concise narrative.
        blurb = extract_blurb(syn_text)
        if not blurb:
            failures.append(f"{slug}: synopsis blurb is EMPTY (likely meta-first)")
            continue
        first = blurb.splitlines()[0].strip()
        if _bold_meta_re.match(first) or first.startswith("- ") or _heading_re.match(first):
            failures.append(f"{slug}: blurb starts with meta, not narrative: {first[:50]!r}")
            continue
        blurb_words = len(re.findall(r"\b[\w’'-]+\b", blurb))
        is_comic = any((d / "pages").glob("page-*.png"))
        min_words = 55 if is_comic else 85
        if blurb_words < min_words or blurb_words > 240:
            failures.append(
                f"{slug}: blurb length {blurb_words} words outside professional band "
                f"{min_words}-240"
            )
    print(f"Checked {checked} publishable book(s).")
    if failures:
        print("RESULT: FAIL")
        for f in failures:
            print("  - " + f)
        sys.exit(1)
    print("RESULT: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
