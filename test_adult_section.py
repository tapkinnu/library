#!/usr/bin/env python3
import unittest
from pathlib import Path

import generate
import verify_site


class AdultSectionTests(unittest.TestCase):
    def test_status_flag_parser(self):
        self.assertTrue(generate._adult_content_from_status("adult_content: true\n"))
        self.assertTrue(generate._adult_content_from_status("ADULT_CONTENT: YES\n"))
        self.assertFalse(generate._adult_content_from_status("adult_content: false\n"))
        self.assertFalse(generate._adult_content_from_status("# adult_content: true\n"))

    def test_explicitly_incomplete_projects_are_not_publishable(self):
        self.assertTrue(generate._status_explicitly_incomplete("phase: repair\n"))
        self.assertTrue(generate._status_explicitly_incomplete("status: IN_PROGRESS\n"))
        self.assertTrue(generate._status_explicitly_incomplete("phase: drafting\n"))
        self.assertTrue(generate._status_explicitly_incomplete("phase: withdrawn\n"))
        self.assertFalse(generate._status_explicitly_incomplete("phase: complete\nstatus: COMPLETE\n"))
        self.assertFalse(generate._status_explicitly_incomplete("  status: drafting\n"))
        self.assertTrue(verify_site._status_explicitly_incomplete("phase: repair\n"))
        self.assertTrue(verify_site._status_explicitly_incomplete("status: WITHDRAWN\n"))
        self.assertFalse(verify_site._status_explicitly_incomplete("phase: complete\n"))

    def test_nav_and_gate_on_adult_section(self):
        page = generate.build_section(
            "After Dark",
            "Adults-only illustrated stories.",
            [],
            "adult",
            adult=True,
        )
        self.assertIn("After Dark · 18+", page)
        self.assertIn('class="age-gate"', page)
        self.assertIn("I am 18 or older", page)
        self.assertIn("adult-comics.html", page)

    def test_adult_book_and_readers_are_gated(self):
        book = {
            "slug": "sample-adult-comic",
            "syn_parsed": {
                "title": "Sample",
                "author": "T. K. Arven",
                "body": "Adult blurb.",
                "blurb": "Adult blurb.",
            },
            "pdf": None,
            "pdf_name": None,
            "is_comic": True,
            "is_adult": True,
            "pages": [Path("page-1.png")],
        }
        book_page = generate.build_book(book)
        gallery_page = generate.build_gallery(book)
        read_page = generate.build_read(book, "<p>Script</p>")
        self.assertIn('class="age-gate"', book_page)
        self.assertIn('class="age-gate"', gallery_page)
        self.assertIn('class="age-gate"', read_page)
        adult_backlink = 'href="/library/adult-comics.html">After Dark</a>'
        self.assertIn(adult_backlink, book_page)
        self.assertIn(adult_backlink, gallery_page)
        self.assertIn(adult_backlink, read_page)

    def test_safe_sections_do_not_render_adult_gate(self):
        page = generate.build_section("Comics", "Safe comics.", [], "comics")
        self.assertNotIn('class="age-gate"', page)


if __name__ == "__main__":
    unittest.main()
