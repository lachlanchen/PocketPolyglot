#!/usr/bin/env python3
"""Regression tests for quadrilingual Japanese ruby validation."""

from __future__ import annotations

import unittest

from codex_trilingual_plain_json_worker import tokenize_ja
from validate_quadrilingual_interlinear_json import validate_ja


class QuadrilingualJapaneseValidationTest(unittest.TestCase):
    def validate(self, tokens: list[dict[str, str]]) -> list[str]:
        errors: list[str] = []
        validate_ja(tokens, "ja", errors, require_japanese=True)
        return errors

    def test_compound_ruby_from_shared_tokenizer_is_valid(self) -> None:
        for text in (
            "長明溝から水を引き、町なかの通りへ流し込む。",
            "『文選』「呉都賦」の劉逵注による。",
        ):
            self.assertEqual(self.validate(tokenize_ja(text)), [])

    def test_kanji_token_still_requires_furigana(self) -> None:
        errors = self.validate([{"t": "長明溝"}, {"t": "から水を引く。"}])
        self.assertTrue(any("needs furigana" in error for error in errors))

    def test_furigana_cannot_attach_to_kana_only_token(self) -> None:
        errors = self.validate([{"t": "ながい", "r": "ながい"}])
        self.assertTrue(any("kanji-bearing token" in error for error in errors))

    def test_sentence_length_ruby_is_rejected(self) -> None:
        errors = self.validate(
            [{"t": "長明溝から町中まで水を流し込む長い一文", "r": "ちょうめいこうからまちなかまで"}]
        )
        self.assertTrue(any("short word or stem" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
