#!/usr/bin/env python3
"""Generate the static Tapio Kinnunen book-library site (GitHub Pages ready).

Scans ~/Books/*/ for finished books and emits a static site into ./docs.

A "finished book" needs, inside ~/Books/<dir>/
    cover/<something>-cover.png     (portrait cover)
    cover/synopsis.md               (title line + "By <author>" + blurb/metadata)
    manuscript/<something>.md       (full manuscript, rendered for "Read online")
    manuscript/<something>.pdf      (optional; exposed as "Download PDF")

Adding a future book = drop it under ~/Books and rerun this script. No manual edits.

Usage:
    python3 generate.py                         # uses ~/Books
    BOOKS_DIR=/path/to/Books python3 generate.py

The `markdown` package is auto-installed into a local .venv_publish venv on
first run if it is not already importable, so this script works under any
python3 (including the cron's interpreter) with no manual setup.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _ensure_markdown():
    """Import markdown, auto-bootstrapping a local venv if needed.

    The cron runner uses Hermes' own python3, which does not have markdown.
    Rather than depend on a manually-created venv, we create/use .venv_publish
    next to this script and `uv pip install markdown` into it. This makes
    `python3 generate.py` work unattended in every context.
    """
    try:
        import markdown  # noqa: F401
        return
    except ImportError:
        pass
    here = Path(__file__).resolve().parent
    venv = here / ".venv_publish"
    vpy = venv / "bin" / "python"
    if not venv.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    # prefer uv if available (fast), else venv pip
    if shutil.which("uv"):
        subprocess.run(["uv", "pip", "install", "--python", str(vpy), "markdown"],
                       check=True)
    else:
        subprocess.run([str(vpy), "-m", "pip", "install", "markdown"], check=True)
    # re-exec the script under the venv interpreter so markdown is importable
    os.execv(str(vpy), [str(vpy), __file__, *sys.argv[1:]])


_ensure_markdown()
import markdown  # now guaranteed available


# --- canonical-manuscript / synopsis reconciliation -----------------------
# A book's canonical manuscript is manuscript/<slug>.md. Anything under an
# 'archive/' directory is a historical draft and must NEVER be published or
# counted. When a book is edited, its synopsis (especially the Length line)
# is auto-reconciled so the site never shows a stale word count.


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def word_count_md(path: Path) -> int:
    """True word count via wc -w on the canonical manuscript (mirrors the
    numbers reported to the reader; ignores markdown markup)."""
    import subprocess
    try:
        out = subprocess.run(["wc", "-w", str(path)],
                             capture_output=True, text=True, check=True)
        return int(out.stdout.split()[0])
    except Exception:
        # fall back to a python count if wc is unavailable
        txt = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
        return len(txt.split())


def reconcile_synopsis(syn_path: Path, wc: int, pages: int = 0) -> bool:
    """Rewrite the **Length:** line in synopsis.md. For comics (pages > 0) the
    value is the page count; for novels it is the canonical manuscript's real
    word count. Returns True if the file was changed.

    Preserves every other line and the line's original prefix (bullet,
    indentation, or none). Idempotent: re-running on an already-correct
    synopsis is a no-op.
    """
    raw = syn_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    new_lines = []
    changed = False
    # Match any line that contains a **Length:** marker, with any leading
    # bullet/whitespace prefix. Capture the prefix so we keep it.
    pat = re.compile(r"^(?P<pre>[\s\*\-\>]*)\*\*(?i:Length):\*\*\s*.+")
    if pages > 0:
        new_val = f"**Length:** {pages} pages"
    else:
        new_val = f"**Length:** {wc:,} words"
    for ln in lines:
        m = pat.match(ln)
        if m:
            new_ln = f"{m.group('pre')}{new_val}"
            if ln != new_ln:
                changed = True
            new_lines.append(new_ln)
        else:
            new_lines.append(ln)
    if changed:
        syn_path.write_text("\n".join(new_lines).rstrip() + "\n",
                            encoding="utf-8")
    return changed


def load_state() -> dict:
    if GENSTATE.exists():
        try:
            return json.loads(GENSTATE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    GENSTATE.write_text(json.dumps(state, indent=2, sort_keys=True),
                        encoding="utf-8")

# --- configuration ---------------------------------------------------------
# GitHub repo name. The Pages site is served at https://<user>.github.io/<REPO>/
# so every asset/link is rooted at /<REPO>/. If you rename the repo, change REPO.
REPO = "library"
BASE = f"/{REPO}"

ROOT = Path(__file__).resolve().parent
GENSTATE = ROOT / ".genstate.json"
BOOKS_ROOT = Path(os.environ.get("BOOKS_DIR", Path.home() / "Books")).expanduser()
OUT = ROOT / "docs"
SRC = ROOT / "src"

SITE_TITLE = "The Library of Tapio Kinnunen"
TAGLINE = "Fantasy and science fiction from the Hermes writer agent."
# SFWA's conventional lower bound for a novel is 40,000 words. Shorter
# prose works belong on the Novellas page (including novelettes).
NOVEL_MIN_WORDS = 40_000

MD_EXT = ["extra"]


# --- helpers ---------------------------------------------------------------
def md_to_html(text: str) -> str:
    return markdown.markdown(text, extensions=MD_EXT)


def asset(*parts: str) -> str:
    return BASE + "/assets/" + "/".join(parts)


def page_url(*parts: str) -> str:
    return BASE + "/" + "/".join(parts)


def _adult_content_from_status(text: str) -> bool:
    """Return True only for an explicit truthy adult_content status flag."""
    return bool(re.search(
        r"(?im)^adult_content:\s*(?:true|yes|1|on)\s*$", text
    ))


def _status_explicitly_incomplete(text: str) -> bool:
    """Block projects whose top-level ledger says unfinished or withdrawn."""
    incomplete = {"draft", "drafting", "in-progress", "in_progress", "repair", "production", "withdrawn"}
    values = re.findall(r"(?im)^(?:phase|status):\s*[\"']?([^\n\"']+)", text)
    return any(value.strip().lower() in incomplete for value in values)


def _genre_from_status(text: str) -> str:
    """Classify a book from top-level status genre/category metadata.

    The historical library predates consistent genre fields and consisted of
    science fiction, so an unlabelled legacy book defaults to science fiction.
    New fantasy projects carry an explicit ``category: ... fantasy`` field.
    Only top-level genre/category lines are considered so unrelated ledger
    fields such as ``last_fantasy_subgenre`` cannot misclassify a book.
    """
    values = re.findall(
        r"(?im)^(?:genre|category):\s*[\"']?([^\n\"']+)", text
    )
    labels = " ".join(values).lower()
    if "fantasy" in labels:
        return "fantasy"
    if (re.search(r"\bscience[ -]?fiction\b", labels)
            or re.search(r"\bsci[ -]?fi\b", labels)
            or re.search(r"\bhard\s+sf\b", labels)
            or re.search(r"\bsf\b", labels)):
        return "science-fiction"
    return "science-fiction"


def age_gate_markup() -> str:
    """Reusable 18+ interstitial for adult sections and reader pages."""
    return f"""<div class="age-gate" id="age-gate" role="dialog" aria-modal="true" aria-labelledby="age-gate-title">
  <div class="age-gate-card">
    <p class="age-gate-badge">18+</p>
    <h1 id="age-gate-title">Adults only</h1>
    <p>This section contains erotic illustrated fiction featuring consenting adult characters.</p>
    <p>By continuing, you confirm that you are at least 18 years old and may legally view adult content where you live.</p>
    <div class="age-gate-actions">
      <button class="btn btn-primary" type="button" onclick="confirmAdultAccess()">I am 18 or older</button>
      <a class="btn" href="{page_url('index.html')}">Return to the library</a>
    </div>
  </div>
