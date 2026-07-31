#!/usr/bin/env python3
"""Hash-bound vision audit gate for every publishable book cover.

The vision model itself is invoked by the Hermes publishing agent via
`vision_analyze`.  That agent writes `cover/vision-audit.json`; this script
refuses publication unless the receipt matches the exact cover bytes and all
required visual checks passed.  Re-typesetting or regenerating a cover makes
its old receipt stale automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 1
RECEIPT_NAME = "vision-audit.json"
REQUIRED_CHECKS = (
    "important_subjects_unobscured",
    "title_readable",
    "byline_readable",
    "safe_margins",
    "no_rendering_artifacts",
    "professional_composition",
)
ALLOWED_TOOLS = {"vision_analyze", "functions.vision_analyze"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_cover(slug: str, cover: Path) -> list[str]:
    errors: list[str] = []
    receipt_path = cover.parent / RECEIPT_NAME
    if not receipt_path.exists():
        return [f"{slug}: missing {receipt_path}"]
    try:
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{slug}: unreadable vision receipt: {exc}"]
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{slug}: unsupported vision receipt schema")
    if data.get("slug") != slug:
        errors.append(f"{slug}: receipt slug mismatch")
    actual_hash = sha256(cover)
    if data.get("cover_sha256") != actual_hash:
        errors.append(f"{slug}: stale vision receipt (cover hash changed)")
    tool_name = data.get("tool") or data.get("inspected_with")
    if tool_name not in ALLOWED_TOOLS:
        errors.append(f"{slug}: receipt does not identify the vision_analyze tool")
    if data.get("verdict") != "PASS":
        errors.append(f"{slug}: vision verdict is {data.get('verdict', 'missing')}, not PASS")
    checks = data.get("checks")
    if not isinstance(checks, dict):
        errors.append(f"{slug}: missing visual checks mapping")
    else:
        for name in REQUIRED_CHECKS:
            if checks.get(name) is not True:
                errors.append(f"{slug}: visual check failed or missing: {name}")
    if not isinstance(data.get("inspected_at"), str) or not data["inspected_at"].strip():
        errors.append(f"{slug}: missing inspected_at")
    if not isinstance(data.get("notes"), str):
        errors.append(f"{slug}: notes must be a string")
    return errors


def verify_entries(entries: Iterable[tuple[str, Path]]) -> list[str]:
    errors: list[str] = []
    for slug, cover in entries:
        errors.extend(validate_cover(slug, cover))
    return errors


def discover_entries(books_root: Path) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    for book in sorted(books_root.iterdir() if books_root.exists() else []):
        if not book.is_dir() or book.name.startswith(("_", ".")):
            continue
        cover = book / "cover" / f"{book.name}-cover.png"
        synopsis = book / "cover" / "synopsis.md"
        manuscripts = list((book / "manuscript").glob("*.md")) if (book / "manuscript").exists() else []
        if cover.exists() and synopsis.exists() and manuscripts:
            entries.append((book.name, cover))
    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", type=Path, default=Path.home() / "Books")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    entries = discover_entries(args.books)
    errors = verify_entries(entries)
    if args.json:
        print(json.dumps({
            "result": "PASS" if not errors else "FAIL",
            "covers_checked": len(entries),
            "errors": errors,
        }, indent=2))
    else:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"RESULT: {'PASS' if not errors else 'FAIL'} ({len(entries)} cover(s) checked)")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
