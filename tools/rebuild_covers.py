#!/usr/bin/env python3
"""Rebuild the library's canonical novel covers from text-free art."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "pro_cover.py"
MANIFEST = HERE / "cover_manifest.json"
BOOKS = Path.home() / "Books"


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def archive_existing(slug: str, outputs: list[str]) -> None:
    cover = BOOKS / slug / "cover"
    archive = BOOKS / slug / "archive" / "covers-2026-07-30"
    archive.mkdir(parents=True, exist_ok=True)
    for name in outputs:
        src = cover / name
        dst = archive / name
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            print(f"ARCHIVED {src} -> {dst}")


def rebuild(slug: str, cfg: dict, archive: bool) -> None:
    cover = BOOKS / slug / "cover"
    art = cover / cfg["art"]
    outputs = cfg["outputs"]
    if archive:
        archive_existing(slug, outputs)
    primary = cover / outputs[0]
    cmd = [
        sys.executable, str(ENGINE),
        "--art", str(art),
        "--out", str(primary),
        "--title", cfg["title"],
        "--title-font", cfg.get("title_font", "dejavu-serif"),
        "--title-y", str(cfg.get("title_y", 0.16)),
        "--kicker", cfg.get("kicker", "A SCIENCE FICTION NOVEL"),
        "--byline", "TAPIO KINNUNEN",
        "--byline-font", "dejavu-sans",
        "--byline-weight", "bold",
    ]
    subprocess.run(cmd, check=True)
    for alias in outputs[1:]:
        shutil.copy2(primary, cover / alias)
        print(f"MIRRORED {primary.name} -> {alias}")


def install_wrapper(slug: str) -> None:
    cover = BOOKS / slug / "cover"
    path = cover / "make_cover.py"
    code = f'''#!/usr/bin/env python3
"""Rebuild the professional cover for {slug}; configuration is site-versioned."""
import subprocess
import sys
subprocess.run([
    sys.executable,
    "/home/ganomix/book-library-site/tools/rebuild_covers.py",
    "{slug}",
], check=True)
'''
    path.write_text(code, encoding="utf-8")
    path.chmod(0o755)
    print(f"WRAPPER {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="*", help="default: every cover in the manifest")
    ap.add_argument("--archive", action="store_true", help="archive current canonical PNGs once")
    ap.add_argument("--install-wrappers", action="store_true")
    args = ap.parse_args()
    manifest = load_manifest()
    slugs = args.slugs or list(manifest)
    unknown = [slug for slug in slugs if slug not in manifest]
    if unknown:
        raise SystemExit(f"Unknown slug(s): {', '.join(unknown)}")
    for slug in slugs:
        rebuild(slug, manifest[slug], args.archive)
        if args.install_wrappers:
            install_wrapper(slug)
    print(f"REBUILT {len(slugs)} cover(s)")


if __name__ == "__main__":
    main()
