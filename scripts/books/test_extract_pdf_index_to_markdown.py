#!/usr/bin/env python3
"""Focused tests for semantic PDF-index reconstruction."""

from __future__ import annotations

import unittest

from extract_pdf_index_to_markdown import parse_index_entries, render_markdown


class PdfIndexExtractionTest(unittest.TestCase):
    def test_numeric_only_wrapped_reference_is_preserved(self) -> None:
        sections, entries = parse_index_entries(
            [
                "B",
                "Barich; 2; 3; 201; 208;",
                "218",
                "Bubaline; 30; 31",
            ]
        )
        self.assertEqual(sections, ["B"])
        self.assertEqual(entries[0], ("B", "Barich; 2; 3; 201; 208; 218"))

    def test_markdown_groups_entries_under_source_section(self) -> None:
        rendered = render_markdown(
            "INDEX",
            ["A", "B"],
            [("A", "Acheulean; 2"), ("B", "Barich; 2; 3")],
        )
        self.assertIn("### A", rendered)
        self.assertIn("- **Acheulean**; 2", rendered)
        self.assertLess(rendered.index("### A"), rendered.index("### B"))


if __name__ == "__main__":
    unittest.main()