</div>
<script>
(function () {{
  const gate = document.getElementById('age-gate');
  if (!gate) return;
  if (localStorage.getItem('tapio-adult-access') === 'confirmed') gate.hidden = true;
  window.confirmAdultAccess = function () {{
    localStorage.setItem('tapio-adult-access', 'confirmed');
    gate.hidden = true;
  }};
}})();
</script>"""


def discover_books():
    books = []
    if not BOOKS_ROOT.exists():
        print(f"[warn] BOOKS_ROOT not found: {BOOKS_ROOT}")
        return books
    for d in sorted(BOOKS_ROOT.iterdir()):
        if not d.is_dir():
            continue
        # Skip auxiliary / non-book directories (e.g. _venv, _autopilot_state)
        if d.name.startswith("_") or d.name.startswith("."):
            continue
        slug = d.name
        cover_canonical = d / "cover" / f"{slug}-cover.png"

        # --- Cover selection (the "raw art vs typeset" trap) ---
        # Several books ship BOTH a raw AI art file (cover/art.png / artwork.png /
        # art-*raw*.png) AND a properly typeset *-cover.png that the author
        # generated via cover/make_cover.py. If the slug-canonical file happens
        # to be the raw art (same md5 as the raw sibling), the site ships a
        # text-less cover. We resolve the right file by:
        #   1. computing md5 of the slug-canonical file (if present),
        #   2. identifying "raw art" siblings by md5 match against the canonical
        #      file (or by path keyword: contains "raw", "art", or "base"),
        #   3. preferring any other *-cover.png sibling whose md5 DIFFERS (the
        #      typeset one). If none differ, fall through to the existing
        #      auto-heal-and-pick-first logic.
        def _md5(p):
            try:
                import hashlib
                return hashlib.md5(p.read_bytes()).hexdigest()
            except Exception:
                return None

        def _is_raw_artifact(p):
            """Match filename patterns used across the library to denote raw AI art."""
            n = p.name.lower()
            return (
                n == "art.png" or n == "artwork.png" or n == "cover.png"
                or n == "cover.jpg" or n.startswith("art-") or n.startswith("art_")
                or "raw" in n or n == "base.png"
            )

        # Collect all PNGs in cover/ once; we reuse the list below.
        all_cover_pngs = [p for p in (d / "cover").glob("*.png") if p.is_file()]
        canonical_md5 = _md5(cover_canonical) if cover_canonical.exists() else None
        # md5 -> [paths] for fast lookup
        md5_index = {}
        for p in all_cover_pngs:
            h = _md5(p)
            if h:
                md5_index.setdefault(h, []).append(p)
        # Find any sibling "raw art" whose md5 matches the canonical. If so the
        # canonical is the raw art and we must promote a *typeset* sibling instead.
        typeset_sibling = None
        if canonical_md5 and md5_index.get(canonical_md5):
            siblings_same_md5 = md5_index[canonical_md5]
            is_canonical_raw = (
                cover_canonical.name.lower() in {"cover.png", "art.png", "artwork.png"}
                or any(_is_raw_artifact(s) for s in siblings_same_md5 if s != cover_canonical)
            )
            if is_canonical_raw:
                # Look for any other *-cover.png whose md5 differs (= the typeset one).
                for p in all_cover_pngs:
                    if p == cover_canonical:
                        continue
                    if not p.name.endswith("-cover.png"):
                        continue
                    h = _md5(p)
                    if h and h != canonical_md5:
                        typeset_sibling = p
                        break

        if typeset_sibling is not None:
            # Promote the typeset sibling over the raw canonical. This is the
            # "raw art vs typeset" fix: the canonical file exists but is the
            # wrong one.
            try:
                import shutil
                shutil.copy2(typeset_sibling, cover_canonical)
                print(f"[auto-fix] {slug}: promoted typeset sibling {typeset_sibling.name} "
                      f"over raw-art canonical ({Path(cover_canonical).name}); same md5 as "
                      f"{', '.join(sorted({Path(s).name for s in md5_index[canonical_md5]}))}")
            except Exception as e:
                print(f"[warn] {slug}: failed to promote typeset sibling: {e}")
        elif not cover_canonical.exists():
            # Auto-heal: pick the best alternate. If any typeset *-cover.png
            # exists, prefer it OVER a bare raw-art filename, so we never
            # silently pick raw art just because it sorts earlier.
            typeset_alts = [p for p in all_cover_pngs if p.name.endswith("-cover.png")]
            raw_alts = [p for p in all_cover_pngs if _is_raw_artifact(p)]
            other_alts = [p for p in all_cover_pngs
                          if p not in typeset_alts and p not in raw_alts]
            src = (
                (typeset_alts + other_alts + raw_alts)[:1]
            )[0] if (typeset_alts or other_alts or raw_alts) else None
            if src is not None:
                try:
                    import shutil
                    shutil.copy2(src, cover_canonical)
                    tag = ("typeset" if src in typeset_alts
                           else "raw" if src in raw_alts
                           else "other")
                    print(f"[auto-fix] {slug}: copied {src.name} -> {cover_canonical.name} "
                          f"(picked {tag})")
                except Exception as e:
                    print(f"[warn] {slug}: failed to auto-fix cover: {e}")

        # Final cover lookup — the canonical name should now be correct.
        cover = (list(d.glob(f"cover/{slug}-cover.png"))
                 or list(d.glob("cover/cover.png"))
                 or list(d.glob("cover/Cover.png"))
                 or list(d.glob("cover/*-cover.png")))
        cover = cover[0] if cover else None
        # House rule (enforced 2026-07-29): published covers MUST be portrait
        # (h > w). Library standard is 576x1024 (9:16). Landscape covers
        # silently shipped on the-calibration-of-gaps because the raw AI
        # art came back 16:9 — refuse the book so a human retypesets it
        # before the next publish tick. A landscape cover cannot typeset
        # title + byline without breaking the layout, so failing here is
        # cheaper than the OCR gate catching it later.
        if cover is not None:
            try:
                from PIL import Image as _PILImage
                with _PILImage.open(cover) as _cim:
                    _cim.load()
                    _cw, _ch = _cim.size
                if _ch <= _cw:
                    print(
                        f"[fail-portrait] {slug}: cover {cover.name} is landscape "
                        f"({_cw}x{_ch}, h/w={_ch/_cw:.3f}); must be portrait "
                        f"(h > w; house standard 576x1024). Regenerate with "
                        f"cover/make_cover.py using portrait raw art."
                    )
                    continue
            except Exception as _e:
                print(f"[warn] {slug}: portrait check skipped: {_e}")
        syn = d / "cover" / "synopsis.md"
        syn = syn if syn.exists() else None
        mds = (list(d.glob(f"manuscript/{slug}.md"))
               or [p for p in d.glob("manuscript/*.md")
                   if not p.name.startswith("~")
                   and "archive" not in p.parts])
        mdfile = mds[0] if mds else None
        pdfs = (list(d.glob(f"manuscript/{slug}.pdf"))
                or [p for p in d.glob("manuscript/*.pdf")
                    if "archive" not in p.parts])
        pdf = pdfs[0] if pdfs else None
        # A book is a comic if it ships a pages/ dir with page-N.png panels.
        page_imgs = sorted(
            [p for p in (d / "pages").glob("page-*.png")
             if not p.name.startswith("~") and "archive" not in p.parts],
            key=lambda p: int("".join(filter(str.isdigit, p.stem)) or 0),
        )
        is_comic = len(page_imgs) > 0
        status_path = d / "status.yaml"
        status_text = (status_path.read_text(encoding="utf-8")
                       if status_path.exists() else "")
        if _status_explicitly_incomplete(status_text):
            print(f"[skip-incomplete] {slug}: status ledger is not complete")
            continue
        is_adult = _adult_content_from_status(status_text)
        genre = _genre_from_status(status_text)
        if not (cover and syn and mdfile):
            # Build a precise skip reason so future misnamings are loud, not silent.
            reasons = []
            if not cover:
                present = [p.name for p in d.glob("cover/*.png")]
                reasons.append(
                    f"no cover matching cover/{slug}-cover.png (found: {present or 'none'})"
                )
            if not syn:
                reasons.append("missing cover/synopsis.md")
            if not mdfile:
                reasons.append("missing manuscript/<slug>.md")
            print(f"[skip] {slug}: " + "; ".join(reasons))
            continue
        digest = _sha256(mdfile)
        wc = word_count_md(mdfile)
        # Compute latest mtime across all relevant book files for "newest first" sorting
        latest_mtime = 0
        for pattern in ["cover/*-cover.png", "cover/synopsis.md", "manuscript/*.md", "manuscript/*.pdf"]:
            for f in d.glob(pattern):
                if "archive" not in f.parts and not f.name.startswith("~"):
                    mtime = f.stat().st_mtime
                    if mtime > latest_mtime:
                        latest_mtime = mtime
        books.append({"slug": slug, "cover": cover, "syn": syn,
                      "md": mdfile, "pdf": pdf,
                      "pages": page_imgs, "is_comic": is_comic,
                      "is_adult": is_adult,
                      "genre": genre,
                      "md_hash": digest, "wc": wc, "mtime": latest_mtime})
    return books


# --- PDF auto-build --------------------------------------------------------
# The site always exposes a "Download PDF" link when manuscript/<slug>.pdf
# exists. To guarantee every published book has a PDF (never ship without
# one), generate.py builds the PDF itself if it is missing, using the book's
# own build_pdf.py when present, else a built-in fpdf2 fallback. fpdf2 must be
# importable by the interpreter that runs build_pdf.py; we prefer the Books
# venv (which has fpdf2), falling back to system python3.
_BOOKS_VENV = BOOKS_ROOT / "_venv" / "bin" / "python"


def _pdf_builder_interpreter() -> str:
    if _BOOKS_VENV.exists():
        return str(_BOOKS_VENV)
    return sys.executable


def ensure_pdf(b: dict) -> None:
    """Build manuscript/<slug>.pdf if it is missing. Idempotent."""
    if b["pdf"] is not None:
        return
    slug = b["slug"]
    book_dir = b["md"].parent.parent
    target = book_dir / "manuscript" / f"{slug}.pdf"
    builder = book_dir / "build_pdf.py"
    interp = _pdf_builder_interpreter()
    try:
        if builder.exists():
            subprocess.run([interp, str(builder)], check=True,
                           cwd=str(book_dir),
                           capture_output=True, text=True)
        else:
            # built-in fallback: a minimal fpdf2 typesetter
            _build_pdf_fallback(b["md"], target)
        if target.exists():
            b["pdf"] = target
            print(f"[pdf]  {slug}: built {target.name}")
        else:
            print(f"[warn] {slug}: PDF build produced no file; skipping PDF link")
    except Exception as e:
        print(f"[warn] {slug}: PDF build failed ({e}); skipping PDF link")


def _build_pdf_fallback(md_path: Path, out_path: Path) -> None:
    """Minimal PDF builder used only if a book has no build_pdf.py.

    Requires fpdf2 in the running interpreter; if unavailable, raises so the
    caller can skip the PDF gracefully.
    """
    from fpdf import FPDF  # may ImportError -> caller skips PDF
    import re as _re
    FONT = "/usr/share/fonts/truetype/dejavu"
    text = md_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    class _P(FPDF):
        def footer(self):
            self.set_y(-14)
            self.set_font("DJ", "", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 8, md_path.parent.parent.name, align="L")
            self.cell(0, 8, f"Page {self.page_no()}", align="R")

    pdf = _P(format="LETTER")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(25.4, 22, 25.4)
    pdf.add_font("DJ", "", f"{FONT}/DejaVuSans.ttf")
    pdf.add_font("DJ", "B", f"{FONT}/DejaVuSans-Bold.ttf")
    pdf.add_page()
    first = True
    for raw in lines:
        line = raw.strip()
        if not line:
            pdf.ln(2)
            continue
        if line.startswith("# "):
            pdf.set_font("DJ", "B", 26 if first else 12.5)
            pdf.set_text_color(27, 42, 74)
            pdf.multi_cell(0, 12 if first else 7, _re.sub(r"[*]", "", line[2:]),
                           align="C")
            pdf.ln(2)
            first = False
            continue
        if line.startswith("## "):
            pdf.set_font("DJ", "B", 15)
            pdf.set_text_color(27, 42, 74)
            pdf.ln(4)
            pdf.multi_cell(0, 8, _re.sub(r"[*]", "", line[3:]), align="C")
            pdf.ln(2)
            continue
        if line == "---":
            pdf.ln(2)
            continue
        pdf.set_font("DJ", "", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 5.4, "    " + _re.sub(r"[*]", "", line), align="J")
        pdf.ln(1.5)
    pdf.output(str(out_path))



def parse_synopsis(path: Path):
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = None
    title_idx = None
    for i, ln in enumerate(lines):
        if title_idx is None and ln.startswith("# "):
            title = ln[2:].strip()
            title = re.split(r"\s*[—–-]\s*Synopsis\b", title, flags=re.I)[0].strip()
            title_idx = i
            break
    author_re = re.compile(r"^\*\*(.+?)\*\*$|^\*(.+?)\*$")
    by_re = re.compile(r"^(?:By|Author)\b[**:]?\s*(.+?)\s*$", re.I)
    author = None
    for ln in lines:
        m = author_re.match(ln.strip())
        if m:
            author = (m.group(1) or m.group(2)).strip()
            break
        m = by_re.match(ln.strip())
        if m:
            author = "By " + m.group(1).strip()
            break
    rest = lines[title_idx + 1:] if title_idx is not None else lines
    body_lines = [ln for ln in rest
                  if not author_re.match(ln.strip())
                  and not by_re.match(ln.strip())]
    blurb = extract_blurb_from_lines(lines, title_idx)
    if author and author.lower().startswith("by "):
        author_name = author[3:].strip()
    else:
        author_name = author or "Tapio Kinnunen"
    return {"title": title or path.parent.parent.name,
            "author": author_name, "body": "\n".join(body_lines).strip(),
            "blurb": blurb}


# --- blurb extraction (used by both generate.py and verify_site.py) -------
# A "meta" line is a bold/italic label like **Genre:**, a bullet, a
# heading, or a trailing italic credit (e.g. "*71,000 words · by ...*").
# The blurb is the contiguous narrative block. If a "## Synopsis" (or
# similar) restart heading appears, the narrative starts AFTER it.
# Canonical Markdown is ``**Label:** value`` (colon inside bold), while a
# few legacy files used ``**Label**: value``. Recognize both forms.
_BLURB_BOLD_META_RE = re.compile(r"^\*\*(?:[^*]*:\*\*|[^*]+\*\*\s*:)")
_BLURB_ITALIC_META_RE = re.compile(r"^\*[^*].*?\*\s*$")
_BLURB_HEADING_RE = re.compile(r"^#{1,6}\s")
_BLURB_BULLET_RE = re.compile(r"^\s*[-*]\s")
_BLURB_AUTHOR_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*$|^\*(.+?)\*$")
_BLURB_BY_RE = re.compile(r"^(?:By|Author)\b[**:]?\s*(.+?)\s*$", re.I)


def _is_blurb_meta(s: str) -> bool:
    if _BLURB_BULLET_RE.match(s) or _BLURB_HEADING_RE.match(s):
        return True
    if _BLURB_BOLD_META_RE.match(s):
        return True
    if _BLURB_ITALIC_META_RE.match(s) and ("words" in s.lower()
                                           or "by tapio" in s.lower()
                                           or "by adrian" in s.lower()):
        return True
    return False


def extract_blurb_from_lines(lines, title_idx) -> str:
    """Robustly extract the narrative blurb from a synopsis's line list.

    `title_idx` is the line index of the `# Title` heading, or None when the
    file has no title heading. The blurb is the contiguous narrative block
    after the title block (or, if a `## Synopsis`/`## Premise` restart
    heading exists, after it). Returns "" only when the file is genuinely
    empty or entirely meta-lines.
    """
    rest = lines[title_idx + 1:] if title_idx is not None else lines
    start = 0
    for i, ln in enumerate(rest):
        s = ln.strip()
        if _BLURB_HEADING_RE.match(s) and re.search(r"synopsis|premise", s, re.I):
            start = i + 1
            break
    blurb_lines, started = [], False
    for ln in rest[start:]:
        s = ln.strip()
        if _is_blurb_meta(s):
            break
        if _BLURB_AUTHOR_BOLD_RE.match(s) or _BLURB_BY_RE.match(s):
            continue
        if not s:
            if started:
                blurb_lines.append(ln)
            continue
        started = True
        blurb_lines.append(ln)
    return "\n".join(blurb_lines).strip()


def heal_synopsis(syn_path: Path, *, title: str, author: str,
                  wc: int, pages: int = 0, is_adult: bool = False) -> bool:
    """Canonicalize the public synopsis structure while preserving its blurb.

    Every published synopsis uses the same reader-facing order:
    title, house byline, narrative blurb, format, and length.  The creative
    blurb is never generated here; an absent/weak blurb is left as a visible
    placeholder so ``verify_site.py`` blocks publication instead of shipping
    generic marketing copy.
    """
    raw = syn_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title_idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), None)
    blurb = extract_blurb_from_lines(lines, title_idx)

    # Legacy metadata-first files can hide a later narrative block from the
    # contiguous blurb parser. Recover prose paragraphs without preserving old
    # Author/Genre/Tags/Structure blocks or duplicate credits.
    if not blurb:
        paragraphs = re.split(r"\n\s*\n", raw)
        candidates = []
        for para in paragraphs:
            s = para.strip()
            if not s or s.startswith("#") or _is_blurb_meta(s):
                continue
            if _BLURB_AUTHOR_BOLD_RE.match(s) or _BLURB_BY_RE.match(s):
                continue
            if re.match(r"(?i)^(?:by|author|genre|themes?|tags?|length|format|structure|setting)\b", s):
                continue
            candidates.append(s)
        blurb = "\n\n".join(candidates)

    if not blurb:
        blurb = "Synopsis forthcoming."

    # The public house byline is intentionally fixed even when a stale project
    # ledger still carries an older author field.
    byline = "**By Tapio Kinnunen**"
    if pages > 0:
        format_name = "Adults-only graphic novel" if is_adult else "Graphic novel"
        length = f"{pages} pages"
    else:
        format_name = "Novelette" if wc < 17_500 else "Novella" if wc < 40_000 else "Novel"
        length = f"{wc:,} words"

    canonical = (
        f"# {title}\n\n"
        f"{byline}\n\n"
        f"{blurb.strip()}\n\n"
        f"**Format:** {format_name}\n"
        f"**Length:** {length}\n"
    )
    if canonical == raw:
        return False
    syn_path.write_text(canonical, encoding="utf-8")
    return True


def _book_title(b: dict) -> str:
    """Read the public title without mistaking chapter-state titles for it.

    The synopsis H1 is authoritative.  Some status ledgers contain many
    nested ``title:`` keys for chapters, so scanning YAML lines for the first
    key can silently rename a book (for example, *The Hollow Light* became
    "The Budget").  Consult the status ledger only when no synopsis H1 exists.
    """
    syn = b.get("syn")
    if syn and Path(syn).exists():
        try:
            for ln in Path(syn).read_text(encoding="utf-8").splitlines():
                if ln.startswith("# "):
                    return re.split(r"\s*[—–-]\s*Synopsis\b", ln[2:].strip(), flags=re.I)[0].strip()
        except Exception:
            pass
    status = b["md"].parent.parent / "status.yaml"
    if status.exists():
        try:
            txt = status.read_text(encoding="utf-8")
            for ln in txt.splitlines():
                stripped = ln.strip()
                if stripped.startswith("title:"):
                    return stripped.split(":", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return b["slug"].replace("-", " ").title()


def _book_author(b: dict) -> str:
    """Read the book author from status.yaml (preferred) or fall back
    to the site default."""
    status = b["md"].parent.parent / "status.yaml"
    if status.exists():
        try:
            txt = status.read_text(encoding="utf-8")
            for ln in txt.splitlines():
                stripped = ln.strip()
                if stripped.startswith("author:"):
                    return stripped.split(":", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return "Tapio Kinnunen"


# --- page builders ----------------------------------------------------------
def base_html(*, title, desc, body, extra_head="", nav="all", adult=False):
    t = html.escape(title)
    d = html.escape(desc)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nav_items = [
        ("All", page_url("index.html"), "all"),
        ("Fantasy", page_url("fantasy.html"), "fantasy"),
        ("Sci-Fi", page_url("science-fiction.html"), "science-fiction"),
        ("Novels", page_url("novels.html"), "novels"),
        ("Novellas", page_url("novellas.html"), "novellas"),
        ("Comics", page_url("comics.html"), "comics"),
        ("After Dark · 18+", page_url("adult-comics.html"), "adult"),
    ]
    nav_html = '<nav class="site-nav" aria-label="Categories">'
    for label, href, key in nav_items:
        cls = "site-nav-link" + (" active" if key == nav else "")
        nav_html += f'<a class="{cls}" href="{href}">{label}</a>'
    nav_html += "</nav>"
    gate = age_gate_markup() if adult else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t} · {SITE_TITLE}</title>
<meta name="description" content="{d}">
<link rel="icon" href="{asset('favicon.svg')}">
<link rel="stylesheet" href="{asset('style.css')}">
{extra_head}
</head>
<body>
{gate}
<header class="site-head">
  <div class="wrap site-head-inner">
    <a class="brand" href="{BASE}/">{SITE_TITLE}</a>
    <p class="tagline">{TAGLINE}</p>
    {nav_html}
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-foot">
  <div class="wrap">
    <p>{SITE_TITLE} · generated {stamp} from the Hermes writer agent.</p>
  </div>
</footer>
</body>
</html>"""


