#!/usr/bin/env python3
"""Normalize token grammar roles to the English component vocabulary."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")
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
DIGIT_TOKEN_RE = re.compile(r"^[0-9０-９]+$")
SHORT_NOTE_DIGIT_TOKEN_RE = re.compile(r"^[0-9０-９]{1,2}$")
NOTE_WORDS = {"注", "註", "訳注", "脚注", "注釈", "注記"}
NOTE_REF_START_WORDS = {"参看", "參看", "参考", "參考", "参照", "參照", "见", "見", "注", "註", "訳注", "脚注"}
OPEN_BRACKETS = {"[", "［", "〔", "【", "(", "（"}
CLOSE_BRACKETS = {"]", "］", "〕", "】", ")", "）"}
PHRASE_ENDINGS = {"。", "．", "、", "，", ",", "；", ";", ")", "）"}

JP_FALLBACK_READINGS = {
    # Simplified Chinese glyphs sometimes appear inside quoted character names
    # in Japanese comments. They still need a single-token ruby reading.
    "妈": "ま",
    "马": "うま",
    "妇": "ふ",
}


ROLE_ALIASES = {
    "zhu": "subject",
    "subject": "subject",
    "wei": "predicate",
    "predicate": "predicate",
    "verb": "predicate",
    "bin": "object",
    "object": "object",
    "ding": "attributive",
    "attributive": "attributive",
    "zhuang": "adverbial",
    "adverbial": "adverbial",
    "bu": "complement",
    "complement": "complement",
    "topic": "topic",
    "function": "function",
    "particle": "function",
}

JP_COMPONENT_MARKERS = {
    "は",
    "が",
    "を",
    "に",
    "へ",
    "で",
    "と",
    "も",
    "の",
    "から",
    "まで",
    "より",
    "には",
    "では",
    "にも",
    "でも",
    "とは",
    "へは",
    "をも",
}
JP_ATTACHED_SUFFIXES = (
    "さんを",
    "さんが",
    "さんは",
    "だのに",
    "だの",
    "などを",
    "などに",
    "など",
    "を",
    "が",
    "は",
    "に",
    "へ",
    "で",
    "と",
    "も",
    "の",
    "から",
    "まで",
    "より",
    "には",
    "では",
    "にも",
    "でも",
    "とは",
    "へは",
    "をも",
)
ZH_COMPONENT_MARKERS = {"的", "地", "得"}
ZH_ASPECT_MARKERS = {"了", "着", "过"}


def strip_reader_note_artifacts(text: str) -> str:
    """Remove EPUB/PDF footnote reference debris from reader-facing text."""

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


def strip_reader_note_artifact_tokens(tokens: Any) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    normalized: list[Any] = []
    for token in tokens:
        if not isinstance(token, dict):
            normalized.append(token)
            continue
        text = str(token.get("t", ""))
        stripped = strip_reader_note_artifacts(text)
        if stripped != text:
            changed += 1
        if not stripped:
            changed += 1
            continue
        new_token = token
        if stripped != text:
            new_token = dict(token)
            new_token["t"] = stripped
        normalized.append(new_token)

    cleaned: list[Any] = []
    index = 0
    while index < len(normalized):
        token = normalized[index]
        token_text = str(token.get("t", "")).strip() if isinstance(token, dict) else ""
        if token_text in OPEN_BRACKETS:
            joined = ""
            end_index = index
            while end_index < len(normalized) and len(joined) < 220:
                next_text = str(normalized[end_index].get("t", "")) if isinstance(normalized[end_index], dict) else ""
                joined += next_text
                end_index += 1
                if ")" in joined or "）" in joined:
                    break
            if PAREN_NOTE_REF_RE.match(joined) or PAREN_ORPHAN_NOTE_REF_RE.match(joined):
                if cleaned and isinstance(cleaned[-1], dict) and not str(cleaned[-1].get("t", "")).strip():
                    cleaned.pop()
                index = end_index
                while index < len(normalized):
                    next_text = (
                        str(normalized[index].get("t", "")).strip()
                        if isinstance(normalized[index], dict)
                        else ""
                    )
                    if next_text:
                        break
                    index += 1
                changed += 1
                continue
            match = MARKDOWN_NOTE_LINK_RE.match(joined) or EMPTY_MARKDOWN_NOTE_LINK_RE.match(joined)
            if match:
                consumed = 0
                end_index = index
                while end_index < len(normalized) and consumed < match.end():
                    consumed += len(str(normalized[end_index].get("t", "")) if isinstance(normalized[end_index], dict) else "")
                    end_index += 1
                if cleaned and isinstance(cleaned[-1], dict) and not str(cleaned[-1].get("t", "")).strip():
                    cleaned.pop()
                index = end_index
                while index < len(normalized):
                    next_text = (
                        str(normalized[index].get("t", "")).strip()
                        if isinstance(normalized[index], dict)
                        else ""
                    )
                    if next_text:
                        break
                    index += 1
                changed += 1
                continue
        if token_text in OPEN_BRACKETS:
            end_index = index + 1
            if end_index < len(normalized):
                next_text = (
                    str(normalized[end_index].get("t", "")).strip()
                    if isinstance(normalized[end_index], dict)
                    else ""
                )
                if next_text in OPEN_BRACKETS:
                    end_index += 1
            if end_index < len(normalized):
                next_text = (
                    str(normalized[end_index].get("t", "")).strip()
                    if isinstance(normalized[end_index], dict)
                    else ""
                )
                if next_text in NOTE_WORDS:
                    end_index += 1
            digit_seen = False
            digit_text = ""
            while end_index < len(normalized):
                next_text = (
                    str(normalized[end_index].get("t", "")).strip()
                    if isinstance(normalized[end_index], dict)
                    else ""
                )
                if not DIGIT_TOKEN_RE.match(next_text):
                    break
                digit_seen = True
                digit_text += next_text
                end_index += 1
            if end_index < len(normalized):
                next_text = (
                    str(normalized[end_index].get("t", "")).strip()
                    if isinstance(normalized[end_index], dict)
                    else ""
                )
                # Standalone one/two digit parentheticals are usually note
                # anchors. Three/four digit parentheticals in Chinese/Japanese
                # texts are often historical year glosses, e.g. （1737） or
                # (1670), and must remain reader-facing text.
                if digit_seen and SHORT_NOTE_DIGIT_TOKEN_RE.fullmatch(digit_text) and next_text in CLOSE_BRACKETS:
                    end_index += 1
                    if end_index < len(normalized):
                        next_text = (
                            str(normalized[end_index].get("t", "")).strip()
                            if isinstance(normalized[end_index], dict)
                            else ""
                        )
                        if next_text in CLOSE_BRACKETS:
                            end_index += 1
                    if cleaned and isinstance(cleaned[-1], dict) and not str(cleaned[-1].get("t", "")).strip():
                        cleaned.pop()
                    index = end_index
                    while index < len(normalized):
                        next_text = (
                            str(normalized[index].get("t", "")).strip()
                            if isinstance(normalized[index], dict)
                            else ""
                        )
                        if next_text:
                            break
                        index += 1
                    changed += 1
                    continue
        if token_text in NOTE_REF_START_WORDS:
            joined = ""
            end_index = index
            while end_index < len(normalized) and len(joined) < 120:
                next_text = str(normalized[end_index].get("t", "")) if isinstance(normalized[end_index], dict) else ""
                joined += next_text
                end_index += 1
                if any(ending in joined for ending in PHRASE_ENDINGS):
                    break
            if NOTE_REF_PHRASE_RE.match(joined) or ORPHAN_NOTE_REF_PHRASE_RE.match(joined) or (
                CIRCLED_NOTE_RE.search(joined) and "注" in joined and ("参照" in joined or "参考" in joined)
            ):
                if cleaned and isinstance(cleaned[-1], dict) and not str(cleaned[-1].get("t", "")).strip():
                    cleaned.pop()
                index = end_index
                while index < len(normalized):
                    next_text = (
                        str(normalized[index].get("t", "")).strip()
                        if isinstance(normalized[index], dict)
                        else ""
                    )
                    if next_text:
                        break
                    index += 1
                changed += 1
                continue
        cleaned.append(token)
        index += 1
    if changed:
        tokens[:] = cleaned
    return changed


def normalize_source_artifacts(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        for key in ("source_text", "corrected_text"):
            if key in node and isinstance(node[key], str):
                cleaned = strip_reader_note_artifacts(node[key])
                if cleaned != node[key]:
                    node[key] = cleaned
                    changed += 1
        for key in ("title_zh", "title_ja", "place_zh", "place_ja", "zh"):
            changed += strip_reader_note_artifact_tokens(node.get(key))
        ja = node.get("ja")
        if isinstance(ja, list):
            for line in ja:
                changed += strip_reader_note_artifact_tokens(line)
        for key, value in node.items():
            if key not in {"source_text", "corrected_text", "title_zh", "title_ja", "place_zh", "place_ja", "zh", "ja"}:
                changed += normalize_source_artifacts(value)
    elif isinstance(node, list):
        for value in node:
            changed += normalize_source_artifacts(value)
    return changed


def normalize_role(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("role", "")
    role = str(value or "").strip().lower()
    return ROLE_ALIASES.get(role, role)


def normalize_node(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        if "g" in node:
            old = node["g"]
            new = normalize_role(old)
            if new != old:
                node["g"] = new
                changed += 1
        for legacy_key in ("role", "syntax"):
            if legacy_key in node:
                new = normalize_role(node.pop(legacy_key))
                if new and "g" not in node:
                    node["g"] = new
                changed += 1
        for value in node.values():
            changed += normalize_node(value)
    elif isinstance(node, list):
        for value in node:
            changed += normalize_node(value)
    return changed


def split_reading_token(token: dict[str, Any], *, lang: str) -> tuple[list[dict[str, Any]], int]:
    text = str(token.get("t", ""))
    reading = str(token.get("r", ""))
    role = token.get("g", "")
    if not reading:
        if lang == "ja" and HAN_RE.search(text) and not SINGLE_HAN_RE.fullmatch(text):
            parts: list[dict[str, Any]] = []
            cursor = 0
            for match in HAN_RE.finditer(text):
                if match.start() > cursor:
                    parts.append({"t": text[cursor : match.start()], "r": "", **({"g": role} if role else {})})
                char = match.group(0)
                parts.append({"t": char, "r": JP_FALLBACK_READINGS.get(char, ""), **({"g": role} if role else {})})
                cursor = match.end()
            if cursor < len(text):
                parts.append({"t": text[cursor:], "r": "", **({"g": role} if role else {})})
            return parts, 1
        return [token], 0
    han_matches = list(HAN_RE.finditer(text))
    if not han_matches:
        new_token = dict(token)
        new_token["r"] = ""
        return [new_token], 1
    if len(han_matches) == 1 and not SINGLE_HAN_RE.fullmatch(text):
        match = han_matches[0]
        parts: list[dict[str, Any]] = []
        prefix = text[: match.start()]
        suffix = text[match.end() :]
        if prefix:
            parts.append({"t": prefix, "r": "", **({"g": role} if role else {})})
        kanji = dict(token)
        kanji["t"] = match.group(0)
        parts.append(kanji)
        if suffix:
            parts.append({"t": suffix, "r": "", **({"g": role} if role else {})})
        return parts, 1
    if lang == "zh" and all(HAN_RE.fullmatch(char) for char in text):
        reading_parts = [part for part in reading.split() if part]
        if len(reading_parts) == len(text):
            role = token.get("g", "")
            return [
                {"t": char, "r": reading_parts[index], **({"g": role} if role else {})}
                for index, char in enumerate(text)
            ], 1
    return [token], 0


def normalize_ruby_token_list(tokens: Any, *, lang: str) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    rebuilt: list[Any] = []
    for token in tokens:
        if not isinstance(token, dict):
            rebuilt.append(token)
            continue
        split, token_changed = split_reading_token(token, lang=lang)
        rebuilt.extend(split)
        changed += token_changed
    if changed:
        tokens[:] = rebuilt
    return changed


def normalize_ruby_token_shapes(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        for key in ("title_zh", "place_zh", "zh"):
            if isinstance(node.get(key), list):
                changed += normalize_ruby_token_list(node[key], lang="zh")
        for key in ("title_ja", "place_ja"):
            if isinstance(node.get(key), list):
                changed += normalize_ruby_token_list(node[key], lang="ja")
        ja = node.get("ja")
        if isinstance(ja, list):
            for line in ja:
                changed += normalize_ruby_token_list(line, lang="ja")
        for key, value in node.items():
            if key not in {"title_zh", "place_zh", "zh", "title_ja", "place_ja", "ja"}:
                changed += normalize_ruby_token_shapes(value)
    elif isinstance(node, list):
        for value in node:
            changed += normalize_ruby_token_shapes(value)
    return changed


def cleanup_component_tokens(tokens: Any, *, lang: str) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    previous_role = ""
    markers = JP_COMPONENT_MARKERS if lang == "ja" else ZH_COMPONENT_MARKERS
    for token in tokens:
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", "")).strip()
        role = normalize_role(token.get("g", ""))
        is_attached_jp = lang == "ja" and any(text.endswith(suffix) for suffix in JP_ATTACHED_SUFFIXES)
        is_attached_zh = lang == "zh" and text in ZH_ASPECT_MARKERS and previous_role in {"predicate", "attributive"}
        if role == "function" and (text in markers or is_attached_jp or is_attached_zh) and previous_role and previous_role != "function":
            token["g"] = previous_role
            changed += 1
            role = previous_role
        if role and role != "function" and text:
            previous_role = role
    return changed


def promote_jp_list_objects(tokens: Any) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    for index, token in enumerate(tokens):
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", "")).strip()
        if "だの" not in text and "など" not in text:
            continue
        cursor = index - 1
        touched = False
        while cursor >= 0:
            previous = tokens[cursor]
            if not isinstance(previous, dict) or normalize_role(previous.get("g", "")) != "adverbial":
                break
            previous["g"] = "object"
            changed += 1
            touched = True
            cursor -= 1
        if touched and normalize_role(token.get("g", "")) != "object":
            token["g"] = "object"
            changed += 1
    return changed


def cleanup_unit_components(unit: dict[str, Any]) -> int:
    changed = 0
    if isinstance(unit.get("zh"), list):
        changed += cleanup_component_tokens(unit["zh"], lang="zh")
    ja = unit.get("ja")
    if isinstance(ja, list):
        for line in ja:
            changed += cleanup_component_tokens(line, lang="ja")
            changed += promote_jp_list_objects(line)
            changed += cleanup_component_tokens(line, lang="ja")
    return changed


def cleanup_components(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        if isinstance(node.get("zh"), list) or isinstance(node.get("ja"), list):
            changed += cleanup_unit_components(node)
        for key, value in node.items():
            if key not in {"zh", "ja"}:
                changed += cleanup_components(value)
    elif isinstance(node, list):
        for value in node:
            changed += cleanup_components(value)
    return changed


def iter_json_paths(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(child for child in path.rglob("*.json") if child.is_file()))
        elif path.is_file() and path.suffix == ".json":
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="JSON file or directory paths")
    parser.add_argument(
        "--sync-components",
        action="store_true",
        help="make attached particles/markers inherit the previous major component role",
    )
    args = parser.parse_args()

    changed_files = 0
    changed_roles = 0
    for path in iter_json_paths([Path(item) for item in args.paths]):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = normalize_node(data)
        changed += normalize_ruby_token_shapes(data)
        if args.sync_components:
            changed += cleanup_components(data)
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed_files += 1
            changed_roles += changed
            print(f"{path}: normalized {changed} roles")
    print(f"changed_files={changed_files} changed_roles={changed_roles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
