#!/usr/bin/env python3
"""Validate wenyan-main quadrilingual interlinear JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SPACE_RE = re.compile(r"\s+")
SOURCE_NOTE_MARK_RE = re.compile(r"(?<=[。！？!?；;：:])\d{1,3}(?=$|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff])")
BRACKETED_SOURCE_NOTE_MARK_RE = re.compile(r"^\s*[\[［【〈《(（]?\s*[一二三四五六七八九十百千万〇零０-９0-9]{1,8}\s*[\]］】〉》)）]?\s*$")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
LATIN_RE = re.compile(r"[A-Za-z]")
BAD_OUTPUT_RE = re.compile(
    r"<[^>]{1,120}>|&(?:lt|gt|amp|quot|nbsp);|"
    r"\{\{|\}\}|\[\[|\]\]|#重定向|#REDIRECT|mw-parser|"
    r"Wikisource|Wikipedia|維基文庫|维基文库|public domain|"
    r"Google|UNIVERSITY OF MICHIGAN|Digitized by|Page \d+",
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


def compact(text: str) -> str:
    return SPACE_RE.sub(" ", str(text or "")).strip()


def no_space(text: str) -> str:
    return "".join(str(text or "").split())


def source_compare_text(text: str) -> str:
    return SOURCE_NOTE_MARK_RE.sub("", no_space(text))


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def validate_output_quality(text: str, where: str, errors: list[str]) -> None:
    if BAD_OUTPUT_RE.search(text):
        errors.append(f"{where}: contains HTML/wiki/page boilerplate or scanned-book noise")


def source_has_content(text: str) -> bool:
    if BRACKETED_SOURCE_NOTE_MARK_RE.fullmatch(str(text or "")):
        return False
    return bool(HAN_RE.search(source_compare_text(text)))


def validate_token_shape(tokens: Any, where: str, errors: list[str]) -> bool:
    if not isinstance(tokens, list):
        errors.append(f"{where}: must be a token list")
        return False
    ok = True
    for index, token in enumerate(tokens):
        if not isinstance(token, dict) or "t" not in token:
            errors.append(f"{where}[{index}]: token must contain t")
            ok = False
            continue
        if token.get("g") and token.get("g") not in GRAMMAR_ROLES:
            errors.append(f"{where}[{index}]: unsupported grammar role {token.get('g')!r}")
            ok = False
        if token.get("r") is not None and not isinstance(token.get("r"), str):
            errors.append(f"{where}[{index}]: r must be a string")
            ok = False
    return ok


def validate_zh_like(tokens: Any, where: str, errors: list[str], *, require_han: bool = False) -> None:
    if not validate_token_shape(tokens, where, errors):
        return
    text = token_text(tokens)
    validate_output_quality(text, where, errors)
    if require_han and not HAN_RE.search(text):
        errors.append(f"{where}: must contain Han characters")
    for index, token in enumerate(tokens):
        t = str(token.get("t", ""))
        r = str(token.get("r", ""))
        is_single_han = bool(SINGLE_HAN_RE.fullmatch(t))
        if HAN_RE.search(t) and not is_single_han:
            errors.append(f"{where}[{index}]: Han tokens must be one character")
        if is_single_han and not r:
            errors.append(f"{where}[{index}]: Han token needs reading")
        if r and not is_single_han:
            errors.append(f"{where}[{index}]: reading may only attach to one Han character")


def validate_ja(tokens: Any, where: str, errors: list[str], *, require_japanese: bool = False) -> None:
    if not validate_token_shape(tokens, where, errors):
        return
    text = token_text(tokens)
    validate_output_quality(text, where, errors)
    readings = "".join(str(token.get("r", "")) for token in tokens if isinstance(token, dict))
    if require_japanese and not (KANA_RE.search(text) or KANA_RE.search(readings)):
        errors.append(f"{where}: Japanese row has no kana/furigana evidence")
    for index, token in enumerate(tokens):
        t = str(token.get("t", ""))
        r = str(token.get("r", ""))
        is_single_kanji = bool(SINGLE_HAN_RE.fullmatch(t))
        if HAN_RE.search(t) and not is_single_kanji:
            errors.append(f"{where}[{index}]: Japanese kanji tokens must be one character")
        if is_single_kanji and not r:
            errors.append(f"{where}[{index}]: kanji token needs furigana")
        if r and not is_single_kanji:
            errors.append(f"{where}[{index}]: furigana may only attach to one kanji")


def validate_en(tokens: Any, where: str, errors: list[str], *, require_latin: bool = False) -> None:
    if not validate_token_shape(tokens, where, errors):
        return
    text = token_text(tokens)
    validate_output_quality(text, where, errors)
    if require_latin and not LATIN_RE.search(text):
        errors.append(f"{where}: English row has no Latin text")
    for index, token in enumerate(tokens):
        if token.get("r"):
            errors.append(f"{where}[{index}]: English token must not have reading")


def validate_chunk(source: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("mode") not in {"quadrilingual_wenyan_main", None}:
        errors.append("mode must be quadrilingual_wenyan_main")
    if result.get("chunk_id") != source["chunk_id"]:
        errors.append(f"chunk_id mismatch: expected {source['chunk_id']!r}")
    paragraphs = result.get("paragraphs")
    if not isinstance(paragraphs, list):
        return errors + ["paragraphs must be a list"]
    expected_ids = [p["id"] for p in source.get("paragraphs", [])]
    got_ids = [p.get("id") for p in paragraphs if isinstance(p, dict)]
    if got_ids != expected_ids:
        errors.append(f"paragraph id/order mismatch: expected {expected_ids}, got {got_ids}")
    source_by_id = {p["id"]: str(p.get("wenyan", "")) for p in source.get("paragraphs", [])}
    for p_index, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, dict):
            errors.append(f"paragraphs[{p_index}]: must be object")
            continue
        pid = paragraph.get("id")
        expected = source_by_id.get(pid, "")
        where = f"paragraphs[{p_index}]"
        if expected and source_compare_text(paragraph.get("source_wenyan", "")) != source_compare_text(expected):
            errors.append(f"{pid}: source_wenyan changed")
        units = paragraph.get("units")
        if not isinstance(units, list) or not units:
            errors.append(f"{pid}: missing units")
            continue
        rebuilt = "".join(str(unit.get("source_wenyan", "")) for unit in units if isinstance(unit, dict))
        if expected and source_compare_text(rebuilt) != source_compare_text(expected):
            errors.append(f"{pid}: units do not reconstruct source wenyan")
        for u_index, unit in enumerate(units):
            uwhere = f"{where}.units[{u_index}]"
            if not isinstance(unit, dict):
                errors.append(f"{uwhere}: must be object")
                continue
            source_wenyan = str(unit.get("source_wenyan", ""))
            require_content = source_has_content(source_wenyan)
            validate_zh_like(unit.get("wenyan", []), f"{uwhere}.wenyan", errors, require_han=require_content)
            validate_zh_like(unit.get("zh_modern", []), f"{uwhere}.zh_modern", errors, require_han=require_content)
            validate_ja(unit.get("ja_modern", []), f"{uwhere}.ja_modern", errors, require_japanese=require_content)
            validate_en(unit.get("en", []), f"{uwhere}.en", errors, require_latin=require_content)
            if no_space(token_text(unit.get("wenyan", []))) != no_space(source_wenyan):
                errors.append(f"{uwhere}: wenyan tokens do not reconstruct source_wenyan")
    return errors


def validate_book(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("mode") != "quadrilingual_wenyan_main":
        errors.append("mode must be quadrilingual_wenyan_main")
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return errors + ["chapters must be a non-empty list"]
    for c_index, chapter in enumerate(chapters):
        for p_index, paragraph in enumerate(chapter.get("paragraphs", [])):
            for u_index, unit in enumerate(paragraph.get("units", [])):
                where = f"chapters[{c_index}].paragraphs[{p_index}].units[{u_index}]"
                source_wenyan = str(unit.get("source_wenyan", ""))
                require_content = source_has_content(source_wenyan)
                validate_zh_like(unit.get("wenyan", []), f"{where}.wenyan", errors, require_han=require_content)
                validate_zh_like(unit.get("zh_modern", []), f"{where}.zh_modern", errors, require_han=require_content)
                validate_ja(unit.get("ja_modern", []), f"{where}.ja_modern", errors, require_japanese=require_content)
                validate_en(unit.get("en", []), f"{where}.en", errors, require_latin=require_content)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path")
    args = parser.parse_args()
    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    errors = validate_book(data)
    if errors:
        for error in errors[:120]:
            print(error)
        raise SystemExit(1)
    print(f"ok: {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