def card(b):
    syn = b["syn_parsed"]
    cover_url = page_url("books", b["slug"], f"{b['slug']}-cover.png")
    book_url = page_url("books", b["slug"], "index.html")
    pdf_url = (page_url("books", b["slug"], b["pdf_name"])
               if b["pdf"] else None)
    blurb_html = md_to_html(syn["blurb"]) if syn["blurb"] else ""
    pdf_btn = (f'<a class="btn btn-sm" href="{pdf_url}">PDF</a>'
               if pdf_url else "")
    adult_badge = ('<span class="adult-card-badge">18+</span>'
                   if b.get("is_adult") else "")
    return f"""<article class="card{' adult-card' if b.get('is_adult') else ''}">
  <a class="card-cover-link" href="{book_url}">
    <img class="card-cover" src="{cover_url}" alt="Cover of {html.escape(syn['title'])}" loading="lazy">
{adult_badge}
  </a>
  <div class="card-body">
    <p class="card-author">{html.escape(syn['author'])}</p>
    <h2 class="card-title"><a href="{book_url}">{html.escape(syn['title'])}</a></h2>
    <div class="card-blurb">{blurb_html}</div>
    <div class="card-actions">
      <a class="btn btn-primary btn-sm" href="{book_url}">View & read</a>
      {pdf_btn}
    </div>
  </div>
</article>"""


