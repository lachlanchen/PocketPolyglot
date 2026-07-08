#!/usr/bin/env python3
"""Audit completed trilingual chunks for common render/source-quality defects."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
KANA_LETTER_RE = re.compile(r"[\u3041-\u3096\u30a1-\u30fa]")
LATIN_RE = re.compile(r"[A-Za-z]")
SUBSTANTIVE_RE = re.compile(r"[A-Za-z\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
NUMBER_CHROME_RE = re.compile(r"^[\s\[\]().,:;:：，。；、'’\"“”\-–—]*\d+[\d\s\[\]().,:;:：，。；、'’\"“”\-–—]*$")
LATIN_OR_NUMERIC_FRAGMENT_RE = re.compile(r"^[\s\w\d\[\]().,:;:：，。；、'’\"“”\-–—/]+$", re.I)
HTML_RE = re.compile(r"</?[a-z][^>]{0,120}>|&(?:nbsp|lt|gt|amp|quot|#\\d+);", re.I)
BOILERPLATE_RE = re.compile(
    r"(Project Gutenberg|Public domain|This work is in the public domain|"
    r"版权所有|版權所有|ISBN|Global Ratio|#\\s*(?:redirect|重定向)|"
    r"^\\s*(?:file|image):|Wikisource|Wikipedia)",
    re.I,
)
SUSPICIOUS_SOURCE_RE = re.compile(r"(\\b(?:OCR|PDF|scan|page)\\b|原书第\\s*\\d+\\s*页)", re.I)
CONTROL_ALLOWED = {"\t", "\n", "\r"}
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


def compact(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def role_counts(tokens: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not isinstance(tokens, list):
        return counts
    for token in tokens:
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", ""))
        if not (HAN_RE.search(text) or KANA_RE.search(text) or LATIN_RE.search(text)):
            continue
        role = str(token.get("g") or "")
        if role in GRAMMAR_ROLES:
            counts[role] += 1
    return counts


def has_forbidden_control(text: str) -> bool:
    return any(ord(ch) < 32 and ch not in CONTROL_ALLOWED for ch in str(text or ""))


def iter_strings(value: Any, path: str = ""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_strings(child, f"{path}[{index}]")


def check_unit(unit: dict[str, Any], where: str) -> list[str]:
    issues: list[str] = []
    en = token_text(unit.get("en"))
    zh = token_text(unit.get("zh"))
    ja = token_text(unit.get("ja"))
    if not en.strip() or not zh.strip() or not ja.strip():
        issues.append(f"{where}: empty language row")
    if NUMBER_CHROME_RE.fullmatch(en) and NUMBER_CHROME_RE.fullmatch(zh) and NUMBER_CHROME_RE.fullmatch(ja):
        issues.append(f"{where}: probable source line/page-number row: {compact(en)}")
        return issues
    if KANA_LETTER_RE.search(zh):
        issues.append(f"{where}: Chinese row contains kana: {compact(zh)}")
    ja_has_substantive = bool(SUBSTANTIVE_RE.search(ja))
    ja_has_kana = KANA_LETTER_RE.search(ja) or any(
        KANA_LETTER_RE.search(str(t.get("r", ""))) for t in unit.get("ja", []) if isinstance(t, dict)
    )
    ja_is_short_latin_fragment = bool(LATIN_OR_NUMERIC_FRAGMENT_RE.fullmatch(ja)) and len(ja) <= 80
    if ja_has_substantive and not ja_has_kana and not ja_is_short_latin_fragment:
        issues.append(f"{where}: Japanese row lacks kana/furigana evidence: {compact(ja)}")
    if LATIN_RE.search(en) and re.search(r"[a-z]{24,}", en):
        issues.append(f"{where}: English may have lost spaces: {compact(en)}")
    for lang, tokens in (("en", unit.get("en")), ("zh", unit.get("zh")), ("ja", unit.get("ja"))):
        counts = role_counts(tokens)
        total = sum(counts.values())
        if total >= 40:
            role, count = counts.most_common(1)[0]
            if count / total >= 0.95:
                issues.append(f"{where}.{lang}: grammar roles nearly all {role} ({count}/{total})")
    return issues


def audit_chunk(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    chunk_id = str(data.get("chunk_id") or path.stem)
    issues: list[str] = []
    for field, text in iter_strings(data):
        if has_forbidden_control(text):
            issues.append(f"{chunk_id}.{field}: forbidden control char")
        if HTML_RE.search(text):
            issues.append(f"{chunk_id}.{field}: HTML/entity fragment: {compact(text)}")
        if BOILERPLATE_RE.search(text):
            issues.append(f"{chunk_id}.{field}: boilerplate/source chrome: {compact(text)}")
        if SUSPICIOUS_SOURCE_RE.search(text):
            issues.append(f"{chunk_id}.{field}: suspicious source/OCR chrome: {compact(text)}")
    for p_index, paragraph in enumerate(data.get("paragraphs") or []):
        if not isinstance(paragraph, dict):
            continue
        for u_index, unit in enumerate(paragraph.get("units") or []):
            if isinstance(unit, dict):
                issues.extend(check_unit(unit, f"{chunk_id}.p{p_index}.u{u_index}"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-dir", action="append", type=Path, required=True)
    parser.add_argument("--max-issues", type=int, default=80)
    args = parser.parse_args()

    issues: list[str] = []
    for chunk_dir in args.chunk_dir:
        for path in sorted(chunk_dir.glob("*.json")):
            issues.extend(audit_chunk(path))
    for issue in issues[: args.max_issues]:
        print(issue)
    if len(issues) > args.max_issues:
        print(f"... {len(issues) - args.max_issues} more issue(s)")
    print(f"issues={len(issues)}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
