#!/usr/bin/env python3
"""Validate the interlinear JSON structure and source-text preservation."""

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
PLACEHOLDER_JA = {"注", "注。", "。"}
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


def normalize(text: str) -> str:
    return SPACE_RE.sub("", text or "")


def token_text(tokens: list[dict[str, Any]]) -> str:
    return "".join(str(token.get("t", "")) for token in tokens)


def ja_lines_text(ja: Any) -> str:
    if not isinstance(ja, list):
        return ""
    return "".join(token_text(line) for line in ja if isinstance(line, list))


def text_target(node: dict[str, Any]) -> str:
    """Return the text that rendered tokens are expected to reconstruct."""
    corrected = str(node.get("corrected_text", "")).strip()
    if corrected:
        return corrected
    return str(node.get("source_text", ""))


def validate_token_shape(tokens: Any, where: str, errors: list[str]) -> bool:
    if not isinstance(tokens, list):
        errors.append(f"{where}: must be a token list")
        return False
    ok = True
    for token_index, token in enumerate(tokens):
        if not isinstance(token, dict) or "t" not in token:
            errors.append(f"{where}[{token_index}]: token must contain t")
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
    return ok


def validate_zh_tokens(tokens: Any, where: str, errors: list[str]) -> None:
    if not validate_token_shape(tokens, where, errors):
        return
    for token_index, token in enumerate(tokens):
        text = str(token.get("t", ""))
        reading = str(token.get("r", ""))
        has_han = bool(HAN_RE.search(text))
        is_single_han = bool(SINGLE_HAN_RE.fullmatch(text))
        if has_han and not is_single_han:
            errors.append(f"{where}[{token_index}]: Chinese Han tokens must be exactly one character")
        if is_single_han and not reading:
            errors.append(f"{where}[{token_index}]: Chinese Han token needs pinyin")
        if reading and not is_single_han:
            errors.append(f"{where}[{token_index}]: pinyin may only be attached to one Chinese Han character")


def validate_ja_tokens(tokens: Any, where: str, errors: list[str]) -> None:
    if not validate_token_shape(tokens, where, errors):
        return
    for token_index, token in enumerate(tokens):
        text = str(token.get("t", ""))
        reading = str(token.get("r", ""))
        has_kanji = bool(HAN_RE.search(text))
        is_single_kanji = bool(SINGLE_HAN_RE.fullmatch(text))
        if has_kanji and not is_single_kanji:
            errors.append(f"{where}[{token_index}]: Japanese kanji tokens must be exactly one kanji character")
        if is_single_kanji and not reading:
            errors.append(f"{where}[{token_index}]: Japanese kanji token needs furigana")
        if reading and not is_single_kanji:
            errors.append(f"{where}[{token_index}]: furigana may only be attached to one Japanese kanji character")


def validate_named_tokens(node: dict[str, Any], where: str, errors: list[str]) -> None:
    if "title_zh" in node:
        validate_zh_tokens(node.get("title_zh"), f"{where}.title_zh", errors)
    if "title_ja" in node:
        validate_ja_tokens(node.get("title_ja"), f"{where}.title_ja", errors)
    if "place_zh" in node:
        validate_zh_tokens(node.get("place_zh"), f"{where}.place_zh", errors)
    if "place_ja" in node:
        validate_ja_tokens(node.get("place_ja"), f"{where}.place_ja", errors)


def validate_unit(unit: dict[str, Any], where: str, errors: list[str]) -> str:
    if "zh" not in unit or not isinstance(unit["zh"], list):
        errors.append(f"{where}: missing zh token list")
        return ""
    validate_zh_tokens(unit["zh"], f"{where}.zh", errors)
    ja = unit.get("ja")
    if not isinstance(ja, list) or len(ja) != 2:
        errors.append(f"{where}: ja must contain exactly two line arrays")
    else:
        for line_index, line in enumerate(ja):
            if not isinstance(line, list):
                errors.append(f"{where}.ja[{line_index}]: line must be a token list")
                continue
            validate_ja_tokens(line, f"{where}.ja[{line_index}]", errors)
        ja_text = normalize(ja_lines_text(ja))
        if not ja_text:
            errors.append(f"{where}: Japanese comment is empty")
        if ja_text in PLACEHOLDER_JA:
            errors.append(f"{where}: Japanese comment is a placeholder, not aligned text")
    zh_text = token_text(unit["zh"])
    target = text_target(unit)
    if target and normalize(zh_text) != normalize(target):
        errors.append(f"{where}: zh tokens do not reconstruct corrected/source text")
    return zh_text


def validate_interlinear(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("mode") != "zh_main_ja_comment":
        errors.append("mode must be zh_main_ja_comment")
    if not isinstance(data.get("sections"), list):
        errors.append("sections must be a list")
        return errors
    title = data.get("title", {})
    if isinstance(title, dict):
        validate_zh_tokens(title.get("zh", []), "title.zh", errors)
        validate_ja_tokens(title.get("ja", []), "title.ja", errors)

    for section_index, section in enumerate(data["sections"]):
        validate_named_tokens(section, f"sections[{section_index}]", errors)
        for subsection_index, subsection in enumerate(section.get("subsections", [])):
            validate_named_tokens(subsection, f"sections[{section_index}].subsections[{subsection_index}]", errors)
            for story_index, story in enumerate(subsection.get("stories", [])):
                validate_named_tokens(story, f"sections[{section_index}].subsections[{subsection_index}].stories[{story_index}]", errors)
                for paragraph_index, paragraph in enumerate(story.get("paragraphs", [])):
                    where = f"sections[{section_index}].subsections[{subsection_index}].stories[{story_index}].paragraphs[{paragraph_index}]"
                    units = paragraph.get("units")
                    if not isinstance(units, list) or not units:
                        errors.append(f"{where}: missing units")
                        continue
                    rebuilt_parts: list[str] = []
                    for unit_index, unit in enumerate(units):
                        rebuilt_parts.append(validate_unit(unit, f"{where}.units[{unit_index}]", errors))
                    rebuilt = "".join(rebuilt_parts)
                    target = text_target(paragraph)
                    if target and normalize(rebuilt) != normalize(target):
                        errors.append(f"{where}: units do not reconstruct paragraph corrected/source text")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path")
    args = parser.parse_args()

    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    errors = validate_interlinear(data)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