def build_section(title, subtitle, books_list, nav, adult=False):
    if not books_list:
        body = (f'<section class="hero"><h1>{html.escape(title)}</h1>'
                f'<p class="lede">{html.escape(subtitle)}</p></section>\n'
                '<p class="empty">Nothing here yet.</p>')
    else:
        grid = "\n".join(card(b) for b in books_list)
        body = (f'<section class="hero"><h1>{html.escape(title)}</h1>'
                f'<p class="lede">{html.escape(subtitle)}</p></section>\n'
                f'<section class="grid-section">\n<div class="grid">\n'
                f'{grid}\n</div>\n</section>')
    return base_html(title=title, desc=subtitle, body=body, nav=nav, adult=adult)


def category_for_book(b):
    """Return the canonical category page URL, label, and nav key."""
    if b.get("is_adult"):
        return page_url("adult-comics.html"), "After Dark", "adult"
    if b.get("is_comic"):
        return page_url("comics.html"), "Comics", "comics"
    if b.get("genre") == "fantasy":
        return page_url("fantasy.html"), "Fantasy", "fantasy"
    return page_url("science-fiction.html"), "Science Fiction", "science-fiction"


def build_home(books):
    if not books:
        return base_html(title="Books", desc=TAGLINE,
                         body='<section class="hero"><h1>Books by Tapio Kinnunen</h1>'
                              '<p class="lede">Fantasy and science fiction, set down by '
                              'the Hermes writer agent.</p></section>\n'
                              '<p class="empty">No books published yet.</p>')

    # Single unified grid: all books (comics + novels) sorted newest first
    grid = "\n".join(card(b) for b in books)
    body = f"""<section class="hero">
  <h1>Books by Tapio Kinnunen</h1>
  <p class="lede">Fantasy and science fiction, set down by the Hermes writer agent. Read online or download the PDF.</p>
</section>
<section class="grid-section">
<div class="grid">
{grid}
</div>
</section>"""
    return base_html(title="Books", desc=TAGLINE, body=body, nav="all")


