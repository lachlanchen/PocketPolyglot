#!/usr/bin/env python3
"""Focused tests for deterministic promotion of plain trilingual chunks."""

from __future__ import annotations

import unittest

from codex_trilingual_plain_json_worker import (
    promote_plain_chunk,
    prompt_for_plain_chunk,
    tokenize_ja,
)
from validate_trilingual_interlinear_json import validate_chunk


class TrilingualPlainPromotionTest(unittest.TestCase):
    def test_prompt_preserves_unmapped_latin_names(self) -> None:
        source = {
            "chunk_id": "fixture-c0001",
            "chapter_id": "chapter-001",
            "chapter_number": 1,
            "chapter_title_en": "Preface",
            "chapter_part_en": "",
            "source_spine_lang": "en",
            "reference": {},
            "paragraphs": [
                {
                    "id": "fixture-p0001",
                    "en": "Paul Yachita Tsuchihashi prepared the tables.",
                }
            ],
        }

        prompt = prompt_for_plain_chunk(source)

        self.assertIn("preserve an unmapped Latin-script personal name", prompt)
        self.assertIn("Never invent a Chinese-character spelling", prompt)
        self.assertIn("Never invent kanji for an unmapped personal name", prompt)

    def test_terminology_contract_rejects_wrong_historical_title(self) -> None:
        source = {
            "chunk_id": "fixture-c0001",
            "chapter_id": "chapter-001",
            "chapter_number": 1,
            "chapter_title_en": "Preface",
            "source_spine_lang": "en",
            "reference": {},
            "translation_contract": {
                "terminology": [
                    {
                        "source": "Lord Nobunaga",
                        "ja": "信長公",
                        "zh": "信长公",
                        "forbidden": {"zh": ["信长公爵"]},
                    }
                ]
            },
            "paragraphs": [
                {
                    "id": "fixture-p0001",
                    "en": "The spirit of Lord Nobunaga remained.",
                }
            ],
        }
        plain = {
            "chunk_id": "fixture-c0001",
            "paragraphs": [
                {
                    "id": "fixture-p0001",
                    "units": [
                        {
                            "unit_id": "fixture-p0001-u001",
                            "ja": "信長公の精神が残った。",
                            "zh": "信长公爵的精神仍然存在。",
                        }
                    ],
                }
            ],
        }

        promoted = promote_plain_chunk(source, plain)
        errors = validate_chunk(source, promoted)

        self.assertTrue(any("forbidden zh terminology" in error for error in errors))

    def test_preferred_terminology_does_not_reject_natural_variant(self) -> None:
        source = {
            "chunk_id": "fixture-c0001",
            "chapter_id": "chapter-001",
            "chapter_number": 1,
            "chapter_title_en": "Preface",
            "source_spine_lang": "en",
            "reference": {},
            "translation_contract": {
                "terminology": [
                    {
                        "source": "Willem Boot",
                        "ja": "ウィレム・ブート",
                        "zh": "Willem Boot",
                        "enforcement": "preferred",
                    }
                ]
            },
            "paragraphs": [
                {
                    "id": "fixture-p0001",
                    "en": "Professor Willem Boot taught the course.",
                }
            ],
        }
        plain = {
            "chunk_id": "fixture-c0001",
            "paragraphs": [
                {
                    "id": "fixture-p0001",
                    "units": [
                        {
                            "unit_id": "fixture-p0001-u001",
                            "ja": "ウィレム・ブート教授がその授業を担当した。",
                            "zh": "威廉·布特教授讲授了这门课程。",
                        }
                    ],
                }
            ],
        }

        promoted = promote_plain_chunk(source, plain)

        self.assertEqual(validate_chunk(source, promoted), [])

    def test_compound_ruby_keeps_real_word_readings(self) -> None:
        tokens = tokenize_ja("この大砂漠と図書館、荒々しく広がる世界。")
        ruby = {token["t"]: token["r"] for token in tokens if token.get("r")}

        self.assertEqual(ruby["砂漠"], "さばく")
        self.assertEqual(ruby["図書館"], "としょかん")
        self.assertEqual(ruby["荒々"], "あらあら")
        self.assertNotIn("さば", ruby.values())
        self.assertNotIn("ょか", ruby.values())

    def test_promotion_preserves_source_figure_metadata(self) -> None:
        source = {
            "chunk_id": "fixture-c0001",
            "chapter_id": "chapter-001",
            "chapter_number": 1,
            "chapter_title_en": "Introduction",
            "source_spine_lang": "en",
            "reference": {},
            "paragraphs": [
                {
                    "id": "fixture-p0001",
                    "en": "A desert figure appears here.",
                    "figures": [
                        {
                            "path": "assets/fixture.png",
                            "caption": "Desert figure",
                            "source_order": 1,
                            "source_page_index": 7,
                        }
                    ],
                    "source_pages": [7],
                }
            ],
        }
        plain = {
            "chunk_id": "fixture-c0001",
            "paragraphs": [
                {
                    "id": "fixture-p0001",
                    "units": [
                        {
                            "unit_id": "fixture-p0001-u001",
                            "ja": "ここに砂漠の図がある。",
                            "zh": "这里有一幅沙漠图。",
                        }
                    ],
                }
            ],
        }

        promoted = promote_plain_chunk(source, plain)
        paragraph = promoted["paragraphs"][0]

        self.assertEqual(paragraph["figures"], source["paragraphs"][0]["figures"])
        self.assertEqual(paragraph["source_pages"], [7])
        self.assertIsNot(paragraph["figures"], source["paragraphs"][0]["figures"])
        self.assertEqual(validate_chunk(source, promoted), [])


if __name__ == "__main__":
    unittest.main()
