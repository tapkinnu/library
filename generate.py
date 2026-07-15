#!/usr/bin/env python3
"""Generate the static Adrian Vey book-library site (GitHub Pages ready).

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

Requires:  pip install markdown   (already present in the writer agent venv)
"""
from __future__ import annotations

import html
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("ERROR: the 'markdown' package is required. Install with: pip install markdown")

# --- configuration ---------------------------------------------------------
# GitHub repo name. The Pages site is served at https://<user>.github.io/<REPO>/
# so every asset/link is rooted at /<REPO>/. If you rename the repo, change REPO.
REPO = "library"
BASE = f"/{REPO}"

ROOT = Path(__file__).resolve().parent
BOOKS_ROOT = Path(os.environ.get("BOOKS_DIR", Path.home() / "Books")).expanduser()
OUT = ROOT / "docs"
SRC = ROOT / "src"

SITE_TITLE = "The Library of Adrian Vey"
TAGLINE = "Novels from the Hermes writer agent — reasoned science fiction."

MD_EXT = ["extra"]

# --- helpers ----------------------------------------------------------------
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
                   if not p.name.startswith("~")])
        mdfile = mds[0] if mds else None
        pdfs = (list(d.glob(f"manuscript/{slug}.pdf"))
                or list(d.glob("manuscript/*.pdf")))
        pdf = pdfs[0] if pdfs else None
        if not (cover and syn and mdfile):
            print(f"[skip] {slug}: cover={bool(cover)} synopsis={bool(syn)} "
                  f"manuscript={bool(mdfile)}")
            continue
        books.append({"slug": slug, "cover": cover, "syn": syn,
                      "md": mdfile, "pdf": pdf})
    return books


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
    author_re = re.compile(r"^\*\*(.+?)\*\*\s*$")
    by_re = re.compile(r"^(?:\*\*)?By\s+(.+?)(?:\*\*)?\s*$", re.I)
    author = None
    for ln in lines:
        m = author_re.match(ln.strip())
        if m:
            author = m.group(1).strip()
            break
        m = by_re.match(ln.strip())
        if m:
            author = "By " + m.group(1).strip()
            break
    rest = lines[title_idx + 1:] if title_idx is not None else lines
    body_lines = [ln for ln in rest
                  if not author_re.match(ln.strip())
                  and not by_re.match(ln.strip())]
    # short blurb: narrative paragraphs before the first list/meta line
    blurb_lines = []
    started = False
    for ln in rest:
        s = ln.strip()
        if s.startswith("- ") or s.startswith("#"):
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
        author_name = author or "Adrian Vey"
    return {"title": title or path.parent.parent.name,
            "author": author_name, "body": body, "blurb": blurb}


# --- page builders ----------------------------------------------------------
def base_html(*, title, desc, body, extra_head=""):
    t = html.escape(title)
    d = html.escape(desc)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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


def build_home(books):
    if not books:
        grid = '<p class="empty">No books published yet.</p>'
    else:
        cards = []
        for b in books:
            syn = b["syn_parsed"]
            cover_url = page_url("books", b["slug"], f"{b['slug']}-cover.png")
            book_url = page_url("books", b["slug"], "index.html")
            pdf_url = (page_url("books", b["slug"], b["pdf_name"])
                       if b["pdf"] else None)
            blurb_html = md_to_html(syn["blurb"]) if syn["blurb"] else ""
            pdf_btn = (f'<a class="btn btn-sm" href="{pdf_url}">PDF</a>'
                       if pdf_url else "")
            cards.append(f"""
<article class="card">
  <a class="card-cover-link" href="{book_url}">
    <img class="card-cover" src="{cover_url}" alt="Cover of {html.escape(syn['title'])}" loading="lazy">
  </a>
  <div class="card-body">
    <p class="card-author">{html.escape(syn['author'])}</p>
    <h2 class="card-title"><a href="{book_url}">{html.escape(syn['title'])}</a></h2>
    <div class="card-blurb">{blurb_html}</div>
    <div class="card-actions">
      <a class="btn btn-primary btn-sm" href="{book_url}">View &amp; read</a>
      {pdf_btn}
    </div>
  </div>
</article>""")
        grid = "\n".join(cards)
    body = f"""
<section class="hero">
  <h1>Books by Adrian Vey</h1>
  <p class="lede">Reasoned science fiction, set down by the Hermes writer agent. Read online or download the PDF.</p>
</section>
<section class="grid">
{grid}
</section>
"""
    return base_html(title="Books", desc=TAGLINE, body=body)


def build_book(b):
    syn = b["syn_parsed"]
    cover_url = page_url("books", b["slug"], f"{b['slug']}-cover.png")
    read_url = page_url("books", b["slug"], "read.html")
    pdf_url = (page_url("books", b["slug"], b["pdf_name"])
               if b["pdf"] else None)
    syn_html = md_to_html(syn["body"])
    actions = [f'<a class="btn btn-primary" href="{read_url}">Read online</a>']
    if pdf_url:
        actions.append(f'<a class="btn" href="{pdf_url}">Download PDF</a>')
    actions.append(f'<a class="btn btn-ghost" href="{BASE}/">← All books</a>')
    body = f"""
<article class="book">
  <div class="book-hero">
    <img class="book-cover" src="{cover_url}" alt="Cover of {html.escape(syn['title'])}">
    <div class="book-meta">
      <p class="eyebrow">{html.escape(syn['author'])}</p>
      <h1 class="book-title">{html.escape(syn['title'])}</h1>
      <div class="book-syn">{syn_html}</div>
      <div class="actions">{''.join(actions)}</div>
    </div>
  </div>
</article>
"""
    return base_html(title=syn["title"], desc=(syn["blurb"] or TAGLINE), body=body)


def build_read(b, manuscript_html):
    syn = b["syn_parsed"]
    book_url = page_url("books", b["slug"], "index.html")
    pdf_url = (page_url("books", b["slug"], b["pdf_name"])
               if b["pdf"] else None)
    pdf_link = f'<a href="{pdf_url}">PDF</a>' if pdf_url else ""
    bar = f"""
<header class="read-bar">
  <a href="{BASE}/">Library</a>
  <span class="read-title">{html.escape(syn['title'])}</span>
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
    parsed = []
    for b in books:
        syn = parse_synopsis(b["syn"])
        # Deterministic, slug-based asset names so links always match files.
        pdf_name = f"{b['slug']}.pdf" if b["pdf"] else None
        parsed.append(dict(b, syn_parsed=syn, pdf_name=pdf_name))
    parsed.sort(key=lambda x: x["syn_parsed"]["title"].lower())
    (OUT / "index.html").write_text(build_home(parsed), encoding="utf-8")
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
        print(f"[ok] {b['slug']}: {b['syn_parsed']['title']}")
    print(f"Built {len(parsed)} book(s) into {OUT}")


if __name__ == "__main__":
    main()
