#!/usr/bin/env python3
"""Filter assembled interlinear JSON before rendering."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any


NOTE_PREFIX_RE = re.compile(
    r"""^\s*(?:
        [\[［〔【(（]\s*(?:注|註)?\s*[0-9０-９]+\s*[\]］〕】)）]
        |
        [\[［〔【(（]\s*注\s*[0-9０-９]*\s*[\]］〕】)）]
        |
        (?:注|註|译注|譯注|注释|註釋|訳注|脚注|注釈|注記)\s*(?:[0-9０-９]+)?\s*[:：\[]?
    )""",
    re.VERBOSE,
)
MARKDOWN_NOTE_LINK_RE = re.compile(
    r"""(?:
        \[\s*\\?\[\s*(?:注|註)?\s*[0-9０-９]{1,4}\s*\\?\]\s*\]\s*\([^)]+(?:\.html|\#)[^)]+\)
        |
        \[\s*(?:注|註)?\s*[0-9０-９]{1,4}\s*\]\s*\([^)]+(?:\.html|\#)[^)]+\)
    )""",
    re.VERBOSE,
)
EMPTY_MARKDOWN_NOTE_LINK_RE = re.compile(
    r"""(?:
        \[\s*\\?\[\s*(?:注|註)?\s*[0-9０-９]{1,4}\s*\\?\]\s*\]\s*\(\s*\)
        |
        \[\s*(?:注|註)?\s*[0-9０-９]{1,4}\s*\]\s*\(\s*\)
    )""",
    re.VERBOSE,
)
INLINE_NOTE_REF_RE = re.compile(
    r"[\[［〔【]\s*\\?\[?\s*(?:注|註)?\s*[0-9０-９]{1,4}\s*\\?\]?\s*[\]］〕】]"
)
HTML_NOTE_TARGET_RE = re.compile(r"\(?#?part[0-9]+\.html#[A-Za-z]?[0-9]+\)?")
CIRCLED_NOTE_CHARS = "\u2460-\u2473"
CIRCLED_NOTE_RE = re.compile(f"[{CIRCLED_NOTE_CHARS}]")
PAREN_NOTE_REF_RE = re.compile(
    rf"[（(][^（）()]{{0,80}}(?:注|註|译注|譯注|訳注|脚注|注釈|注記)"
    rf"[^（）()]{{0,30}}[{CIRCLED_NOTE_CHARS}][^（）()]{{0,30}}[）)]"
)
PAREN_ORPHAN_NOTE_REF_RE = re.compile(
    r"[（(][^（）()]{0,80}(?:参看|參看|参考|參考|参照|參照|见|見)"
    r"[^（）()]{0,50}(?:注|註|译注|譯注|訳注|脚注|注釈|注記)\s*[）)]"
)
NOTE_REF_PHRASE_RE = re.compile(
    rf"(?:参看|參看|参考|參考|参照|參照|见|見)\s*"
    rf"(?:第?[一二三四五六七八九十百千万〇零两0-9０-９]+(?:页|頁|ページ))?\s*"
    rf"(?:注|註|译注|譯注|訳注|脚注|注釈|注記)?\s*[{CIRCLED_NOTE_CHARS}]+[。．、，,；;]?"
)
ORPHAN_NOTE_REF_PHRASE_RE = re.compile(
    r"(?:参看|參看|参考|參考|参照|參照|见|見)\s*"
    r"(?:第?[一二三四五六七八九十百千万〇零两0-9０-９]+(?:页|頁|ページ))?\s*"
    r"(?:注|註|译注|譯注|訳注|脚注|注釈|注記)\s*[。．、，,；;]?"
)
SHORT_SEE_NOTE_RE = re.compile(
    rf"^\s*.{{0,8}}(?:参看|參看|参考|參考|参照|參照|见|見)\s*"
    rf"(?:第?[一二三四五六七八九十百千万〇零两0-9０-９]+(?:页|頁|ページ))?\s*"
    rf"(?:注|註|译注|譯注|訳注|脚注|注釈|注記)?\s*[{CIRCLED_NOTE_CHARS}]+[。．、，,；;]?\s*$"
)
DIGIT_TOKEN_RE = re.compile(r"^[0-9０-９]+$")
NOTE_WORDS = {"注", "註", "訳注", "脚注", "注釈", "注記"}
NOTE_REF_START_WORDS = {"参看", "參看", "参考", "參考", "参照", "參照", "见", "見", "注", "註", "訳注", "脚注"}
OPEN_BRACKETS = {"[", "［", "〔", "【", "(", "（"}
CLOSE_BRACKETS = {"]", "］", "〕", "】", ")", "）"}
PHRASE_ENDINGS = {"。", "．", "、", "，", ",", "；", ";", ")", "）"}


def plain_tokens(tokens: list[dict[str, Any]]) -> str:
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def plain_title(item: dict[str, Any], key: str) -> str:
    value = item.get(key, [])
    if isinstance(value, list):
        return plain_tokens(value)
    return str(value)


def strip_text_note_refs(text: str) -> str:
    cleaned = MARKDOWN_NOTE_LINK_RE.sub("", str(text))
    cleaned = EMPTY_MARKDOWN_NOTE_LINK_RE.sub("", cleaned)
    cleaned = HTML_NOTE_TARGET_RE.sub("", cleaned)
    cleaned = PAREN_NOTE_REF_RE.sub("", cleaned)
    cleaned = PAREN_ORPHAN_NOTE_REF_RE.sub("", cleaned)
    cleaned = NOTE_REF_PHRASE_RE.sub("", cleaned)
    cleaned = ORPHAN_NOTE_REF_PHRASE_RE.sub("", cleaned)
    cleaned = INLINE_NOTE_REF_RE.sub("", cleaned)
    cleaned = CIRCLED_NOTE_RE.sub("", cleaned)
    return cleaned


def unit_text(unit: dict[str, Any], lang: str) -> str:
    if lang == "zh":
        value = unit.get("zh", [])
        return plain_tokens(value) if isinstance(value, list) else ""
    lines = unit.get("ja", [])
    if not isinstance(lines, list):
        return ""
    return "".join(plain_tokens(line) for line in lines if isinstance(line, list))


def is_note_unit(unit: dict[str, Any]) -> bool:
    zh = unit_text(unit, "zh").strip()
    ja = unit_text(unit, "ja").strip()
    source_text = str(unit.get("source_text", ""))
    corrected_text = str(unit.get("corrected_text", ""))
    cleaned_source = strip_text_note_refs(source_text).strip()
    cleaned_corrected = strip_text_note_refs(corrected_text).strip()
    source_was_only_note = bool(source_text.strip()) and not cleaned_source
    corrected_was_only_note = bool(corrected_text.strip()) and not cleaned_corrected
    return bool(
        NOTE_PREFIX_RE.match(zh)
        or NOTE_PREFIX_RE.match(ja)
        or NOTE_PREFIX_RE.match(source_text.strip())
        or NOTE_PREFIX_RE.match(corrected_text.strip())
        or SHORT_SEE_NOTE_RE.match(zh)
        or SHORT_SEE_NOTE_RE.match(ja)
        or SHORT_SEE_NOTE_RE.match(source_text.strip())
        or SHORT_SEE_NOTE_RE.match(corrected_text.strip())
        or (not zh and (source_was_only_note or corrected_was_only_note))
        or (not zh and "注" in ja and "参照" in ja)
    )


def strip_inline_note_refs_from_tokens(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for token in tokens:
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", ""))
        stripped = strip_text_note_refs(text)
        if not stripped:
            continue
        new_token = copy.deepcopy(token)
        new_token["t"] = stripped
        normalized.append(new_token)

    cleaned: list[dict[str, Any]] = []
    index = 0
    while index < len(normalized):
        token_text = str(normalized[index].get("t", "")).strip()
        if token_text in OPEN_BRACKETS:
            joined = ""
            end_index = index
            while end_index < len(normalized) and len(joined) < 220:
                joined += str(normalized[end_index].get("t", ""))
                end_index += 1
                if ")" in joined or "）" in joined:
                    break
            if PAREN_NOTE_REF_RE.match(joined) or PAREN_ORPHAN_NOTE_REF_RE.match(joined):
                if cleaned and not str(cleaned[-1].get("t", "")).strip():
                    cleaned.pop()
                index = end_index
                while index < len(normalized) and not str(normalized[index].get("t", "")).strip():
                    index += 1
                continue
            match = MARKDOWN_NOTE_LINK_RE.match(joined) or EMPTY_MARKDOWN_NOTE_LINK_RE.match(joined)
            if match:
                consumed = 0
                end_index = index
                while end_index < len(normalized) and consumed < match.end():
                    consumed += len(str(normalized[end_index].get("t", "")))
                    end_index += 1
                if cleaned and not str(cleaned[-1].get("t", "")).strip():
                    cleaned.pop()
                index = end_index
                while index < len(normalized) and not str(normalized[index].get("t", "")).strip():
                    index += 1
                continue
        if token_text in OPEN_BRACKETS:
            end_index = index + 1
            if end_index < len(normalized) and str(normalized[end_index].get("t", "")).strip() in OPEN_BRACKETS:
                end_index += 1
            if end_index < len(normalized) and str(normalized[end_index].get("t", "")).strip() in NOTE_WORDS:
                end_index += 1
            digit_seen = False
            while end_index < len(normalized) and DIGIT_TOKEN_RE.match(str(normalized[end_index].get("t", "")).strip()):
                digit_seen = True
                end_index += 1
            if digit_seen and end_index < len(normalized) and str(normalized[end_index].get("t", "")).strip() in CLOSE_BRACKETS:
                end_index += 1
                if end_index < len(normalized) and str(normalized[end_index].get("t", "")).strip() in CLOSE_BRACKETS:
                    end_index += 1
                if cleaned and not str(cleaned[-1].get("t", "")).strip():
                    cleaned.pop()
                index = end_index
                while index < len(normalized) and not str(normalized[index].get("t", "")).strip():
                    index += 1
                continue
        if token_text in NOTE_REF_START_WORDS:
            joined = ""
            end_index = index
            while end_index < len(normalized) and len(joined) < 120:
                joined += str(normalized[end_index].get("t", ""))
                end_index += 1
                if any(ending in joined for ending in PHRASE_ENDINGS):
                    break
            if NOTE_REF_PHRASE_RE.match(joined) or ORPHAN_NOTE_REF_PHRASE_RE.match(joined) or (
                CIRCLED_NOTE_RE.search(joined) and "注" in joined and ("参照" in joined or "参考" in joined)
            ):
                if cleaned and not str(cleaned[-1].get("t", "")).strip():
                    cleaned.pop()
                index = end_index
                while index < len(normalized) and not str(normalized[index].get("t", "")).strip():
                    index += 1
                continue
        cleaned.append(normalized[index])
        index += 1
    return cleaned


def strip_inline_note_refs_from_named_tokens(node: dict[str, Any]) -> None:
    for key in ("title_zh", "title_ja", "place_zh", "place_ja"):
        tokens = node.get(key)
        if isinstance(tokens, list):
            node[key] = strip_inline_note_refs_from_tokens(tokens)


def strip_inline_note_refs(unit: dict[str, Any]) -> dict[str, Any]:
    unit = copy.deepcopy(unit)
    for key in ("source_text", "corrected_text"):
        if key in unit and isinstance(unit[key], str):
            unit[key] = strip_text_note_refs(unit[key])
    zh = unit.get("zh", [])
    if isinstance(zh, list):
        unit["zh"] = strip_inline_note_refs_from_tokens(zh)
        rendered_zh = plain_tokens(unit["zh"])
        if rendered_zh:
            unit["source_text"] = rendered_zh
            unit["corrected_text"] = rendered_zh
    ja_lines = unit.get("ja", [])
    if isinstance(ja_lines, list):
        cleaned_lines = []
        for line in ja_lines:
            if not isinstance(line, list):
                continue
            cleaned_lines.append(strip_inline_note_refs_from_tokens(line))
        while len(cleaned_lines) < 2:
            cleaned_lines.append([])
        if len(cleaned_lines) > 2:
            cleaned_lines = cleaned_lines[:2]
        unit["ja"] = cleaned_lines
    return unit


def filter_story(story: dict[str, Any], *, drop_editorial_notes: bool) -> dict[str, Any] | None:
    story = copy.deepcopy(story)
    paragraphs: list[dict[str, Any]] = []
    for paragraph in story.get("paragraphs", []):
        units = paragraph.get("units", [])
        if not isinstance(units, list):
            continue
        if drop_editorial_notes:
            filtered_units = []
            for unit in units:
                if not isinstance(unit, dict) or is_note_unit(unit):
                    continue
                cleaned_unit = strip_inline_note_refs(unit)
                if is_note_unit(cleaned_unit):
                    continue
                if unit_text(cleaned_unit, "zh").strip() or unit_text(cleaned_unit, "ja").strip():
                    filtered_units.append(cleaned_unit)
            units = filtered_units
        if not units:
            continue
        new_paragraph = copy.deepcopy(paragraph)
        new_paragraph["units"] = units
        rendered_source = "".join(unit_text(unit, "zh") for unit in units if isinstance(unit, dict))
        if rendered_source:
            new_paragraph["source_text"] = rendered_source
            new_paragraph["corrected_text"] = rendered_source
        paragraphs.append(new_paragraph)
    story["paragraphs"] = paragraphs
    return story if paragraphs else None


def filter_data(
    data: dict[str, Any],
    *,
    include_section_title_zh: set[str],
    drop_editorial_notes: bool,
) -> dict[str, Any]:
    data = copy.deepcopy(data)
    sections: list[dict[str, Any]] = []
    for section in data.get("sections", []):
        if include_section_title_zh and plain_title(section, "title_zh") not in include_section_title_zh:
            continue
        section = copy.deepcopy(section)
        if drop_editorial_notes:
            strip_inline_note_refs_from_named_tokens(section)
        subsections: list[dict[str, Any]] = []
        for subsection in section.get("subsections", []):
            subsection = copy.deepcopy(subsection)
            if drop_editorial_notes:
                strip_inline_note_refs_from_named_tokens(subsection)
            stories: list[dict[str, Any]] = []
            for story in subsection.get("stories", []):
                if drop_editorial_notes:
                    strip_inline_note_refs_from_named_tokens(story)
                filtered = filter_story(story, drop_editorial_notes=drop_editorial_notes)
                if filtered is not None:
                    stories.append(filtered)
            subsection["stories"] = stories
            if stories:
                subsections.append(subsection)
        section["subsections"] = subsections
        if subsections:
            sections.append(section)
    data["sections"] = sections
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="assembled interlinear JSON source")
    parser.add_argument("-o", "--output", required=True, help="filtered JSON output path")
    parser.add_argument("--include-section-title-zh", action="append", default=[], help="keep only this Chinese section title")
    parser.add_argument("--drop-editorial-notes", action="store_true", help="drop note-only units such as [1]... or 注：...")
    args = parser.parse_args(argv)

    source = Path(args.source)
    data = json.loads(source.read_text(encoding="utf-8"))
    filtered = filter_data(
        data,
        include_section_title_zh={title.strip() for title in args.include_section_title_zh if title.strip()},
        drop_editorial_notes=args.drop_editorial_notes,
    )
    if not filtered.get("sections"):
        print("filter produced no renderable sections", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(filtered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
