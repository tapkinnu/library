#!/usr/bin/env python3
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import generate
import verify_covers
import verify_site


class AdultPublicationExclusionTests(unittest.TestCase):
    def test_status_flag_parser_is_shared(self):
        samples = (
            "adult_content: true\n",
            "ADULT_CONTENT: YES\n",
            "adult_content: 1\n",
            "adult_content: on\n",
        )
        for text in samples:
            self.assertTrue(generate._adult_content_from_status(text))
            self.assertTrue(verify_site._adult_content_from_status(text))
            self.assertTrue(verify_covers._adult_content_from_status(text))
        for text in ("adult_content: false\n", "# adult_content: true\n"):
            self.assertFalse(generate._adult_content_from_status(text))
            self.assertFalse(verify_site._adult_content_from_status(text))
            self.assertFalse(verify_covers._adult_content_from_status(text))

    def test_explicitly_incomplete_projects_are_not_publishable(self):
        self.assertTrue(generate._status_explicitly_incomplete("phase: repair\n"))
        self.assertTrue(generate._status_explicitly_incomplete("status: IN_PROGRESS\n"))
        self.assertTrue(generate._status_explicitly_incomplete("phase: withdrawn\n"))
        self.assertFalse(generate._status_explicitly_incomplete("phase: complete\nstatus: COMPLETE\n"))
        self.assertTrue(verify_site._status_explicitly_incomplete("phase: repair\n"))
        self.assertFalse(verify_site._status_explicitly_incomplete("phase: complete\n"))

    def test_public_navigation_has_no_after_dark_section(self):
        page = generate.base_html(
            title="Books",
            desc="Library",
            body="<p>Books</p>",
            nav="all",
        )
        self.assertNotIn("After Dark", page)
        self.assertNotIn("adult-comics.html", page)
        self.assertNotIn("18+", page)

    def test_discovery_excludes_adult_projects_without_deleting_sources(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "sample-adult-comic"
            project.mkdir()
            status = project / "status.yaml"
            status.write_text(
                "phase: complete\nstatus: COMPLETE\nadult_content: true\n",
                encoding="utf-8",
            )
            with mock.patch.object(generate, "BOOKS_ROOT", root):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    books = generate.discover_books()
            self.assertEqual(books, [])
            self.assertIn("[skip-adult] sample-adult-comic", output.getvalue())
            self.assertTrue(status.exists())

    def test_public_comics_section_remains_ungated(self):
        page = generate.build_section("Comics", "Graphic novels.", [], "comics")
        self.assertNotIn("After Dark", page)
        self.assertNotIn("adult-comics.html", page)
        self.assertNotIn('class="age-gate"', page)


if __name__ == "__main__":
    unittest.main()
