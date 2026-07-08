#!/usr/bin/env python3
"""Validate trilingual English/Japanese/Chinese interlinear JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SPACE_RE = re.compile(r"\s+")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")
KANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30fa]")
LATIN_RE = re.compile(r"[A-Za-z]")
VISUAL_TECHNICAL_RE = re.compile(r"\b(?:figs?|figure|track)\s*\.?\s*\d*|[図圖图]\s*\d*", re.IGNORECASE)
MUSIC_TABLE_TOKEN_RE = re.compile(
    r"\b(?:[A-G](?:[#b+>°])?(?:m|maj|min|dim|aug)?\d*|[b#]?(?:I|II|III|IV|V|VI|VII|i|ii|iii|iv|v|vi|vii)|major|minor|dim|aug)\b"
)
TECHNICAL_NON_HAN_RE = re.compile(
    r"\d|[._/@#%°℃₂₃+-]|[A-Z]{2,}|"
    r"\b(?:sol|jpg|jpeg|ascii|nasa|mav|eva|jpl|capcom|hermes|ares|"
    r"coda|fine|ritard|ritardando|simile|tacet|tutte|piano|forte|fortissimo|pianissimo|"
    r"lennon|mccartney|guitar|fender|stratocaster|star|licks|hal|leonard|modes|starter|series)\b",
    re.IGNORECASE,
)
GRAMMAR_ROLES = {
    "subject",
    "predicate",
    "object",
    "attributive",
    "adverbial",
    "complement",
    "topic",
    "function",
}
ALLOWED_TEXT_CONTROLS = {"\t", "\n", "\r"}


def control_char_positions(text: str) -> list[tuple[int, int]]:
    return [
        (index, ord(ch))
        for index, ch in enumerate(str(text or ""))
        if ord(ch) < 32 and ch not in ALLOWED_TEXT_CONTROLS
    ]


def validate_no_control_chars(value: Any, where: str, errors: list[str]) -> None:
    if isinstance(value, str):
        bad = control_char_positions(value)
        if bad:
            preview = ", ".join(f"{index}:U+{code:04X}" for index, code in bad[:8])
            errors.append(f"{where}: contains forbidden control character(s): {preview}")
    elif isinstance(value, dict):
        for key, child in value.items():
            validate_no_control_chars(child, f"{where}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_no_control_chars(child, f"{where}[{index}]", errors)


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", str(text or "")).strip()


def no_space(text: str) -> str:
    return "".join(str(text or "").split())


def normalized_latin_fragment(text: str) -> str:
    return re.sub(r"[^a-z0-9#.+/%°-]+", "", compact(text).lower()).strip(".")


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def has_language_content(text: str) -> bool:
    return bool(HAN_RE.search(text) or KANA_RE.search(text) or LATIN_RE.search(text))


def music_table_token_count(text: str) -> int:
    return len(MUSIC_TABLE_TOKEN_RE.findall(compact(text)))


def allows_latin_music_table_fragment(source_text: str, target_text: str) -> bool:
    target = compact(target_text)
    source = compact(source_text)
    if not target or HAN_RE.search(target) or KANA_RE.search(target):
        return False
    if len(target) > 220:
        return False
    token_count = music_table_token_count(source + " " + target)
    prose_words = re.findall(r"\b[A-Za-z]{4,}\b", source + " " + target)
    symbol_count = len(re.findall(r"[^A-Za-z0-9\s]", source + " " + target))
    return token_count >= 6 and (symbol_count >= 4 or len(prose_words) <= 18)


def allows_non_han_zh_fragment(source_text: str, zh_text: str) -> bool:
    """Allow short technical/proper-name fragments that are naturally non-Han."""
    text = compact(zh_text)
    if not text or HAN_RE.search(text) or KANA_RE.search(text):
        return False
    source = compact(source_text)
    if allows_latin_music_table_fragment(source, text):
        return True
    if normalized_latin_fragment(text) and normalized_latin_fragment(text) == normalized_latin_fragment(source):
        return len(text) <= 90
    if len(text) > 50:
        return False
    if len(LATIN_RE.findall(text)) > 34:
        return False
    return bool(TECHNICAL_NON_HAN_RE.search(text) or TECHNICAL_NON_HAN_RE.search(source))


def allows_non_japanese_ja_fragment(source_text: str, ja_text: str) -> bool:
    """Allow Latin music markings, product titles, and other technical fragments."""
    text = compact(ja_text)
    if not text or HAN_RE.search(text) or KANA_RE.search(text):
        return False
    source = compact(source_text)
    if allows_latin_music_table_fragment(source, text):
        return True
    if normalized_latin_fragment(text) and normalized_latin_fragment(text) == normalized_latin_fragment(source):
        return len(text) <= 90
    if len(text) > 50:
        return False
    return bool(TECHNICAL_NON_HAN_RE.search(text) or TECHNICAL_NON_HAN_RE.search(source))


def allows_technical_ja_without_kana(source_text: str, ja_text: str) -> bool:
    """Allow figure/track-only rows that will receive kanji ruby after promotion."""
    text = compact(ja_text)
    source = compact(source_text)
    if not text or KANA_RE.search(text):
        return False
    if not (VISUAL_TECHNICAL_RE.search(source) or VISUAL_TECHNICAL_RE.search(text)):
        return False
    prose_words = re.findall(r"\b[A-Za-z]{3,}\b", source)
    symbol_count = len(re.findall(r"[^A-Za-z0-9\s]", source))
    digit_count = len(re.findall(r"\d", source))
    return len(prose_words) <= 8 or symbol_count + digit_count >= 6


def validate_token_shape(tokens: Any, where: str, errors: list[str]) -> bool:
    if not isinstance(tokens, list):
        errors.append(f"{where}: must be a token list")
        return False
    ok = True
    for token_index, token in enumerate(tokens):
        if not isinstance(token, dict) or "t" not in token:
            errors.append(f"{where}[{token_index}]: token must be an object containing t")
            ok = False
            continue
        legacy_keys = sorted({"role", "syntax"}.intersection(token))
        if legacy_keys:
            errors.append(f"{where}[{token_index}]: use only g for grammar role, not {', '.join(legacy_keys)}")
            ok = False
        role = token.get("g")
        if role and str(role) not in GRAMMAR_ROLES:
            allowed = ", ".join(sorted(GRAMMAR_ROLES))
            errors.append(f"{where}[{token_index}]: unsupported grammar role {role!r}; use one of {allowed}")
            ok = False
        reading = token.get("r")
        if reading is not None and not isinstance(reading, str):
            errors.append(f"{where}[{token_index}]: r must be a string when present")
            ok = False
    return ok


def validate_en_tokens(tokens: Any, where: str, errors: list[str]) -> None:
    if not validate_token_shape(tokens, where, errors):
        return
    for token_index, token in enumerate(tokens):
        if token.get("r"):
            errors.append(f"{where}[{token_index}]: English tokens must not carry ruby/pinyin")


def validate_zh_tokens(
    tokens: Any,
    where: str,
    errors: list[str],
    *,
    require_han: bool = False,
    allow_kana: bool = False,
) -> None:
    if not validate_token_shape(tokens, where, errors):
        return
    text_parts: list[str] = []
    for token_index, token in enumerate(tokens):
        text = str(token.get("t", ""))
        text_parts.append(text)
        reading = str(token.get("r", ""))
        has_han = bool(HAN_RE.search(text))
        is_single_han = bool(SINGLE_HAN_RE.fullmatch(text))
        if has_han and not is_single_han:
            errors.append(f"{where}[{token_index}]: Chinese Han tokens must be exactly one character")
        if is_single_han and not reading:
            errors.append(f"{where}[{token_index}]: Chinese Han token needs pinyin")
        if reading and not is_single_han:
            errors.append(f"{where}[{token_index}]: pinyin may only be attached to one Chinese Han character")
    text = "".join(text_parts)
    if require_han and not HAN_RE.search(text):
        errors.append(f"{where}: Chinese text must contain Han characters")
    if KANA_RE.search(text) and not allow_kana:
        errors.append(f"{where}: Chinese row contains Japanese kana")


def validate_ja_tokens(tokens: Any, where: str, errors: list[str], *, require_japanese: bool = False) -> None:
    if not validate_token_shape(tokens, where, errors):
        return
    text_parts: list[str] = []
    furigana_parts: list[str] = []
    for token_index, token in enumerate(tokens):
        text = str(token.get("t", ""))
        text_parts.append(text)
        reading = str(token.get("r", ""))
        if reading:
            furigana_parts.append(reading)
        has_kanji = bool(HAN_RE.search(text))
        is_single_kanji = bool(SINGLE_HAN_RE.fullmatch(text))
        if has_kanji and not is_single_kanji:
            errors.append(f"{where}[{token_index}]: Japanese kanji tokens must be exactly one kanji character")
        if is_single_kanji and not reading:
            errors.append(f"{where}[{token_index}]: Japanese kanji token needs furigana")
        if reading and not is_single_kanji:
            errors.append(f"{where}[{token_index}]: furigana may only be attached to one Japanese kanji character")
    text = "".join(text_parts)
    readings = "".join(furigana_parts)
    if require_japanese and not (KANA_RE.search(text) or KANA_RE.search(readings)):
        errors.append(f"{where}: Japanese row has no kana/furigana evidence and may be Chinese")


def validate_title(title: Any, where: str, errors: list[str]) -> None:
    if not isinstance(title, dict):
        errors.append(f"{where}: title must be an object")
        return
    validate_en_tokens(title.get("en", []), f"{where}.en", errors)
    validate_zh_tokens(title.get("zh", []), f"{where}.zh", errors)
    validate_ja_tokens(title.get("ja", []), f"{where}.ja", errors)


def validate_unit(unit: Any, where: str, errors: list[str]) -> tuple[str, str, str]:
    if not isinstance(unit, dict):
        errors.append(f"{where}: unit must be an object")
        return "", "", ""
    source_en = str(unit.get("source_en", ""))
    source_zh = str(unit.get("source_zh", ""))
    source_ja = str(unit.get("source_ja", ""))
    source_basis = source_zh or source_ja or source_en
    require_content = has_language_content(source_basis)
    require_zh_han = require_content and (not source_zh or bool(HAN_RE.search(source_zh)))
    allow_zh_kana = bool(source_zh and KANA_RE.search(source_zh))
    validate_en_tokens(unit.get("en", []), f"{where}.en", errors)
    en_text = token_text(unit.get("en", []))
    zh_text = token_text(unit.get("zh", []))
    ja_text = token_text(unit.get("ja", []))
    require_ja = require_content and not (
        allows_non_japanese_ja_fragment(source_basis, ja_text)
        or allows_technical_ja_without_kana(source_basis, ja_text)
    )
    validate_zh_tokens(unit.get("zh", []), f"{where}.zh", errors, require_han=False, allow_kana=allow_zh_kana)
    validate_ja_tokens(unit.get("ja", []), f"{where}.ja", errors, require_japanese=require_ja)
    if require_zh_han and not HAN_RE.search(zh_text) and not allows_non_han_zh_fragment(source_basis, zh_text):
        errors.append(f"{where}.zh: Chinese text must contain Han characters")
    if source_en and compact(en_text) != compact(source_en):
        errors.append(f"{where}: en tokens do not reconstruct unit source_en")
    if source_zh and no_space(zh_text) != no_space(source_zh):
        errors.append(f"{where}: zh tokens do not reconstruct unit source_zh")
    if source_ja and no_space(ja_text) != no_space(source_ja):
        errors.append(f"{where}: ja tokens do not reconstruct unit source_ja")
    if not zh_text.strip():
        errors.append(f"{where}: zh text is empty")
    if not ja_text.strip():
        errors.append(f"{where}: ja text is empty")
    return en_text, zh_text, ja_text


def validate_chunk(source: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    validate_no_control_chars(source, "source", errors)
    validate_no_control_chars(result, "result", errors)
    if result.get("mode") not in {"trilingual_standard", None}:
        errors.append("mode must be trilingual_standard when present")
    if result.get("chunk_id") != source["chunk_id"]:
        errors.append(f"chunk_id mismatch: expected {source['chunk_id']!r}")
    chapter = result.get("chapter")
    if not isinstance(chapter, dict):
        errors.append("chapter: must be an object")
    else:
        if chapter.get("id") != source["chapter_id"]:
            errors.append(f"chapter.id mismatch: expected {source['chapter_id']!r}")
        validate_title(chapter.get("title", {}), "chapter.title", errors)
    paragraphs = result.get("paragraphs")
    if not isinstance(paragraphs, list):
        return errors + ["paragraphs must be a list"]
    expected_ids = [paragraph["id"] for paragraph in source["paragraphs"]]
    got_ids = [paragraph.get("id") for paragraph in paragraphs if isinstance(paragraph, dict)]
    if got_ids != expected_ids:
        errors.append(f"paragraph id/order mismatch: expected {expected_ids}, got {got_ids}")
    source_by_id = {paragraph["id"]: str(paragraph.get("en", "")) for paragraph in source["paragraphs"]}
    for paragraph_index, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, dict):
            errors.append(f"paragraphs[{paragraph_index}]: must be an object")
            continue
        paragraph_id = paragraph.get("id")
        where = f"paragraphs[{paragraph_index}]"
        if paragraph_id not in source_by_id:
            continue
        expected_en = source_by_id[paragraph_id]
        paragraph_source_en = str(paragraph.get("source_en", ""))
        if expected_en and compact(paragraph_source_en) != compact(expected_en):
            errors.append(f"{paragraph_id}: paragraph source_en changed")
        if not expected_en and not compact(paragraph_source_en):
            errors.append(f"{paragraph_id}: paragraph source_en is required when English is generated")
        units = paragraph.get("units")
        if not isinstance(units, list) or not units:
            errors.append(f"{paragraph_id}: missing units")
            continue
        rebuilt_en_parts: list[str] = []
        for unit_index, unit in enumerate(units):
            en_text, _zh_text, _ja_text = validate_unit(unit, f"{where}.units[{unit_index}]", errors)
            rebuilt_en_parts.append(en_text)
        expected_rebuilt_en = expected_en or paragraph_source_en
        if expected_rebuilt_en and compact("".join(rebuilt_en_parts)) != compact(expected_rebuilt_en):
            errors.append(f"{paragraph_id}: units do not reconstruct paragraph English")
    return errors


def validate_book(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    validate_no_control_chars(data, "book", errors)
    if data.get("mode") != "trilingual_standard":
        errors.append("mode must be trilingual_standard")
    validate_title(data.get("title", {}), "title", errors)
    chapters = data.get("chapters")
    if not isinstance(chapters, list):
        return errors + ["chapters must be a list"]
    for chapter_index, chapter in enumerate(chapters):
        where = f"chapters[{chapter_index}]"
        if not isinstance(chapter, dict):
            errors.append(f"{where}: must be an object")
            continue
        validate_title(chapter.get("title", {}), f"{where}.title", errors)
        for paragraph_index, paragraph in enumerate(chapter.get("paragraphs", [])):
            if not isinstance(paragraph, dict):
                errors.append(f"{where}.paragraphs[{paragraph_index}]: must be an object")
                continue
            source_en = str(paragraph.get("source_en", ""))
            units = paragraph.get("units")
            if not isinstance(units, list) or not units:
                errors.append(f"{where}.paragraphs[{paragraph_index}]: missing units")
                continue
            rebuilt_en_parts: list[str] = []
            for unit_index, unit in enumerate(units):
                en_text, _zh_text, _ja_text = validate_unit(
                    unit,
                    f"{where}.paragraphs[{paragraph_index}].units[{unit_index}]",
                    errors,
                )
                rebuilt_en_parts.append(en_text)
            if source_en and compact("".join(rebuilt_en_parts)) != compact(source_en):
                errors.append(f"{where}.paragraphs[{paragraph_index}]: units do not reconstruct paragraph English")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path")
    args = parser.parse_args()

    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    errors = validate_book(data)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
