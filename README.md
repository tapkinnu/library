# The Library of Adrian Vey

A static book-library site for novels produced by the Hermes **writer** agent,
published via GitHub Pages.

## How it works

- `generate.py` scans `~/Books/*/` for finished books and emits a fully static
  site into `docs/` (served by GitHub Pages from the `main` branch, `/docs`).
- A finished book needs, inside `~/Books/<dir>/`:
  - `cover/<something>-cover.png` — portrait cover
  - `cover/synopsis.md` — `# Title — Synopsis`, a `**By Author**` line, then a
    blurb and optional metadata bullets
  - `manuscript/<something>.md` — full manuscript (rendered for "Read online")
  - `manuscript/<something>.pdf` — optional; exposed as "Download PDF"
- No manual edits: adding a future book = drop it under `~/Books` and rerun.

## Regenerate

```bash
# from this repo root
python3 generate.py                 # uses ~/Books
BOOKS_DIR=/path/to/Books python3 generate.py
```

Requires `markdown` (`pip install markdown`). Then commit & push:

```bash
git add -A && git commit -m "rebuild site" && git push
```

## Branding

Deep navy `#1B2A4A`, cream `#F6EFE0`, terracotta accent `#C46A4E`. Calm
"rationalist library" feel, mobile-friendly.

## Note on repo/base path

The site is rooted at `/library/` (the repo name). If you rename the repo,
update `REPO` at the top of `generate.py` so asset and link paths stay correct.
