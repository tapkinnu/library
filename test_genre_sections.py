#!/usr/bin/env python3
import unittest

import generate
import verify_site


class GenreSectionTests(unittest.TestCase):
    def test_genre_parser_recognizes_fantasy_and_science_fiction(self):
        fantasy_status = "category: adult dark folkloric fantasy\nstatus: COMPLETE\n"
        science_fiction_statuses = [
            "genre: science fiction\n",
            "category: original adult science-fiction novel\n",
            "genre: Hard SF / Institutional Thriller\n",
            "genre: sci-fi adventure\n",
        ]
        self.assertEqual(generate._genre_from_status(fantasy_status), "fantasy")
        self.assertEqual(verify_site._genre_from_status(fantasy_status), "fantasy")
        for status in science_fiction_statuses:
            with self.subTest(status=status):
                self.assertEqual(generate._genre_from_status(status), "science-fiction")
                self.assertEqual(verify_site._genre_from_status(status), "science-fiction")

    def test_legacy_unlabelled_books_default_to_science_fiction(self):
        status = "phase: complete\n"
        self.assertEqual(generate._genre_from_status(status), "science-fiction")
        self.assertEqual(verify_site._genre_from_status(status), "science-fiction")

    def test_only_top_level_genre_and_category_fields_drive_classification(self):
        status = "phase: complete\nlast_fantasy_subgenre: weird fantasy\n"
        self.assertEqual(generate._genre_from_status(status), "science-fiction")

    def test_navigation_exposes_both_genre_pages(self):
        page = generate.build_section("Fantasy", "Magic and myth.", [], "fantasy")
        self.assertIn('href="/library/fantasy.html"', page)
        self.assertIn('href="/library/science-fiction.html"', page)
        self.assertIn('class="site-nav-link active" href="/library/fantasy.html"', page)

    def test_prose_book_backlink_uses_genre_category(self):
        fantasy = {"genre": "fantasy", "is_comic": False, "is_adult": False, "is_novella": False}
        science_fiction = {
            "genre": "science-fiction", "is_comic": False,
            "is_adult": False, "is_novella": True,
        }
        self.assertEqual(
            generate.category_for_book(fantasy),
            ("/library/fantasy.html", "Fantasy", "fantasy"),
        )
        self.assertEqual(
            generate.category_for_book(science_fiction),
            ("/library/science-fiction.html", "Science Fiction", "science-fiction"),
        )


if __name__ == "__main__":
    unittest.main()
