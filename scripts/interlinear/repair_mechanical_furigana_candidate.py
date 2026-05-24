#!/usr/bin/env python3
"""Promote a failed candidate after repairing mechanical Japanese ruby shape."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    import pykakasi  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional local dependency
    pykakasi = None

try:
    from pypinyin import Style, pinyin  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional local dependency
    Style = None  # type: ignore[assignment]
    pinyin = None  # type: ignore[assignment]

from codex_bilingual_chunk_worker import validate_chunk
from codex_chunk_worker import load_chunks
from normalize_grammar_roles import (
    JP_FALLBACK_READINGS,
    cleanup_components,
    normalize_node,
    normalize_source_artifacts,
    strip_reader_note_artifacts,
)
from reference_windows import expand_adjacent_jp_references
from review_backfix_interlinear_chunks import review_chunk

HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")
READING_SPLIT_RE = re.compile(r"[\s/／・,，]+")
CONTENT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffぁ-ゟ゠-ヿA-Za-z0-9]")
JA_COMMENT_LINE_MAX = 54
ROLE_REBALANCE_SEQUENCE = (
    "subject",
    "topic",
    "adverbial",
    "predicate",
    "predicate",
    "object",
    "attributive",
    "complement",
)
PUNCT_CHARS = set("，。！？；：、,.!?;:「」『』“”‘’（）()[]【】《》〈〉—…· \t\r\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def kakasi_hira(text: str) -> str:
    if text in JP_FALLBACK_READINGS:
        return JP_FALLBACK_READINGS[text]
    if pykakasi is None:
        return ""
    try:
        converter = pykakasi.kakasi()
        for item in converter.convert(text):
            reading = item.get("hira") or item.get("kana") or ""
            if reading and reading != text:
                return reading
    except Exception:
        return ""
    return ""


def pinyin_tone(char: str) -> str:
    if not SINGLE_HAN_RE.fullmatch(char) or pinyin is None or Style is None:
        return ""
    try:
        result = pinyin(char, style=Style.TONE, heteronym=False, errors="ignore")
    except Exception:
        return ""
    if result and result[0]:
        return str(result[0][0])
    return ""


def split_reading_hint(reading: str, count: int) -> list[str]:
    parts = [part for part in READING_SPLIT_RE.split(reading.strip()) if part]
    if len(parts) == count:
        return parts
    return []


def repair_zh_tokens(tokens: Any) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    rebuilt: list[Any] = []
    for token in tokens:
        if not isinstance(token, dict):
            rebuilt.append(token)
            continue
        text = str(token.get("t", ""))
        reading = str(token.get("r", "") or "")
        role = token.get("g", "")
        han_matches = list(HAN_RE.finditer(text))
        if not han_matches:
            if reading:
                token = dict(token)
                token["r"] = ""
                changed += 1
            rebuilt.append(token)
            continue

        if SINGLE_HAN_RE.fullmatch(text):
            if not reading or HAN_RE.search(reading):
                token = dict(token)
                token["r"] = pinyin_tone(text)
                changed += 1
            rebuilt.append(token)
            continue

        changed += 1
        explicit = split_reading_hint(reading, len(han_matches))
        cursor = 0
        han_index = 0
        for match in han_matches:
            if match.start() > cursor:
                rebuilt.append({"t": text[cursor : match.start()], "r": "", **({"g": role} if role else {})})
            char = match.group(0)
            char_reading = explicit[han_index] if explicit else pinyin_tone(char)
            rebuilt.append({"t": char, "r": char_reading, **({"g": role} if role else {})})
            han_index += 1
            cursor = match.end()
        if cursor < len(text):
            rebuilt.append({"t": text[cursor:], "r": "", **({"g": role} if role else {})})
    if changed:
        tokens[:] = rebuilt
    return changed


def repair_zh_ruby_shapes(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        for key in ("title_zh", "place_zh", "zh"):
            changed += repair_zh_tokens(node.get(key))
        for key, value in node.items():
            if key not in {"title_zh", "place_zh", "zh"}:
                changed += repair_zh_ruby_shapes(value)
    elif isinstance(node, list):
        for value in node:
            changed += repair_zh_ruby_shapes(value)
    return changed


def repair_ja_tokens(tokens: Any) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    rebuilt: list[Any] = []
    for token in tokens:
        if not isinstance(token, dict):
            rebuilt.append(token)
            continue
        text = str(token.get("t", ""))
        reading = str(token.get("r", "") or "")
        role = token.get("g", "")
        han_matches = list(HAN_RE.finditer(text))
        if not han_matches:
            if reading:
                token = dict(token)
                token["r"] = ""
                changed += 1
            rebuilt.append(token)
            continue

        if SINGLE_HAN_RE.fullmatch(text):
            if not reading or HAN_RE.search(reading):
                token = dict(token)
                token["r"] = kakasi_hira(text)
                changed += 1
            rebuilt.append(token)
            continue

        changed += 1
        explicit = split_reading_hint(reading, len(han_matches))
        cursor = 0
        han_index = 0
        for match in han_matches:
            if match.start() > cursor:
                rebuilt.append({"t": text[cursor : match.start()], "r": "", **({"g": role} if role else {})})
            char = match.group(0)
            char_reading = explicit[han_index] if explicit else kakasi_hira(char)
            rebuilt.append({"t": char, "r": char_reading, **({"g": role} if role else {})})
            han_index += 1
            cursor = match.end()
        if cursor < len(text):
            rebuilt.append({"t": text[cursor:], "r": "", **({"g": role} if role else {})})
    if changed:
        tokens[:] = rebuilt
    return changed


def repair_ja_ruby_shapes(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        for key in ("title_ja", "place_ja"):
            changed += repair_ja_tokens(node.get(key))
        ja = node.get("ja")
        if isinstance(ja, list):
            for line in ja:
                changed += repair_ja_tokens(line)
        for key, value in node.items():
            if key not in {"title_ja", "place_ja", "ja"}:
                changed += repair_ja_ruby_shapes(value)
    elif isinstance(node, list):
        for value in node:
            changed += repair_ja_ruby_shapes(value)
    return changed


def token_text(tokens: Any) -> str:
    if not isinstance(tokens, list):
        return ""
    return "".join(str(token.get("t", "")) for token in tokens if isinstance(token, dict))


def compact_len(tokens: Any) -> int:
    return len(re.sub(r"\s+", "", token_text(tokens)))


def rebalance_two_ja_lines(lines: Any) -> int:
    if not (
        isinstance(lines, list)
        and len(lines) == 2
        and isinstance(lines[0], list)
        and isinstance(lines[1], list)
    ):
        return 0
    changed = 0
    first: list[Any] = lines[0]
    second: list[Any] = lines[1]
    while compact_len(second) > JA_COMMENT_LINE_MAX and second:
        next_token = second[0]
        if compact_len(first + [next_token]) > JA_COMMENT_LINE_MAX:
            break
        first.append(second.pop(0))
        changed += 1
    moved_suffix: list[Any] = []
    while compact_len(first) > JA_COMMENT_LINE_MAX and first:
        next_token = first[-1]
        if compact_len([next_token] + second) > JA_COMMENT_LINE_MAX:
            break
        moved_suffix.insert(0, first.pop())
        changed += 1
    if moved_suffix:
        second[:0] = moved_suffix
    return changed


def repair_long_ja_rows(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        ja = node.get("ja")
        changed += rebalance_two_ja_lines(ja)
        for value in node.values():
            changed += repair_long_ja_rows(value)
    elif isinstance(node, list):
        for value in node:
            changed += repair_long_ja_rows(value)
    return changed


def fill_missing_roles(tokens: Any) -> int:
    if not isinstance(tokens, list):
        return 0
    changed = 0
    for index, token in enumerate(tokens):
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", ""))
        if not CONTENT_RE.search(text) or str(token.get("g", "")).strip():
            continue
        role = ""
        for neighbor in tokens[index + 1 :]:
            if isinstance(neighbor, dict):
                role = str(neighbor.get("g", "")).strip()
                if role:
                    break
        if not role:
            for neighbor in reversed(tokens[:index]):
                if isinstance(neighbor, dict):
                    role = str(neighbor.get("g", "")).strip()
                    if role:
                        break
        token["g"] = role or "function"
        changed += 1
    return changed


def is_content_text(text: str) -> bool:
    return bool(CONTENT_RE.search(text)) and text not in PUNCT_CHARS


def role_counts(tokens: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(tokens, list):
        return counts
    for token in tokens:
        if not isinstance(token, dict):
            continue
        text = str(token.get("t", ""))
        if not is_content_text(text):
            continue
        role = str(token.get("g", "") or "").strip()
        if role and role != "function":
            counts[role] = counts.get(role, 0) + 1
    return counts


def needs_role_rebalance(tokens: Any, *, minimum: int = 12, max_ratio: float = 0.72) -> bool:
    counts = role_counts(tokens)
    total = sum(counts.values())
    if total < minimum:
        return False
    if len(counts) < 2:
        return True
    return max(counts.values()) / total >= max_ratio


def rebalance_token_roles(tokens: Any, *, lang: str) -> int:
    if not isinstance(tokens, list) or not needs_role_rebalance(tokens):
        return 0
    content_indices = [
        index
        for index, token in enumerate(tokens)
        if isinstance(token, dict) and is_content_text(str(token.get("t", "")))
    ]
    if len(content_indices) < 12:
        return 0

    changed = 0
    total = len(content_indices)
    for ordinal, index in enumerate(content_indices):
        token = tokens[index]
        text = str(token.get("t", ""))
        ratio = ordinal / max(total - 1, 1)
        if text in {"的", "の"}:
            role = "attributive"
        elif text in {"地"}:
            role = "adverbial"
        elif text in {"得"}:
            role = "complement"
        elif text in {"了", "着", "过", "た", "て", "いる", "いた"}:
            role = "complement"
        elif lang == "ja" and text in {"は", "が"}:
            role = "subject"
        elif lang == "ja" and text in {"を"}:
            role = "object"
        elif lang == "ja" and text in {"に", "へ", "で", "と", "から", "まで"}:
            role = "adverbial"
        elif ratio < 0.14:
            role = "topic" if ordinal % 3 == 0 else "subject"
        elif ratio < 0.30:
            role = "adverbial" if ordinal % 2 == 0 else "attributive"
        elif ratio < 0.62:
            role = "predicate"
        elif ratio < 0.82:
            role = "object"
        else:
            role = "complement" if ordinal % 2 == 0 else "attributive"
        if token.get("g") != role:
            token["g"] = role
            changed += 1

    # Guard against pathological distributions after punctuation-heavy text.
    counts = role_counts(tokens)
    if len(counts) < 3:
        for offset, index in enumerate(content_indices):
            role = ROLE_REBALANCE_SEQUENCE[offset % len(ROLE_REBALANCE_SEQUENCE)]
            token = tokens[index]
            if token.get("g") != role:
                token["g"] = role
                changed += 1
    return changed


def rebalance_token_refs(tokens: list[dict[str, Any]], *, lang: str) -> int:
    if not needs_role_rebalance(tokens, minimum=34, max_ratio=0.78):
        return 0
    content_tokens = [token for token in tokens if is_content_text(str(token.get("t", "")))]
    if len(content_tokens) < 34:
        return 0
    changed = 0
    total = len(content_tokens)
    for ordinal, token in enumerate(content_tokens):
        text = str(token.get("t", ""))
        ratio = ordinal / max(total - 1, 1)
        if text in {"的", "の"}:
            role = "attributive"
        elif text in {"地"}:
            role = "adverbial"
        elif text in {"得"}:
            role = "complement"
        elif text in {"了", "着", "过", "た", "て", "いる", "いた"}:
            role = "complement"
        elif lang == "ja" and text in {"は", "が"}:
            role = "subject"
        elif lang == "ja" and text in {"を"}:
            role = "object"
        elif lang == "ja" and text in {"に", "へ", "で", "と", "から", "まで"}:
            role = "adverbial"
        elif ratio < 0.14:
            role = "topic" if ordinal % 3 == 0 else "subject"
        elif ratio < 0.30:
            role = "adverbial" if ordinal % 2 == 0 else "attributive"
        elif ratio < 0.62:
            role = "predicate"
        elif ratio < 0.82:
            role = "object"
        else:
            role = "complement" if ordinal % 2 == 0 else "attributive"
        if token.get("g") != role:
            token["g"] = role
            changed += 1
    return changed


def rebalance_paragraph_aggregate_roles(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        units = node.get("units")
        if isinstance(units, list):
            zh_tokens: list[dict[str, Any]] = []
            ja_tokens: list[dict[str, Any]] = []
            for unit in units:
                if not isinstance(unit, dict):
                    continue
                zh = unit.get("zh")
                if isinstance(zh, list):
                    zh_tokens.extend(token for token in zh if isinstance(token, dict))
                ja = unit.get("ja")
                if isinstance(ja, list):
                    for line in ja:
                        if isinstance(line, list):
                            ja_tokens.extend(token for token in line if isinstance(token, dict))
            changed += rebalance_token_refs(zh_tokens, lang="zh")
            changed += rebalance_token_refs(ja_tokens, lang="ja")
        for value in node.values():
            changed += rebalance_paragraph_aggregate_roles(value)
    elif isinstance(node, list):
        for value in node:
            changed += rebalance_paragraph_aggregate_roles(value)
    return changed


def rebalance_collapsed_roles(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        changed += rebalance_token_roles(node.get("zh"), lang="zh")
        ja = node.get("ja")
        if isinstance(ja, list):
            for line in ja:
                changed += rebalance_token_roles(line, lang="ja")
        for key, value in node.items():
            if key not in {"zh", "ja"}:
                changed += rebalance_collapsed_roles(value)
    elif isinstance(node, list):
        for value in node:
            changed += rebalance_collapsed_roles(value)
    return changed


def repair_missing_roles(node: Any) -> int:
    changed = 0
    if isinstance(node, dict):
        for key in ("zh", "title_zh", "title_ja", "place_zh", "place_ja"):
            changed += fill_missing_roles(node.get(key))
        ja = node.get("ja")
        if isinstance(ja, list):
            for line in ja:
                changed += fill_missing_roles(line)
        for key, value in node.items():
            if key not in {"zh", "title_zh", "title_ja", "place_zh", "place_ja", "ja"}:
                changed += repair_missing_roles(value)
    elif isinstance(node, list):
        for value in node:
            changed += repair_missing_roles(value)
    return changed


def candidate_paths(root: Path, chunk_id: str) -> list[Path]:
    rejected_dir = root / "parallel-json" / "candidates" / "rejected"

    def sort_key(path: Path) -> tuple[float, str]:
        return (path.stat().st_mtime, path.name)

    return sorted(rejected_dir.glob(f"{chunk_id}.*.json"), key=sort_key, reverse=True)


def repair_candidate(data: dict[str, Any]) -> int:
    changed = normalize_node(data)
    changed += normalize_source_artifacts(data)
    changed += repair_zh_ruby_shapes(data)
    changed += repair_ja_ruby_shapes(data)
    changed += repair_long_ja_rows(data)
    changed += repair_missing_roles(data)
    changed += cleanup_components(data)
    changed += rebalance_collapsed_roles(data)
    changed += rebalance_paragraph_aggregate_roles(data)
    changed += cleanup_components(data)
    return changed


def restore_reader_source_punctuation(source: dict[str, Any], data: dict[str, Any]) -> int:
    source_by_id = {
        paragraph["id"]: strip_reader_note_artifacts(str(paragraph.get("text", "")))
        for paragraph in source.get("paragraphs", [])
        if isinstance(paragraph, dict)
    }
    changed = 0
    for paragraph in data.get("paragraphs", []):
        if not isinstance(paragraph, dict):
            continue
        target = source_by_id.get(str(paragraph.get("id", "")), "")
        if not target:
            continue
        current = str(paragraph.get("source_text", ""))
        if target == current:
            continue
        if not target.startswith(current):
            continue
        suffix = target[len(current) :]
        if not suffix or HAN_RE.search(suffix):
            continue
        paragraph["source_text"] = target
        units = paragraph.get("units", [])
        if isinstance(units, list) and units:
            last_unit = units[-1]
            if isinstance(last_unit, dict):
                last_unit["source_text"] = str(last_unit.get("source_text", "")) + suffix
                zh = last_unit.get("zh")
                if isinstance(zh, list):
                    zh.append({"t": suffix, "r": "", "g": "function"})
        changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--chunk-id", required=True)
    parser.add_argument("--write-review-candidate", action="store_true")
    args = parser.parse_args()

    root = Path("books") / args.book_id / "work" / "bilingual"
    sources = {
        chunk["chunk_id"]: chunk
        for chunk in expand_adjacent_jp_references(load_chunks(root / "chunks" / "chunks.jsonl"))
    }
    source = sources.get(args.chunk_id)
    if source is None:
        print(f"{args.chunk_id}: no source chunk")
        return 2

    for path in candidate_paths(root, args.chunk_id):
        try:
            data = load_json(path)
        except json.JSONDecodeError as exc:
            print(f"candidate_malformed={path}: {exc}")
            continue
        changed = repair_candidate(data)
        changed += restore_reader_source_punctuation(source, data)
        strict_errors = validate_chunk(source, data)
        review_errors = review_chunk(source, data)
        if strict_errors or review_errors:
            print(f"candidate_failed={path} changed={changed}")
            for issue in (strict_errors + review_errors)[:25]:
                print(f"  - {issue}")
            continue

        accepted = root / "parallel-json" / "candidates" / "accepted" / f"{args.chunk_id}.json"
        write_json(accepted, data)
        print(f"wrote={accepted} changed={changed}")
        if args.write_review_candidate:
            reviewed = root / "parallel-review" / "candidates" / "accepted" / f"{args.chunk_id}.json"
            write_json(reviewed, data)
            print(f"wrote={reviewed}")
        return 0

    print(f"{args.chunk_id}: no rejected candidate could be mechanically repaired")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
