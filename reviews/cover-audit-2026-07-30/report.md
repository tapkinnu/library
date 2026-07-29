# Cover audit — 2026-07-30

## Scope

Reviewed every one of the 24 covers currently published by *The Library of Tapio Kinnunen* at source resolution, in contact sheets, and in the rendered 9:16 website card layout.

## Defects found

- Eighteen novel covers used narrow, single-line outlined titles over busy artwork. Long titles were technically present but visually compressed, unevenly legible at thumbnail size, and inconsistent with professional trade-cover hierarchy.
- *The Custody of Silence* contained visible AI-generated pseudo-lettering at the lower trim edge.
- *The Glass Monument* had a low-contrast tagline and a redundant, faint `BY` label.
- *The Axiom of Void* had no clean raw-art master from which to rebuild typography.
- *Cinder Nine: The Last Gun* and *The Quiet Beacon* used legacy 2:3 cover files rather than the site's 9:16 house standard.

## Corrections

- Re-typeset 18 novel covers from text-free source art using a new deterministic cover engine.
- Replaced narrow one-line title treatments with balanced one- or two-line title blocks, solid high-contrast lettering, controlled negative-space fields, and consistent author placement.
- Added an opaque lower trim-safe field so accidental AI pseudo-lettering cannot remain visible.
- Removed the malformed lower-edge text from *The Custody of Silence*.
- Rebuilt *The Glass Monument* without the weak tagline or redundant `BY` label.
- Generated a new text-free geometric raw-art master for *The Axiom of Void*, then typeset the title and byline programmatically.
- Converted the two legacy comic covers to 576×1024 without distortion, restoring a clean trim border after center-cropping.
- Archived every superseded canonical cover under each book's `archive/covers-2026-07-30/` directory.
- Installed reproducible `cover/make_cover.py` wrappers for all corrected projects.

## Final checks

- 24/24 published covers are portrait and render in the website's 9:16 cards without title/byline clipping.
- 24/24 pass `verify_covers.py` OCR/byline validation.
- 24/24 pass `verify_site.py` completeness validation.
- The corrected covers were inspected in four six-cover contact sheets and in a locally rendered browser build.
- No visible AI pseudo-lettering remains in the corrected lower trim bands.
