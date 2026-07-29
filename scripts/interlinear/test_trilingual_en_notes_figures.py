#!/usr/bin/env python3
"""Regression tests for opt-in figures in English-main trilingual TeX."""

from __future__ import annotations

import unittest

from json_to_trilingual_en_notes_tex import convert


class TrilingualEnNotesFigureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = {
            "title": {
                "en": [{"t": "Example"}],
                "ja": [{"t": "例"}],
                "zh": [{"t": "示例"}],
            },
            "chapters": [
                {
                    "number": 1,
                    "title": {
                        "en": [{"t": "Chapter"}],
                        "ja": [{"t": "章"}],
                        "zh": [{"t": "章"}],
                    },
                    "paragraphs": [
                        {
                            "units": [
                                {
                                    "en": [{"t": "Text"}],
                                    "ja": [{"t": "本文"}],
                                    "zh": [{"t": "正文"}],
                                }
                            ],
                            "figures": [
                                {
                                    "path": "assets/example image.jpg",
                                    "caption": "Source figure",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    def render(self, *, include_figures: bool) -> str:
        return convert(
            self.data,
            color_mode="color",
            author="",
            author_reading="",
            curated_by="",
            curated_url="",
            powered_by="",
            cover_image="",
            include_figures=include_figures,
        )

    def test_figures_are_opt_in(self) -> None:
        self.assertNotIn(r"\TriAllFigure", self.render(include_figures=False))

    def test_figures_keep_source_path_and_caption(self) -> None:
        rendered = self.render(include_figures=True)
        self.assertIn(
            r"\TriAllFigure{assets/example image.jpg}{Source figure}",
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
