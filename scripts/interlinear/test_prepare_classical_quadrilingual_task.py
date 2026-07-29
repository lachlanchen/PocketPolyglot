#!/usr/bin/env python3
"""Focused tests for section-aware classical source preparation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prepare_classical_quadrilingual_task import (
    extract_sectioned_html,
    sectioned_source_order,
)


class SectionedClassicalPreparationTest(unittest.TestCase):
    def write_html(self, body: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "source.html"
        path.write_text(
            f"<html><head><title>Fixture</title></head>"
            f"<body><div class='mw-parser-output'>{body}</div></body></html>",
            encoding="utf-8",
        )
        return path

    def test_nested_work_titles_and_verse_lines_are_preserved(self) -> None:
        path = self.write_html(
            "<p>Navigation text before the first work.</p>"
            "<h2>卷一</h2>"
            "<h3>○滄海賦</h3>"
            "<p>水何澹澹<br>山島竦峙</p>"
            "<h3>燕歌行</h3>"
            "<h4>其一</h4>"
            "<p>秋風蕭瑟天氣涼<br>草木搖落露為霜</p>"
        )
        _, sections = extract_sectioned_html(path, drop_small=False)
        self.assertEqual(
            [section["chapter_title"] for section in sections],
            ["卷一 · 滄海賦", "卷一 · 燕歌行 · 其一"],
        )
        self.assertEqual(sections[0]["paragraphs"], ["水何澹澹\n山島竦峙"])
        self.assertNotIn(
            "Navigation text before the first work.",
            [paragraph for section in sections for paragraph in section["paragraphs"]],
        )

    def test_parent_volume_prefix_accepts_chinese_numerals(self) -> None:
        path = self.write_html(
            "<h2>東征賦（並序）</h2>"
            "<p>建安十九年，王師東征。</p>"
        )
        _, sections = extract_sectioned_html(
            path,
            parent_label="卷十",
            drop_small=False,
        )
        self.assertEqual(sections[0]["chapter_title"], "卷十 · 東征賦（並序）")

    def test_sectioned_pages_sort_by_volume_not_download_filename(self) -> None:
        pages = [
            ("曹子建集/卷十", "0002-volume-ten.html"),
            ("曹子建集/卷二", "0008-volume-two.html"),
            ("曹子建集/卷一", "0011-volume-one.html"),
        ]
        ordered = sorted(
            pages,
            key=lambda item: sectioned_source_order(item[0], item[1]),
        )
        self.assertEqual(
            [title for title, _ in ordered],
            ["曹子建集/卷一", "曹子建集/卷二", "曹子建集/卷十"],
        )

    def test_inline_markup_does_not_duplicate_text(self) -> None:
        path = self.write_html(
            "<h2>觀滄海</h2>"
            "<p>前句<ruby>滄海<rt>そうかい</rt></ruby><br>後句</p>"
        )
        _, sections = extract_sectioned_html(path, drop_small=False)
        self.assertEqual(sections[0]["paragraphs"], ["前句滄海\n後句"])


if __name__ == "__main__":
    unittest.main()
