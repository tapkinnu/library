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
TAGLINE = "Novels from the Hermes writer agent — reasoned science fiction."

MD_EXT = ["extra"]


# --- helpers ---------------------------------------------------------------
def md_to_html(text: str) -> str:
    return markdown.markdown(text, extensions=MD_EXT)


def asset(*parts: str) -> str:
    return BASE + "/assets/" + "/".join(parts)


def page_url(*parts: str) -> str:
    return BASE + "/" + "/".join(parts)


def discover_books():
    books = []
    if not BOOKS_ROOT.exists():
        print(f"[warn] BOOKS_ROOT not found: {BOOKS_ROOT}")
        return books
    for d in sorted(BOOKS_ROOT.iterdir()):
        if not d.is_dir():
            continue
        slug = d.name
        cover = (list(d.glob(f"cover/{slug}-cover.png"))
                 or list(d.glob("cover/*-cover.png")))
        cover = cover[0] if cover else None
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
        if not (cover and syn and mdfile):
            print(f"[skip] {slug}: cover={bool(cover)} synopsis={bool(syn)} "
                  f"manuscript={bool(mdfile)}")
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
    # --- robust narrative blurb extraction -------------------------------
    # A "meta" line is a bold/italic label like **Genre:**, a bullet, a
    # heading, or a trailing italic credit (e.g. "*71,000 words · by ...*").
    # The blurb is the contiguous narrative block. If a "## Synopsis" (or
    # similar) restart heading appears, the narrative starts AFTER it.
    bold_meta_re = re.compile(r"^\*\*[^*]+\*\*\s*:")
    italic_meta_re = re.compile(r"^\*[^*].*?\*\s*$")
    heading_re = re.compile(r"^#{1,6}\s")
    bullet_re = re.compile(r"^\s*[-*]\s")

    def is_meta(s):
        if bullet_re.match(s) or heading_re.match(s):
            return True
        if bold_meta_re.match(s):
            return True
        # trailing italic credit line (contains "words" or "by tapio"/"by adrian")
        if italic_meta_re.match(s) and ("words" in s.lower()
                                        or "by tapio" in s.lower()
                                        or "by adrian" in s.lower()):
            return True
        return False

    # find the narrative start: default right after the title block, but if a
    # "## Synopsis"/"## Premise" restart heading exists, begin there.
    start = 0
    for i, ln in enumerate(rest):
        s = ln.strip()
        if heading_re.match(s) and re.search(r"synopsis|premise", s, re.I):
            start = i + 1
            break
    blurb_lines = []
    started = False
    for ln in rest[start:]:
        s = ln.strip()
        if is_meta(s):
            break
        if author_re.match(s) or by_re.match(s):
            continue
        if not s:
            if started:
                blurb_lines.append(ln)
            continue
        started = True
        blurb_lines.append(ln)
    blurb = "\n".join(blurb_lines).strip()
    body = "\n".join(body_lines).strip()
    if author and author.lower().startswith("by "):
        author_name = author[3:].strip()
    else:
        author_name = author or "Tapio Kinnunen"
    return {"title": title or path.parent.parent.name,
            "author": author_name, "body": body, "blurb": blurb}


# --- page builders ----------------------------------------------------------
def base_html(*, title, desc, body, extra_head="", nav="all"):
    t = html.escape(title)
    d = html.escape(desc)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nav_items = [
        ("All", page_url("index.html"), "all"),
        ("Novels", page_url("novels.html"), "novels"),
        ("Comics", page_url("comics.html"), "comics"),
    ]
    nav_html = '<nav class="site-nav" aria-label="Categories">'
    for label, href, key in nav_items:
        cls = "site-nav-link" + (" active" if key == nav else "")
        nav_html += f'<a class="{cls}" href="{href}">{label}</a>'
    nav_html += "</nav>"
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
    return f"""<article class="card">
  <a class="card-cover-link" href="{book_url}">
    <img class="card-cover" src="{cover_url}" alt="Cover of {html.escape(syn['title'])}" loading="lazy">
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


def build_section(title, subtitle, books_list, nav):
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
    return base_html(title=title, desc=subtitle, body=body, nav=nav)


def build_home(books):
    if not books:
        return base_html(title="Books", desc=TAGLINE,
                         body='<section class="hero"><h1>Books by Tapio Kinnunen</h1>'
                              '<p class="lede">Reasoned science fiction, set down by '
                              'the Hermes writer agent.</p></section>\n'
                              '<p class="empty">No books published yet.</p>')

    # Single unified grid: all books (comics + novels) sorted newest first
    grid = "\n".join(card(b) for b in books)
    body = f"""<section class="hero">
  <h1>Books by Tapio Kinnunen</h1>
  <p class="lede">Reasoned science fiction, set down by the Hermes writer agent. Read online or download the PDF.</p>
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
    actions.append(f'<a class="btn btn-ghost" href="{BASE}/">All books</a>')
    body = f"""<article class="book">
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
    return base_html(title=syn["title"], desc=(syn["blurb"] or TAGLINE), body=body)


def build_gallery(b):
    syn = b["syn_parsed"]
    bar = f"""<header class="read-bar">
  <a href="{BASE}/">Library</a>
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
{body}
</body>
</html>"""


def build_read(b, manuscript_html):
    syn = b["syn_parsed"]
    book_url = page_url("books", b["slug"], "index.html")
    pdf_url = (page_url("books", b["slug"], b["pdf_name"])
               if b["pdf"] else None)
    pdf_link = f'<a href="{pdf_url}">PDF</a>' if pdf_url else ""
    gallery_link = (f'<a href="{page_url("books", b["slug"], "gallery.html")}">Comic</a>'
                    if b["is_comic"] else "")
    bar = f"""<header class="read-bar">
  <a href="{BASE}/">Library</a>
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
        state[slug] = {"md_hash": b["md_hash"], "wc": b["wc"]}
    save_state(state)

    parsed = []
    for b in books:
        syn = parse_synopsis(b["syn"])
        # Deterministic, slug-based asset names so links always match files.
        pdf_name = f"{b['slug']}.pdf" if b["pdf"] else None
        parsed.append(dict(b, syn_parsed=syn, pdf_name=pdf_name))
    # Sort by most recently modified first (newest book or most recently edited at top)
    parsed.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    (OUT / "index.html").write_text(build_home(parsed), encoding="utf-8")
    comics_list = [b for b in parsed if b["is_comic"]]
    novels_list = [b for b in parsed if not b["is_comic"]]
    (OUT / "comics.html").write_text(
        build_section("Comics", "Graphic novels and illustrated stories.", comics_list, "comics"),
        encoding="utf-8")
    (OUT / "novels.html").write_text(
        build_section("Novels", "Reasoned science fiction, set down by the Hermes writer agent.", novels_list, "novels"),
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