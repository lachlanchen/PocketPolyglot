#!/usr/bin/env python3
"""Focused tests for illustrated nonfiction source preparation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prepare_modern_nonfiction_trilingual import (
    apply_source_exact_replacements,
    canonical_chapter_title,
    clean_line,
    clean_markdown_line,
    drop_repeated_page_headers,
    english_line_has_terminal_boundary,
    expand_dot_leader_index_lines,
    find_start,
    is_heading_line,
    is_recovered_index_entry,
    join_proven_page_continuations,
    parse_chapters,
    repair_embedded_text_artifacts,
    split_english_timeline_entries,
    split_source_units_grouped,
    split_source_units,
    split_markdown_line_figures,
)


class IllustratedNonfictionPreparationTest(unittest.TestCase):
    def test_source_exact_replacements_require_evidence_and_expected_count(self) -> None:
        task = {
            "book_id": "test-book",
            "source_exact_replacements": [
                {
                    "before": "Hidevoshi",
                    "after": "Hideyoshi",
                    "expected_count": 2,
                    "evidence": "Two readings checked against the printed page.",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("prepare_modern_nonfiction_trilingual.ROOT", Path(temp_dir)):
                repaired = apply_source_exact_replacements(
                    "Hidevoshi and Hidevoshi", task
                )
                self.assertEqual(repaired, "Hideyoshi and Hideyoshi")
                report = (
                    Path(temp_dir)
                    / "books/test-book/work/source-extraction/source-correction-report.json"
                )
                self.assertTrue(report.exists())
                with self.assertRaises(RuntimeError):
                    apply_source_exact_replacements("Hidevoshi", task)

    def test_running_page_headers_are_not_joined_into_prose(self) -> None:
        for header in ("x preface", "preface xi", "18 introduction", "476 book xv"):
            with self.subTest(header=header):
                self.assertEqual(clean_line(header, "A Book"), "")
        self.assertEqual(clean_line("BOOK XV", "A Book"), "BOOK XV")

    def test_page_continuation_after_preposition_joins_uppercase_place(self) -> None:
        self.assertEqual(
            join_proven_page_continuations(
                [
                    "The repelled army forced Nobunaga to hasten to",
                    "",
                    "Kyoto and order a fortified residence to be built.",
                ]
            ),
            [
                "The repelled army forced Nobunaga to hasten to Kyoto and order a fortified residence to be built."
            ],
        )

    def test_url_bearing_prose_is_not_discarded_as_boilerplate(self) -> None:
        line = "The two useful sites are http://example.test and another source."

        self.assertEqual(clean_line(line, "A Book"), line)
        self.assertEqual(clean_line("https://example.test", "A Book"), "")

    def test_pdf_wrapped_url_scheme_is_rejoined(self) -> None:
        self.assertEqual(
            repair_embedded_text_artifacts(
                "The source is http:// example.test and map.yahoo.co.jp remains readable."
            ),
            "The source is http://example.test and map.yahoo.co.jp remains readable.",
        )

    def test_dehyphenation_preserves_real_compounds(self) -> None:
        self.assertEqual(
            repair_embedded_text_artifacts(
                "A part-time soldier used a well-known mod-ern method."
            ),
            "A part-time soldier used a well-known modern method.",
        )

    def test_printed_superscript_note_is_normalized_without_touching_years(self) -> None:
        self.assertEqual(
            repair_embedded_text_artifacts(
                'The country was supplied with everything."4 Architect of renewal.'
            ),
            'The country was supplied with everything."[4] Architect of renewal.',
        )
        self.assertEqual(
            repair_embedded_text_artifacts("The year was 1598. Another era began."),
            "The year was 1598. Another era began.",
        )

    def test_repeated_page_headers_are_removed_in_both_directions(self) -> None:
        self.assertEqual(
            drop_repeated_page_headers(
                [
                    "Previous prose continues",
                    "4 chronology & dramatis personae",
                    "on the next page.",
                    "chronology & dramatis personae 5",
                    "6 chronology & dramatis personae",
                    "52 [“initial book”]",
                    "Body text.",
                    "54 [“initial book”]",
                    "what happened before Nobunaga’s march on Kyoto 53",
                    "More body text.",
                    "what happened before Nobunaga’s march on Kyoto 55",
                    "BOOK I",
                ]
            ),
            [
                "Previous prose continues",
                "",
                "on the next page.",
                "",
                "",
                "",
                "Body text.",
                "",
                "",
                "More body text.",
                "",
                "BOOK I",
            ],
        )

    def test_dot_leader_index_entries_are_recovered_across_lines(self) -> None:
        self.assertEqual(
            expand_dot_leader_index_lines(
                [
                    "Map 1. Owari Province.......... 52 Map 2. Ōmi Province.......... 119 Map 10.",
                    "The Western Front.......... 288 Map 11. Settsu Province.......... 304",
                    "BOOK I",
                ]
            ),
            [
                "Map 1. Owari Province — 52",
                "Map 2. Ōmi Province — 119",
                "Map 10. The Western Front — 288",
                "Map 11. Settsu Province — 304",
                "BOOK I",
            ],
        )
        recovered = "Map 1. Owari Province — 52"
        self.assertTrue(is_recovered_index_entry(recovered))
        self.assertEqual(split_source_units(recovered, "en", max_chars=900), [recovered])

    def test_all_caps_chapter_heading_survives_artifact_filter(self) -> None:
        self.assertEqual(clean_line("CHAPTER I", "A Book"), "CHAPTER I")
        self.assertEqual(clean_line("CHAPTER ONE", "A Book"), "CHAPTER ONE")
        self.assertEqual(clean_line("FOREWORD", "A Book"), "FOREWORD")

    def test_spaced_roman_chapter_number_is_normalized(self) -> None:
        self.assertEqual(clean_markdown_line("CHAPTER XV II"), "CHAPTER XVII")
        self.assertEqual(clean_markdown_line("CHAPTER XV III"), "CHAPTER XVIII")

    def test_configured_heading_rules_can_exclude_running_headers(self) -> None:
        task = {
            "source_spine_lang": "en",
            "chapter_heading_patterns": [r"^(?:PREFACE|BOOK [IVXLCDM]+)$"],
            "chapter_heading_mode": "configured_only",
            "chapter_heading_case_sensitive": True,
        }
        self.assertTrue(is_heading_line("BOOK XI", task))
        self.assertFalse(is_heading_line("book xi", task))
        self.assertFalse(is_heading_line("Conclusion", task))
        self.assertEqual(
            clean_line("PREFACE", "A Book", "en", task),
            "PREFACE",
        )

    def test_configured_heading_title_map_is_applied(self) -> None:
        task = {
            "chapter_title_map": {
                "Background to war": "Background to war — Loyalty to the shogun collapses"
            }
        }
        self.assertEqual(
            canonical_chapter_title("Background to war", task),
            "Background to war — Loyalty to the shogun collapses",
        )

    def test_explicit_missing_start_marker_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "start marker not found"):
            find_start(
                ["Front matter", "CHAPTER ONE", "Body"],
                {
                    "start_marker": "INTRODUCTION",
                    "start_marker_exact": True,
                },
            )

    def test_chinese_source_units_split_on_cjk_sentence_boundaries(self) -> None:
        self.assertEqual(
            split_source_units("乱世破晓。群雄并起！家康仍在等待。", "zh", max_chars=12),
            ["乱世破晓。群雄并起！", "家康仍在等待。"],
        )

    def test_scholarly_sub_voce_abbreviation_is_not_a_sentence_boundary(self) -> None:
        text = "Looking up the Vocabvlario s. v. Tôzan corrected the reading. Next sentence."
        self.assertEqual(
            split_source_units(text, "en", max_chars=900),
            ["Looking up the Vocabvlario s. v. Tôzan corrected the reading. Next sentence."],
        )
        self.assertFalse(english_line_has_terminal_boundary("Looking up the Vocabvlario s. v."))
        self.assertTrue(english_line_has_terminal_boundary("Tôzan corrected the reading."))

    def test_overlong_timeline_is_split_losslessly_at_entry_boundaries(self) -> None:
        text = " ".join(
            [
                "1534 — Nobunaga is born; the family remains in Owari",
                "1542 — Nobuhide campaigns in Mikawa; the army returns",
                "1544 — The campaign moves into Mino; resistance continues",
                "1546 — Kichibōshi celebrates his coming of age",
            ]
        )
        units = split_source_units(text, "en", max_chars=95)
        self.assertGreater(len(units), 1)
        self.assertTrue(all(len(unit) <= 95 for unit in units))
        self.assertEqual(" ".join(units), text)

    def test_timeline_entries_split_even_when_each_entry_is_short(self) -> None:
        text = (
            "1534 — Nobunaga is born 1542 — Nobuhide campaigns in Mikawa "
            "1544 — The army enters Mino"
        )
        self.assertEqual(
            split_english_timeline_entries(text),
            [
                "1534 — Nobunaga is born",
                "1542 — Nobuhide campaigns in Mikawa",
                "1544 — The army enters Mino",
            ],
        )

    def test_overlong_entry_prefers_early_semicolon_to_arbitrary_word_cut(self) -> None:
        prefix = "1569 — The attacking army is repelled;"
        text = f"{prefix} " + " ".join(["Nobunaga"] * 80)

        units = split_source_units(text, "en", max_chars=220)

        self.assertEqual(units[0], prefix)
        self.assertTrue(all(len(unit) <= 220 for unit in units))
        self.assertEqual(" ".join(units), text)

    def test_timeline_fragments_share_a_keep_together_group(self) -> None:
        text = "1573 — " + " ".join(["campaign"] * 180)

        grouped = split_source_units_grouped(text, "en", max_chars=220)

        self.assertGreater(len(grouped), 1)
        self.assertEqual({group for _unit, group in grouped}, {"timeline:1573"})
        self.assertEqual(" ".join(unit for unit, _group in grouped), text)

    def test_chinese_markdown_spine_preserves_body_and_headings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            markdown = Path(temporary) / "zh.md"
            markdown.write_text(
                "# 德川家康\n\n## 第一章 乱世破晓\n\n"
                "这是足够长的第一段正文，用来验证中文源文本不会被英文字符检查误删。\n\n"
                "这是第二段正文，也应当完整保留并作为同一章节中的独立段落。\n",
                encoding="utf-8",
            )
            task = {
                "book_id": "zh-fixture",
                "source_spine_lang": "zh",
                "title_en": "Tokugawa Ieyasu",
                "title_zh": "德川家康",
                "title_ja": "徳川家康",
                "start_marker": "第一章 乱世破晓",
                "start_marker_exact": True,
                "allow_markdown_headings": True,
            }
            chapters = parse_chapters(markdown, task, max_unit_chars=900)
            self.assertEqual(chapters[0]["title"], "第一章 乱世破晓")
            self.assertEqual(len(chapters[0]["paragraphs"]), 2)
            self.assertIn("中文源文本", chapters[0]["paragraphs"][0]["text"])

    def test_bold_cjk_chapter_titles_can_be_promoted_without_list_false_positives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            markdown = Path(temporary) / "zh.md"
            markdown.write_text(
                "**一 乱世破晓**\n\n"
                "这是足够长的正文，用来确认真正的粗体章节标题能够被保留。\n\n"
                "六、占高台院西苑为居所。\n\n"
                "这是同一章节的后续正文，不应被误判成一个新的章节。\n\n"
                "**二 嫁途风波**\n\n"
                "这是第二章的完整正文，也应当被正确划分。\n",
                encoding="utf-8",
            )
            task = {
                "book_id": "zh-bold-fixture",
                "source_spine_lang": "zh",
                "title_en": "Fixture",
                "title_zh": "测试",
                "title_ja": "テスト",
                "start_marker": "一 乱世破晓",
                "start_marker_exact": True,
                "bold_lines_as_headings": True,
                "bold_heading_patterns": [
                    r"^[〇零一二三四五六七八九十百千万两兩○]+\s+[^，。！？；：]{1,30}$"
                ],
                "allow_markdown_headings": True,
            }
            chapters = parse_chapters(markdown, task, max_unit_chars=900)
            self.assertEqual([chapter["title"] for chapter in chapters], ["一 乱世破晓", "二 嫁途风波"])
            self.assertIn("六、占高台院西苑为居所。", chapters[0]["paragraphs"][1]["text"])

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
