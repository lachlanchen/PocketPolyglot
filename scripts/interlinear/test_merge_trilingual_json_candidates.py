#!/usr/bin/env python3
"""Focused tests for deterministic trilingual candidate merging."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from merge_trilingual_json_candidates import canonicalize_chapter_title, is_valid_existing


class CanonicalChapterTitleTest(unittest.TestCase):
    @staticmethod
    def chunk(chapter_id: str, en_title: str) -> dict:
        return {
            "chapter": {
                "id": chapter_id,
                "title": {
                    "en": [{"t": en_title}],
                    "zh": [{"t": "一 乱世破晓"}],
                    "ja": [{"t": "第一章 乱世の夜明け"}],
                },
            }
        }

    def test_later_chunk_reuses_first_validated_title(self) -> None:
        titles: dict = {}
        first = self.chunk("chapter-001", "Chapter 1: Dawn of an Age of War")
        later = self.chunk("chapter-001", "Chapter 1: Dawn of an Age of Turmoil")

        self.assertFalse(
            canonicalize_chapter_title(first, {"chapter_id": "chapter-001"}, titles)
        )
        self.assertTrue(
            canonicalize_chapter_title(later, {"chapter_id": "chapter-001"}, titles)
        )
        self.assertEqual(later["chapter"]["title"], first["chapter"]["title"])

    def test_different_chapters_keep_independent_titles(self) -> None:
        titles: dict = {}
        first = self.chunk("chapter-001", "Chapter 1")
        second = self.chunk("chapter-002", "Chapter 2")

        canonicalize_chapter_title(first, {"chapter_id": "chapter-001"}, titles)
        self.assertFalse(
            canonicalize_chapter_title(second, {"chapter_id": "chapter-002"}, titles)
        )
        self.assertEqual(second["chapter"]["title"]["en"][0]["t"], "Chapter 2")

    def test_existing_valid_chunk_is_recognized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunk.json"
            path.write_text(json.dumps({"chunk_id": "fixture-c0001"}), encoding="utf-8")
            with patch("merge_trilingual_json_candidates.validate_chunk", return_value=[]):
                self.assertTrue(is_valid_existing(path, {"chunk_id": "fixture-c0001"}))


if __name__ == "__main__":
    unittest.main()
