#!/usr/bin/env python3
import hashlib
import json
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cover_vision_gate import REQUIRED_CHECKS, validate_cover


class CoverVisionGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cover_dir = Path(self.tmp.name) / "cover"
        self.cover_dir.mkdir()
        self.cover = self.cover_dir / "demo-cover.png"
        self.cover.write_bytes(b"exact-cover-bytes")

    def tearDown(self):
        self.tmp.cleanup()

    def receipt(self, **updates):
        data = {
            "schema_version": 1,
            "slug": "demo",
            "cover_sha256": hashlib.sha256(self.cover.read_bytes()).hexdigest(),
            "tool": "functions.vision_analyze",
            "verdict": "PASS",
            "inspected_at": "2026-07-31T23:30:00+03:00",
            "checks": {name: True for name in REQUIRED_CHECKS},
            "notes": "All focal subjects and typography inspected.",
        }
        data.update(updates)
        (self.cover_dir / "vision-audit.json").write_text(json.dumps(data))

    def test_missing_receipt_blocks(self):
        self.assertIn("missing", validate_cover("demo", self.cover)[0])

    def test_exact_pass_receipt_accepts(self):
        self.receipt()
        self.assertEqual([], validate_cover("demo", self.cover))

    def test_changed_cover_invalidates_receipt(self):
        self.receipt()
        self.cover.write_bytes(b"changed-cover-bytes")
        self.assertTrue(any("stale" in e for e in validate_cover("demo", self.cover)))

    def test_failed_subject_occlusion_blocks(self):
        checks = {name: True for name in REQUIRED_CHECKS}
        checks["important_subjects_unobscured"] = False
        self.receipt(verdict="FAIL", checks=checks)
        errors = validate_cover("demo", self.cover)
        self.assertTrue(any("verdict" in e for e in errors))
        self.assertTrue(any("important_subjects_unobscured" in e for e in errors))

    def test_non_vision_receipt_blocks(self):
        self.receipt(tool="human")
        self.assertTrue(any("vision_analyze" in e for e in validate_cover("demo", self.cover)))


if __name__ == "__main__":
    unittest.main()
