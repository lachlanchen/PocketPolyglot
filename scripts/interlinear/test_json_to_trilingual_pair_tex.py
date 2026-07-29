#!/usr/bin/env python3
"""Focused tests for localized trilingual pair front matter."""

from __future__ import annotations

import unittest

from json_to_trilingual_pair_tex import convert


class TrilingualPairTexTest(unittest.TestCase):
    def render(self, main_lang: str, comment_lang: str) -> str:
        data = {
            "title": {
                "en": [{"t": "Fixture"}],
                "ja": [{"t": "試験", "r": "しけん"}],
                "zh": [{"t": "测试"}],
            },
            "chapters": [],
        }
        return convert(
            data,
            main_lang=main_lang,
            comment_lang=comment_lang,
            color_mode="color",
            author="Author",
            author_reading="",
            curated_by="Curator",
            curated_url="https://example.com",
            powered_by="Publisher",
            cover_image="",
        )

    def test_contents_heading_follows_main_language(self) -> None:
        self.assertIn(
            r"\renewcommand{\contentsname}{Contents}",
            self.render("en", "ja"),
        )
        self.assertIn(
            r"\renewcommand{\contentsname}{目录}",
            self.render("zh", "en"),
        )
        self.assertIn(
            r"\renewcommand{\contentsname}{目次}",
            self.render("ja", "zh"),
        )


if __name__ == "__main__":
    unittest.main()
