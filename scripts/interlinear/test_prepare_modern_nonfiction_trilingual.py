#!/usr/bin/env python3
"""Focused tests for illustrated nonfiction source preparation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prepare_modern_nonfiction_trilingual import (
    clean_markdown_line,
    find_start,
    join_proven_page_continuations,
    parse_chapters,
    split_markdown_line_figures,
)


class IllustratedNonfictionPreparationTest(unittest.TestCase):
    def test_clean_heading_keeps_level_and_removes_extraction_markup(self) -> None:
        source = '### <span id="page-7-0"></span>**[Introduction](#page-4-0)**'
        self.assertEqual(clean_markdown_line(source), "### Introduction")

    def test_exact_start_marker_skips_toc_row(self) -> None:
        lines = [
            "| Chapter One | CENTRAL SAHARA: CLIMATE AND ARCHAEOLOGY | 1 |",
            "### Acknowledgments",
            "## CENTRAL SAHARA: CLIMATE AND ARCHAEOLOGY",
        ]
        task = {
            "start_marker": "CENTRAL SAHARA: CLIMATE AND ARCHAEOLOGY",
            "start_marker_exact": True,
        }
        self.assertEqual(find_start(lines, task), 2)

    def test_multiple_images_on_one_line_remain_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            markdown = Path(temporary) / "source-reviewed.md"
            markdown.write_text("", encoding="utf-8")
            parts = split_markdown_line_figures(
                "Before ![First](one.png) ![Second](two.png) After",
                markdown,
            )
            self.assertEqual(len(parts), 4)
            self.assertEqual(parts[0], "Before")
            self.assertEqual(parts[1]["caption"], "First")
            self.assertEqual(parts[2]["caption"], "Second")
            self.assertEqual(parts[3], "After")

    def test_literal_footnote_mark_survives_markdown_cleanup(self) -> None:
        self.assertEqual(
            clean_markdown_line(r"resourceful kind of ape,\* while climate changed"),
            "resourceful kind of ape,* while climate changed",
        )

    def test_page_split_prose_is_joined_only_with_strong_evidence(self) -> None:
        lines = [
            "The landscape directed the development of civilisations",
            "",
            "throughout history. The result was profound.",
            "",
            "A complete paragraph.",
            "",
            "Another complete paragraph.",
            "",
            "## A Heading",
            "",
            "lowercase text beneath a heading.",
        ]
        self.assertEqual(
            join_proven_page_continuations(lines),
            [
                "The landscape directed the development of civilisations throughout history. The result was profound.",
                "",
                "A complete paragraph.",
                "",
                "Another complete paragraph.",
                "",
                "## A Heading",
                "",
                "lowercase text beneath a heading.",
            ],
        )

    def test_front_matter_figures_are_not_attached_to_first_body_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown = root / "source-reviewed.md"
            (root / "front.png").write_bytes(b"front")
            (root / "body.png").write_bytes(b"body")
            markdown.write_text(
                "\n".join(
                    [
                        "![](front.png)",
                        "# Title Page",
                        "## Introduction",
                        "This is the first complete body paragraph.",
                        "![](body.png)",
                        "This is the second complete body paragraph.",
                    ]
                ),
                encoding="utf-8",
            )
            task = {
                "book_id": "fixture",
                "title_en": "Fixture",
                "start_marker": "Introduction",
                "start_marker_exact": True,
                "allow_markdown_headings": True,
            }
            chapters = parse_chapters(markdown, task, max_unit_chars=900)
            figures = [
                figure
                for chapter in chapters
                for paragraph in chapter["paragraphs"]
                for figure in paragraph.get("figures", [])
            ]
            self.assertEqual(len(figures), 1)
            self.assertTrue(figures[0]["path"].endswith("body.png"))


if __name__ == "__main__":
    unittest.main()