def build_book(b):
    syn = b["syn_parsed"]
    cover_url = page_url("books", b["slug"], f"{b['slug']}-cover.png")
    read_url = page_url("books", b["slug"], "read.html")
    pdf_url = (page_url("books", b["slug"], b["pdf_name"])
               if b["pdf"] else None)
    gallery_url = (page_url("books", b["slug"], "gallery.html")
                   if b["is_comic"] else None)
    syn_html = md_to_html(syn["body"])
    actions = []
    if b["is_comic"] and gallery_url:
        actions.append(f'<a class="btn btn-primary" href="{gallery_url}">Read the comic</a>')
    else:
        actions.append(f'<a class="btn btn-primary" href="{read_url}">Read online</a>')
    if pdf_url:
        actions.append(f'<a class="btn" href="{pdf_url}">Download PDF</a>')
    back_url, back_label, section_nav = category_for_book(b)
    actions.append(f'<a class="btn btn-ghost" href="{back_url}">{back_label}</a>')
    adult_note = ("""<aside class="adult-content-note"><strong>18+ adult content.</strong> This erotic comic features consenting adult characters.</aside>"""
                  if b.get("is_adult") else "")
    body = f"""{adult_note}<article class="book">
  <div class="book-hero">
    <img class="book-cover" src="{cover_url}" alt="Cover of {html.escape(syn['title'])}">
    <div class="book-meta">
      <p class="eyebrow">{html.escape(syn['author'])}</p>
      <h1 class="book-title">{html.escape(syn['title'])}</h1>
      <div class="book-syn">{syn_html}</div>
      <div class="actions">{''.join(actions)}</div>
    </div>
  </div>
</article>"""
    return base_html(title=syn["title"], desc=(syn["blurb"] or TAGLINE), body=body,
                     nav=section_nav,
                     adult=b.get("is_adult", False))


