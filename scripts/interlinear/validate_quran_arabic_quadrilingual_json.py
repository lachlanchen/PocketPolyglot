#!/usr/bin/env python3
"""Validate Quran Arabic quadrilingual JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
LATIN_RE = re.compile(r"[A-Za-z]")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
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


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def token_readings(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("r", "")) for token in tokens if isinstance(token, dict))


def validate_tokens(tokens: Any, where: str, errors: list[str], *, pattern: re.Pattern[str] | None = None) -> None:
    if not isinstance(tokens, list) or not tokens:
        errors.append(f"{where}: missing token list")
        return
    for index, token in enumerate(tokens):
        if not isinstance(token, dict) or "t" not in token:
            errors.append(f"{where}[{index}]: token must contain t")
            continue
        if token.get("r") is not None and not isinstance(token.get("r"), str):
            errors.append(f"{where}[{index}]: r must be a string")
        if token.get("g") and token.get("g") not in GRAMMAR_ROLES:
            errors.append(f"{where}[{index}]: unsupported grammar role {token.get('g')!r}")
    if pattern and not (pattern.search(token_text(tokens)) or pattern.search(token_readings(tokens))):
        errors.append(f"{where}: does not contain expected script evidence")


def validate_book(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("mode") != "arabic_quadrilingual_main":
        errors.append("mode must be arabic_quadrilingual_main")
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != 114:
        errors.append(f"chapters: expected 114, got {len(chapters) if isinstance(chapters, list) else 'non-list'}")
        return errors
    unit_count = 0
    for c_index, chapter in enumerate(chapters):
        title = chapter.get("title") or {}
        validate_tokens(title.get("ar"), f"chapters[{c_index}].title.ar", errors, pattern=ARABIC_RE)
        validate_tokens(title.get("en"), f"chapters[{c_index}].title.en", errors, pattern=LATIN_RE)
        validate_tokens(title.get("ja"), f"chapters[{c_index}].title.ja", errors)
        validate_tokens(title.get("zh"), f"chapters[{c_index}].title.zh", errors, pattern=HAN_RE)
        for p_index, paragraph in enumerate(chapter.get("paragraphs") or []):
            for u_index, unit in enumerate(paragraph.get("units") or []):
                where = f"chapters[{c_index}].paragraphs[{p_index}].units[{u_index}]"
                unit_count += 1
                validate_tokens(unit.get("ar"), f"{where}.ar", errors, pattern=ARABIC_RE)
                validate_tokens(unit.get("en"), f"{where}.en", errors, pattern=LATIN_RE)
                validate_tokens(unit.get("ja"), f"{where}.ja", errors, pattern=KANA_RE)
                validate_tokens(unit.get("zh"), f"{where}.zh", errors, pattern=HAN_RE)
                if not unit.get("verse_key"):
                    errors.append(f"{where}: missing verse_key")
    if unit_count != 6348:
        errors.append(f"unit_count: expected 6348 including unnumbered basmalas, got {unit_count}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path")
    args = parser.parse_args()
    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    errors = validate_book(data)
    if errors:
        for error in errors[:160]:
            print(error)
        raise SystemExit(1)
    print(f"ok: {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
