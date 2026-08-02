#!/usr/bin/env python3
"""Tests for deterministic trilingual figure overlays."""

from __future__ import annotations

import unittest

from apply_trilingual_figure_manifest import apply_manifest


class TrilingualFigureOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = {
            "source": {},
            "chapters": [
                {
                    "paragraphs": [
                        {"id": "p1", "units": []},
                        {"id": "p2", "units": []},
                    ]
                }
            ],
        }
        self.manifest = {
            "figure_count": 2,
            "figures": [
                {
                    "source_order": 2,
                    "source_page_index": 20,
                    "paragraph_id": "p2",
                    "path": "second.jpg",
                    "caption": "Second",
                },
                {
                    "source_order": 1,
                    "source_page_index": 10,
                    "paragraph_id": "p1",
                    "path": "first.jpg",
                    "caption": "First",
                },
            ],
        }

    def test_applies_figures_to_source_paragraphs(self) -> None:
        result = apply_manifest(self.data, self.manifest, require_assets=False)
        paragraphs = result["chapters"][0]["paragraphs"]
        self.assertEqual(paragraphs[0]["figures"][0]["caption"], "First")
        self.assertEqual(paragraphs[1]["figures"][0]["caption"], "Second")
        self.assertEqual(result["source"]["figure_count"], 2)

    def test_reapplication_is_idempotent(self) -> None:
        apply_manifest(self.data, self.manifest, require_assets=False)
        apply_manifest(self.data, self.manifest, require_assets=False)
        figures = [
            figure
            for paragraph in self.data["chapters"][0]["paragraphs"]
            for figure in paragraph.get("figures", [])
        ]
        self.assertEqual(len(figures), 2)

    def test_unknown_paragraph_is_rejected(self) -> None:
        self.manifest["figures"][0]["paragraph_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown paragraph"):
            apply_manifest(self.data, self.manifest, require_assets=False)

    def test_manifest_count_mismatch_is_rejected(self) -> None:
        self.manifest["figure_count"] = 99
        with self.assertRaisesRegex(ValueError, "count"):
            apply_manifest(self.data, self.manifest, require_assets=False)


if __name__ == "__main__":
    unittest.main()