def build_gallery(b):
    syn = b["syn_parsed"]
    section_url, section_label, _ = category_for_book(b)
    bar = f"""<header class="read-bar">
  <a href="{section_url}">{section_label}</a>
  <span class="read-title">{html.escape(syn['title'])}</span>
  <a href="{page_url('books', b['slug'], 'index.html')}">About</a>
  <a href="{page_url('books', b['slug'], 'read.html')}">Script</a>
</header>"""
    figs = []
    for i, p in enumerate(b["pages"], 1):
        src = page_url("books", b["slug"], f"pages/{p.name}")
        figs.append(f'<figure class="comic-page">'
                    f'<img src="{src}" alt="{html.escape(syn["title"])} page {i}" loading="lazy">'
                    f'<figcaption>Page {i}</figcaption></figure>')
    body = (f"{bar}\n<main class=\"wrap gallery\">\n" + "\n".join(figs) + "\n</main>")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Read {html.escape(syn['title'])} · {SITE_TITLE}</title>
<link rel="icon" href="{asset('favicon.svg')}">
<link rel="stylesheet" href="{asset('style.css')}">
</head>
<body class="read-page">
{age_gate_markup() if b.get('is_adult') else ''}
{body}
</body>
</html>"""


def build_read(b, manuscript_html):
    syn = b["syn_parsed"]
    section_url, section_label, _ = category_for_book(b)
    book_url = page_url("books", b["slug"], "index.html")
    pdf_url = (page_url("books", b["slug"], b["pdf_name"])
               if b["pdf"] else None)
    pdf_link = f'<a href="{pdf_url}">PDF</a>' if pdf_url else ""
    gallery_link = (f'<a href="{page_url("books", b["slug"], "gallery.html")}">Comic</a>'
                    if b["is_comic"] else "")
    bar = f"""<header class="read-bar">
  <a href="{section_url}">{section_label}</a>
  <span class="read-title">{html.escape(syn['title'])}</span>
  {gallery_link}
  {pdf_link}
</header>"""
    foot = (f'<footer class="read-foot wrap">'
            f'<a href="{book_url}">← Back to {html.escape(syn["title"])}</a>'
            f'</footer>')
    body = (f"{bar}\n"
            f'<main class="wrap reader">'
            f'<article class="manuscript">{manuscript_html}</article>'
            f'</main>\n{foot}')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Read {html.escape(syn['title'])} · {SITE_TITLE}</title>
<link rel="icon" href="{asset('favicon.svg')}">
<link rel="stylesheet" href="{asset('style.css')}">
</head>
<body class="read-page">
{age_gate_markup() if b.get('is_adult') else ''}
{body}
</body>
</html>"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    for f in ("style.css", "favicon.svg"):
        srcf = SRC / f
        if srcf.exists():
            shutil.copy(srcf, OUT / "assets" / f)
    (OUT / ".nojekyll").write_text("")
    books = discover_books()

    # Mandatory machine-vision cover gate. Every exact cover hash must have a
    # PASS receipt produced after inspection with Hermes' vision_analyze tool.
    # A regenerated or re-typeset cover invalidates its receipt automatically.
    from tools.cover_vision_gate import verify_entries as verify_cover_vision_entries
    vision_errors = verify_cover_vision_entries(
        (b["slug"], Path(b["cover"])) for b in books
    )
    if vision_errors:
        details = "\n".join(f"  - {error}" for error in vision_errors)
        raise SystemExit(
            "BLOCKED: mandatory cover vision audit failed; site was not rebuilt:\n" + details
        )
    print(f"[vision-pass] {len(books)} exact cover hash(es) approved")

    # --- guarantee every book ships with a PDF ---------------------------
    # If a book has no manuscript/<slug>.pdf yet, build it now (via the book's
    # own build_pdf.py, or the built-in fallback). This enforces the rule that
    # the published library always exposes a "Download PDF" link per book.
    for b in books:
        ensure_pdf(b)

    # --- synopsis auto-reconciliation + edit detection --------------------
    # Whenever a book's canonical manuscript changes (hash differs from the
    # last generation), we recompute its true word count and rewrite the
    # **Length:** line in cover/synopsis.md so the published site can never
    # show a stale count. This runs on EVERY generate, so editing a book and
    # re-running is enough to keep the synopsis honest.
    state = load_state()
    for b in books:
        slug = b["slug"]
        prev = state.get(slug, {})
        edited = prev.get("md_hash") != b["md_hash"]
        if edited:
            if prev:
                print(f"[edit] {slug}: manuscript changed since last build "
                      f"(was {prev.get('wc')} words, now {b['wc']})")
            else:
                print(f"[new]  {slug}: first build ({b['wc']} words)")
        changed = reconcile_synopsis(b["syn"], b["wc"], pages=len(b["pages"]))
        if changed:
            print(f"[sync] {slug}: synopsis Length updated -> {b['wc']:,} words")
        # Auto-heal malformed synopsis (missing # title / By-line / blurb).
        # Idempotent. Cheap. Run BEFORE parse_synopsis so the parsed blurb
        # is non-empty and the verify_site gate passes.
        healed = heal_synopsis(
            b["syn"],
            title=_book_title(b),
            author=_book_author(b),
            wc=b["wc"],
            pages=len(b["pages"]),
            is_adult=b.get("is_adult", False),
        )
        if healed:
            print(f"[heal] {slug}: synopsis normalized (title/byline/blurb/Length)")
        state[slug] = {"md_hash": b["md_hash"], "wc": b["wc"]}
    save_state(state)

    parsed = []
    for b in books:
        syn = parse_synopsis(b["syn"])
        # Deterministic, slug-based asset names so links always match files.
        pdf_name = f"{b['slug']}.pdf" if b["pdf"] else None
        parsed.append(dict(
            b,
            syn_parsed=syn,
            pdf_name=pdf_name,
            is_novella=(not b["is_comic"] and b["wc"] < NOVEL_MIN_WORDS),
        ))
    # Sort by most recently modified first (newest book or most recently edited at top)
    parsed.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    public_list = [b for b in parsed if not b.get("is_adult")]
    (OUT / "index.html").write_text(build_home(public_list), encoding="utf-8")
    comics_list = [b for b in parsed if b["is_comic"] and not b.get("is_adult")]
    fantasy_list = [b for b in parsed
                    if b["genre"] == "fantasy" and not b.get("is_adult")]
    science_fiction_list = [b for b in parsed
                            if b["genre"] == "science-fiction" and not b.get("is_adult")]
    novels_list = [b for b in parsed
                   if not b["is_comic"] and not b["is_novella"] and not b.get("is_adult")]
    novellas_list = [b for b in parsed if b["is_novella"] and not b.get("is_adult")]
    adult_list = [b for b in parsed if b.get("is_adult")]
    (OUT / "fantasy.html").write_text(
        build_section(
            "Fantasy",
            "Adult fantasy shaped by magic, myth, strange cities, and costly wonders.",
            fantasy_list,
            "fantasy",
        ),
        encoding="utf-8")
    (OUT / "science-fiction.html").write_text(
        build_section(
            "Science Fiction",
            "Reasoned science fiction about distant worlds, altered societies, and difficult futures.",
            science_fiction_list,
            "science-fiction",
        ),
        encoding="utf-8")
    (OUT / "comics.html").write_text(
        build_section("Comics", "Graphic novels and illustrated stories.", comics_list, "comics"),
        encoding="utf-8")
    (OUT / "novels.html").write_text(
        build_section(
            "Novels",
            "Full-length fantasy and science-fiction novels of 40,000 words or more.",
            novels_list,
            "novels",
        ),
        encoding="utf-8")
    (OUT / "novellas.html").write_text(
        build_section(
            "Novellas",
            "Shorter fantasy and science fiction under 40,000 words, including novellas and novelettes.",
            novellas_list,
            "novellas",
        ),
        encoding="utf-8")
    (OUT / "adult-comics.html").write_text(
        build_section(
            "After Dark",
            "Adults-only erotic comics featuring consenting adult characters. 18+.",
            adult_list,
            "adult",
            adult=True,
        ),
        encoding="utf-8")
    for b in parsed:
        dest = OUT / "books" / b["slug"]
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(b["cover"], dest / f"{b['slug']}-cover.png")
        if b["pdf"]:
            shutil.copy(b["pdf"], dest / b["pdf_name"])
        (dest / "index.html").write_text(build_book(b), encoding="utf-8")
        md_text = b["md"].read_text(encoding="utf-8")
        (dest / "read.html").write_text(
            build_read(b, md_to_html(md_text)), encoding="utf-8")
        if b["is_comic"] and b["pages"]:
            pages_dest = dest / "pages"
            pages_dest.mkdir(parents=True, exist_ok=True)
            for p in b["pages"]:
                shutil.copy(p, pages_dest / p.name)
            (dest / "gallery.html").write_text(
                build_gallery(b), encoding="utf-8")
        print(f"[ok] {b['slug']}: {b['syn_parsed']['title']}")
    print(f"Built {len(parsed)} book(s) into {OUT}")


if __name__ == "__main__":
    main()