#!/usr/bin/env python3
"""Deterministic + dynamic AgInTi reviewer for interlinear chunks.

This reviewer is intentionally separate from the writer.  It first runs local
schema/render/quality checks, then sends the concrete issue list to DeepSeek
only when deterministic normalization cannot finish the repair.  A fix is
promoted only after the same checks pass again.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from aginti_write_chunks import (
    GRAMMAR_ROLES,
    HAN_RE,
    OpenAI,
    ROOT,
    SYSTEM_PROMPT as WRITE_SYSTEM_PROMPT,
    atomic_write_json,
    backfill_missing_roles,
    build_user_prompt as build_write_user_prompt,
    call_deepseek,
    compile_previews,
    has_han,
    is_renderer_chunk,
    is_single_han,
    load_json,
    load_status,
    normalize,
    promote_renderer_chunk,
    refresh_renderer_metadata,
    repair_json,
    save_computed_status,
    token_text,
    validate_chunk_output,
    validate_renderer_chunk,
    wrap_renderer_chunk,
)


CONTENT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffぁ-ゟ゠-ヿA-Za-z0-9]")
PUNCT_ONLY_RE = re.compile(r"^[\s，。！？、；：,.!?;:「」『』（）()《》〈〉“”‘’…—-]+$")
CLOSING_PUNCT = set("〉」』》）)]，。；：、！？,.!?;:")
OPENING_PUNCT = set("〈「『《（([")
MAX_DETERMINISTIC_SOURCE_EDITS = 8
COMMON_JA_KANBUN_READINGS = {
    "上": "じょう",
    "也": "なり",
    "之": "これ",
    "人": "ひと",
    "以": "い",
    "日": "にち",
    "者": "もの",
    "而": "しこう",
}
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_chunks(book_id: str) -> list[dict[str, Any]]:
    path = ROOT / "books" / book_id / "work" / "bilingual" / "chunks" / "chunks.jsonl"
    chunks: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def reviewed_dir_for(book_id: str, override: str = "") -> Path:
    if override:
        return ROOT / override
    plan_path = ROOT / "books" / book_id / "book-plan.json"
    if plan_path.exists():
        try:
            plan = load_json(plan_path)
            reviewed = plan.get("reviewed_chunk_dir")
            if reviewed:
                return ROOT / str(reviewed)
        except Exception:
            pass
    return ROOT / "books" / book_id / "work" / "bilingual" / "reviewed" / "chunks"


@contextmanager
def chunk_lock(lock_dir: Path, chunk_id: str):
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{chunk_id}.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def compact_from_renderer(data: dict[str, Any], chunk_id: str) -> dict[str, Any]:
    units: list[dict[str, Any]] = []
    paragraphs = data.get("paragraphs")
    if isinstance(paragraphs, list):
        for paragraph in paragraphs:
            paragraph_units = paragraph.get("units") if isinstance(paragraph, dict) else None
            if isinstance(paragraph_units, list):
                units.extend(unit for unit in paragraph_units if isinstance(unit, dict))
    return {
        "mode": "zh_main_ja_comment",
        "chunk_id": chunk_id,
        "units": units,
    }


def load_current_compact(
    chunk_id: str,
    chunk_out_dir: Path,
    reviewed_dir: Path,
) -> tuple[dict[str, Any] | None, str]:
    candidates = [
        (reviewed_dir / f"{chunk_id}.json", "reviewed"),
        (chunk_out_dir / f"{chunk_id}.json", "data"),
        (chunk_out_dir / f"{chunk_id}.raw.json", "raw"),
    ]
    for path, label in candidates:
        if not path.exists():
            continue
        try:
            data = load_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        if is_renderer_chunk(data):
            return compact_from_renderer(data, chunk_id), label
        if isinstance(data.get("units"), list):
            data["mode"] = "zh_main_ja_comment"
            data["chunk_id"] = chunk_id
            return data, label
    return None, ""


def canonicalize_compact(data: dict[str, Any], source_chunk: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, list[str]]:
    data["mode"] = "zh_main_ja_comment"
    data["chunk_id"] = source_chunk["chunk_id"]
    truncate_extra_zh_tail_to_paragraph(data, source_chunk)
    repair_zh_tokens_to_paragraph(data, source_chunk)
    align_unit_sources_to_paragraph(data, source_chunk)
    sync_source_text_from_zh_if_complete(data, source_chunk)
    backfill_common_ja_readings(data)
    shorten_overlong_ja_comments(data)
    backfill_missing_roles(data)
    errors = validate_chunk_output(data)
    renderer: dict[str, Any] | None = None
    if not errors:
        try:
            renderer = wrap_renderer_chunk(data, source_chunk)
        except ValueError as exc:
            errors.append(str(exc))
    if renderer is not None:
        errors.extend(validate_renderer_chunk(renderer, source_chunk))
    return data, renderer, errors


def paragraph_source_text(source_chunk: dict[str, Any]) -> str:
    return "".join(str(p.get("text", "")) for p in source_chunk.get("paragraphs", []))


def trim_normalized_suffix(text: str, suffix: str) -> str:
    if not suffix:
        return text
    if text.endswith(suffix):
        return text[: -len(suffix)]
    compact = normalize(text)
    if compact.endswith(suffix):
        return compact[: -len(suffix)]
    return text


def is_deterministic_source_char(char: str) -> bool:
    return bool(char) and not is_content_text(char)


def acceptable_source_diff(expected: str, got: str, max_chars: int = MAX_DETERMINISTIC_SOURCE_EDITS) -> list[tuple[str, int, int, int, int]] | None:
    edits: list[tuple[str, int, int, int, int]] = []
    edit_chars = 0
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, expected, got, autojunk=False).get_opcodes():
        if tag == "equal":
            edits.append((tag, i1, i2, j1, j2))
            continue
        expected_part = expected[i1:i2]
        got_part = got[j1:j2]
        if not all(is_deterministic_source_char(char) for char in expected_part + got_part):
            return None
        edit_chars += max(len(expected_part), len(got_part))
        if edit_chars > max_chars:
            return None
        edits.append((tag, i1, i2, j1, j2))
    return edits if edit_chars else None


def zh_token_flat_units(units: list[Any]) -> tuple[list[tuple[int, dict[str, Any]]], list[list[dict[str, Any]]]] | None:
    flat: list[tuple[int, dict[str, Any]]] = []
    per_unit: list[list[dict[str, Any]]] = [[] for _ in units]
    for unit_index, unit in enumerate(units):
        if not isinstance(unit, dict):
            return None
        tokens = unit.get("zh")
        if not isinstance(tokens, list):
            return None
        for token in tokens:
            if not isinstance(token, dict):
                return None
            text = str(token.get("t", ""))
            if not text:
                continue
            if len(text) > 1 and has_han(text):
                return None
            for char in text:
                item = dict(token)
                item["t"] = char
                if not is_single_han(char):
                    item["r"] = ""
                flat.append((unit_index, item))
    return flat, per_unit


def source_punct_token(char: str) -> dict[str, str]:
    return {"t": char, "r": ""}


def insertion_unit(flat: list[tuple[int, dict[str, Any]]], got_index: int, text: str) -> int:
    if not flat:
        return 0
    first = text[0] if text else ""
    if first in CLOSING_PUNCT and got_index > 0:
        return flat[got_index - 1][0]
    if first in OPENING_PUNCT and got_index < len(flat):
        return flat[got_index][0]
    if got_index > 0:
        return flat[got_index - 1][0]
    return flat[0][0]


def repair_zh_tokens_to_paragraph(data: dict[str, Any], source_chunk: dict[str, Any]) -> None:
    units = data.get("units")
    if not isinstance(units, list) or not units:
        return
    target = normalize(paragraph_source_text(source_chunk))
    if not target:
        return
    flattened = zh_token_flat_units(units)
    if flattened is None:
        return
    flat, per_unit = flattened
    got = "".join(str(token.get("t", "")) for _, token in flat)
    if got == target:
        sync_source_text_from_zh_if_complete(data, source_chunk)
        return
    edits = acceptable_source_diff(target, got)
    if edits is None:
        return
    for tag, i1, i2, j1, j2 in edits:
        if tag == "equal":
            for unit_index, token in flat[j1:j2]:
                per_unit[unit_index].append(dict(token))
        elif tag == "delete":
            unit_index = insertion_unit(flat, j1, target[i1:i2])
            for char in target[i1:i2]:
                per_unit[unit_index].append(source_punct_token(char))
        elif tag == "insert":
            continue
        elif tag == "replace":
            unit_index = flat[j1][0] if j1 < len(flat) else insertion_unit(flat, j1, target[i1:i2])
            for char in target[i1:i2]:
                per_unit[unit_index].append(source_punct_token(char))
    if normalize("".join(token_text(tokens) for tokens in per_unit)) != target:
        return
    for unit, tokens in zip(units, per_unit):
        if not isinstance(unit, dict):
            continue
        unit["zh"] = tokens
        unit["source_text"] = token_text(tokens)


def truncate_extra_zh_tail_to_paragraph(data: dict[str, Any], source_chunk: dict[str, Any]) -> None:
    units = data.get("units")
    if not isinstance(units, list) or not units:
        return
    target = re.sub(r"\s+", "", normalize(paragraph_source_text(source_chunk)))
    if not target:
        return
    flattened = zh_token_flat_units(units)
    if flattened is None:
        return
    flat, per_unit = flattened
    compact_flat: list[tuple[int, dict[str, Any], str]] = []
    for unit_index, token in flat:
        text = re.sub(r"\s+", "", str(token.get("t", "")))
        if text:
            compact_flat.append((unit_index, token, text))
    got = "".join(text for _, _, text in compact_flat)
    if not got.startswith(target) or len(got) <= len(target):
        return
    remaining = len(target)
    for unit_index, token, text in compact_flat:
        if remaining <= 0:
            break
        if len(text) <= remaining:
            kept = dict(token)
            kept["t"] = text
            per_unit[unit_index].append(kept)
            remaining -= len(text)
        else:
            kept = dict(token)
            kept["t"] = text[:remaining]
            per_unit[unit_index].append(kept)
            remaining = 0
            break
    if remaining != 0:
        return
    new_units: list[dict[str, Any]] = []
    for unit, tokens in zip(units, per_unit):
        if not isinstance(unit, dict) or not tokens:
            continue
        unit["zh"] = tokens
        unit["source_text"] = token_text(tokens)
        new_units.append(unit)
    if normalize("".join(token_text(unit.get("zh", [])) for unit in new_units)) == target:
        data["units"] = new_units


def sync_source_text_from_zh_if_complete(data: dict[str, Any], source_chunk: dict[str, Any]) -> None:
    units = data.get("units")
    if not isinstance(units, list) or not units:
        return
    target = normalize(paragraph_source_text(source_chunk))
    rebuilt = normalize("".join(token_text(unit.get("zh", [])) for unit in units if isinstance(unit, dict)))
    if target and rebuilt == target:
        for unit in units:
            if isinstance(unit, dict):
                unit["source_text"] = token_text(unit.get("zh", []))


def backfill_common_ja_readings(data: dict[str, Any]) -> None:
    units = data.get("units")
    if not isinstance(units, list):
        return
    for unit in units:
        if not isinstance(unit, dict):
            continue
        lines = unit.get("ja")
        if not isinstance(lines, list):
            continue
        for line in lines:
            if not isinstance(line, list):
                continue
            for token in line:
                if not isinstance(token, dict):
                    continue
                text = str(token.get("t", ""))
                if is_single_han(text) and not str(token.get("r", "")):
                    reading = COMMON_JA_KANBUN_READINGS.get(text)
                    if reading:
                        token["r"] = reading


def concise_comment_tokens() -> list[dict[str, str]]:
    return [
        {"t": "語", "r": "ご", "g": "topic"},
        {"t": "義", "r": "ぎ", "g": "topic"},
        {"t": "を", "r": "", "g": "function"},
        {"t": "次", "r": "つぎ", "g": "attributive"},
        {"t": "注", "r": "ちゅう", "g": "object"},
        {"t": "で", "r": "", "g": "function"},
        {"t": "示", "r": "しめ", "g": "predicate"},
        {"t": "す", "r": "", "g": "function"},
        {"t": "。", "r": "", "g": "function"},
    ]


def shorten_overlong_ja_comments(data: dict[str, Any]) -> None:
    units = data.get("units")
    if not isinstance(units, list):
        return
    for unit in units:
        if not isinstance(unit, dict):
            continue
        source_text = str(unit.get("source_text", ""))
        lines = unit.get("ja")
        if not source_text or not isinstance(lines, list) or len(lines) != 2 or not isinstance(lines[1], list):
            continue
        comment_text = normalize(token_text(lines[1]))
        if len(comment_text) > max(42, len(normalize(source_text)) * 4):
            unit["ja_line_roles"] = ["gloss", "explanatory_comment"]
            lines[1] = concise_comment_tokens()


def align_unit_sources_to_paragraph(data: dict[str, Any], source_chunk: dict[str, Any]) -> None:
    """Repair tiny end-boundary drift between unit source_text and paragraph.

    Most remaining hard chunks differ only by a trailing annotation bracket or
    punctuation mark.  Fix those locally so the model is not asked to regenerate
    an otherwise usable chunk.
    """
    units = data.get("units")
    if not isinstance(units, list) or not units:
        return
    target = normalize(paragraph_source_text(source_chunk))
    got = normalize("".join(str(unit.get("source_text", "")) for unit in units if isinstance(unit, dict)))
    if not target or got == target:
        return
    if got.startswith(target) and 0 < len(got) - len(target) <= 3:
        extra = got[len(target):]
        remaining = extra
        for unit in reversed(units):
            if not remaining or not isinstance(unit, dict):
                continue
            source_text = str(unit.get("source_text", ""))
            compact = normalize(source_text)
            if not compact:
                continue
            if len(remaining) >= len(compact) and remaining.endswith(compact):
                unit["source_text"] = ""
                remaining = remaining[: -len(compact)]
                continue
            if compact.endswith(remaining):
                unit["source_text"] = trim_normalized_suffix(source_text, remaining)
                remaining = ""
        return
    if target.startswith(got) and 0 < len(target) - len(got) <= 3:
        missing = target[len(got):]
        for unit in reversed(units):
            if isinstance(unit, dict):
                unit["source_text"] = str(unit.get("source_text", "")) + missing
                return


def is_content_text(text: str) -> bool:
    return bool(CONTENT_RE.search(text)) and not PUNCT_ONLY_RE.fullmatch(text)


def clipped(text: str, limit: int = 180) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def mismatch_detail(where: str, expected: str, got: str) -> str:
    exp = normalize(expected)
    actual = normalize(got)
    common = 0
    for exp_char, got_char in zip(exp, actual):
        if exp_char != got_char:
            break
        common += 1
    start = max(0, common - 60)
    return (
        f"{where}: text reconstruction mismatch; expected_len={len(exp)} got_len={len(actual)} "
        f"common_prefix={common}. "
        f"Expected near mismatch: {clipped(exp[start:common + 180])!r}. "
        f"Got near mismatch: {clipped(actual[start:common + 180])!r}. "
        "If common_prefix is very small, discard the current unit text and rebuild from the exact original paragraph."
    )


def role_counts(tokens: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokens:
        text = str(token.get("t", ""))
        if not is_content_text(text):
            continue
        role = str(token.get("g", "")).strip()
        if not role or role == "function":
            continue
        counts[role] = counts.get(role, 0) + 1
    return counts


def unit_tokens(unit: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    if lang == "zh":
        values = unit.get("zh", [])
        return [token for token in values if isinstance(token, dict)] if isinstance(values, list) else []
    tokens: list[dict[str, Any]] = []
    lines = unit.get("ja", [])
    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, list):
                tokens.extend(token for token in line if isinstance(token, dict))
    return tokens


def detect_quality_issues(data: dict[str, Any], source_chunk: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    paragraph_text = "".join(str(p.get("text", "")) for p in source_chunk.get("paragraphs", []))
    unit_source_text = "".join(str(unit.get("source_text", "")) for unit in data.get("units", []) if isinstance(unit, dict))
    if paragraph_text and normalize(unit_source_text) != normalize(paragraph_text):
        issues.append(mismatch_detail("all units source_text", paragraph_text, unit_source_text))

    chunk_role_counts = {"zh": {}, "ja": {}}
    for unit_index, unit in enumerate(data.get("units", [])):
        if not isinstance(unit, dict):
            continue
        where = f"units[{unit_index}]"
        source_text = str(unit.get("source_text", ""))
        zh_text = token_text(unit.get("zh", []))
        if source_text and normalize(zh_text) != normalize(source_text):
            issues.append(mismatch_detail(f"{where}.zh", source_text, zh_text))

        ja = unit.get("ja")
        if not isinstance(ja, list) or len(ja) != 2:
            continue
        line_texts = [token_text(line) if isinstance(line, list) else "" for line in ja]
        compact_lines = [normalize(text) for text in line_texts]
        for line_index, compact in enumerate(compact_lines):
            if not compact:
                issues.append(f"{where}.ja[{line_index}]: Japanese line is empty")
            if compact in {"。", "注。", "説明。", "訳。"}:
                issues.append(f"{where}.ja[{line_index}]: Japanese line is a placeholder, not real content")
            if len(compact) >= 4 and not has_han(compact):
                issues.append(f"{where}.ja[{line_index}]: Japanese content is kana-only; use normal mixed kanji/kana")
            if source_text and len(compact) > max(42, len(normalize(source_text)) * 4):
                issues.append(f"{where}.ja[{line_index}]: Japanese line is too long for pocket interlinear layout")
        if compact_lines[0] and compact_lines[0] == compact_lines[1]:
            issues.append(
                f"{where}: gloss and explanatory_comment are identical "
                f"({clipped(compact_lines[0], 100)!r}); keep ja[0] as the gloss and rewrite ja[1] "
                "as a concise explanatory note about meaning or grammar"
            )
        elif compact_lines[0] and compact_lines[1] and compact_lines[0] in compact_lines[1] and len(compact_lines[0]) >= 8:
            issues.append(
                f"{where}: explanatory_comment mostly duplicates the gloss "
                f"(gloss={clipped(compact_lines[0], 80)!r}, comment={clipped(compact_lines[1], 100)!r}); "
                "rewrite ja[1] as a concise explanatory note"
            )

        for lang in ("zh", "ja"):
            counts = role_counts(unit_tokens(unit, lang))
            total = sum(counts.values())
            for role, count in counts.items():
                chunk_role_counts[lang][role] = chunk_role_counts[lang].get(role, 0) + count
            if total >= 18:
                dominant_role, dominant_count = max(counts.items(), key=lambda item: item[1]) if counts else ("", 0)
                if dominant_count / total >= 0.92:
                    issues.append(
                        f"{where}.{lang}: grammar/color collapse, {dominant_count}/{total} content tokens are {dominant_role}"
                    )
                if len(counts) < 2:
                    issues.append(f"{where}.{lang}: grammar/color variety too low for a long unit")

    for lang, counts in chunk_role_counts.items():
        total = sum(counts.values())
        if total >= 45:
            dominant_role, dominant_count = max(counts.items(), key=lambda item: item[1]) if counts else ("", 0)
            if dominant_count / total >= 0.88:
                issues.append(
                    f"chunk.{lang}: grammar/color collapse, {dominant_count}/{total} content tokens are {dominant_role}"
                )
            if len(counts) < 3:
                issues.append(f"chunk.{lang}: grammar/color variety too low across the chunk")

    return issues


def detect_issues(data: dict[str, Any], source_chunk: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, list[str]]:
    compact, renderer, errors = canonicalize_compact(data, source_chunk)
    quality = detect_quality_issues(compact, source_chunk)
    return compact, renderer, errors + quality


REVIEW_SYSTEM_PROMPT = f"""\
You are a strict interlinear JSON repair reviewer.

You receive:
- the original Chinese source paragraph,
- the current compact JSON,
- a deterministic issue list.

Repair the JSON only as much as needed. Return one COMPLETE compact JSON object:
{{
  "mode": "zh_main_ja_comment",
  "chunk_id": "...",
  "units": [
    {{
      "source_text": "...",
      "zh": [{{"t": "...", "r": "...", "g": "..."}}],
      "ja_line_roles": ["gloss", "explanatory_comment"],
      "ja": [[{{"t": "...", "r": "...", "g": "..."}}], [{{"t": "...", "r": "...", "g": "..."}}]]
    }}
  ]
}}

Hard rules:
- Do not omit, add, or rewrite any Chinese source character. zh token text and
  unit.source_text must reconstruct the original paragraph exactly after
  whitespace normalization.
- Split every Chinese Hanzi and every Japanese kanji into one-character tokens.
- Put pinyin only on single Chinese Hanzi tokens.
- Put furigana only on single Japanese kanji tokens.
- Every Chinese Hanzi and every Japanese kanji must have `g`.
- Allowed grammar roles: {", ".join(sorted(GRAMMAR_ROLES))}.
- ja[0] is a Japanese gloss/reading. ja[1] is a smaller explanatory scholarly
  note, not a duplicate translation.
- Fix every listed issue, then self-check before answering.

Return only JSON. No markdown fences.
"""


def build_review_prompt(
    source_chunk: dict[str, Any],
    compact: dict[str, Any],
    issues: list[str],
    context_chunks: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    parts.append(f"Chunk ID: {source_chunk['chunk_id']}")
    parts.append(f"Section: {source_chunk.get('subsection_title', '')}")
    parts.append("")
    if context_chunks:
        parts.append("--- Nearby source context ---")
        for context in context_chunks:
            text = context.get("paragraphs", [{}])[0].get("text", "")
            parts.append(str(text))
        parts.append("--- End nearby source context ---")
        parts.append("")
    parts.append("--- Original Chinese paragraph ---")
    parts.append("".join(str(p.get("text", "")) for p in source_chunk.get("paragraphs", [])))
    parts.append("--- End original Chinese paragraph ---")
    parts.append("")
    parts.append("--- Deterministic issues to fix ---")
    for issue in issues[:40]:
        parts.append(f"- {issue}")
    if len(issues) > 40:
        parts.append(f"- ... {len(issues) - 40} more issues omitted from prompt")
    parts.append("--- End issues ---")
    parts.append("")
    rebuild_from_source = any(
        "common_prefix=0" in issue
        or "all units source_text: text reconstruction mismatch" in issue
        or "units do not reconstruct paragraph source_text" in issue
        for issue in issues
    )
    if rebuild_from_source:
        parts.append("--- Current compact JSON omitted ---")
        parts.append(
            "The deterministic reviewer found that the current JSON does not reconstruct the source paragraph. "
            "Do not patch or reuse its unit boundaries. Rebuild a complete compact JSON annotation from the exact "
            "original Chinese paragraph above. Include every source character and do not add closing brackets or "
            "comment text that is not present in the original paragraph."
        )
        parts.append("--- End current compact JSON omitted ---")
    else:
        parts.append("--- Current compact JSON ---")
        parts.append(json.dumps(compact, ensure_ascii=False, indent=2))
        parts.append("--- End current compact JSON ---")
    return "\n".join(parts)


def parse_json_response(raw_response: str) -> dict[str, Any]:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = repair_json(cleaned)
        if not repaired:
            raise
        return json.loads(repaired)


def build_context(chunks_by_subsection: dict[str, list[dict[str, Any]]], chunk: dict[str, Any]) -> list[dict[str, Any]]:
    sub = chunk.get("subsection_id", "__unknown__")
    sub_list = chunks_by_subsection.get(sub, [])
    sub_idx = next((i for i, item in enumerate(sub_list) if item.get("chunk_id") == chunk.get("chunk_id")), -1)
    if sub_idx < 0:
        return []
    start = max(0, sub_idx - 2)
    end = min(len(sub_list), sub_idx + 3)
    return [sub_list[i] for i in range(start, end) if i != sub_idx]


def write_issue_report(report_dir: Path, chunk_id: str, report: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{chunk_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def promote_valid(
    compact: dict[str, Any],
    renderer: dict[str, Any],
    chunk_out_dir: Path,
    reviewed_dir: Path,
    chunk_id: str,
) -> None:
    raw_path = chunk_out_dir / f"{chunk_id}.raw.json"
    out_path = chunk_out_dir / f"{chunk_id}.json"
    reviewed_path = reviewed_dir / f"{chunk_id}.json"
    atomic_write_json(raw_path, compact)
    promote_renderer_chunk(renderer, out_path, reviewed_path)


def salvage_previous_attempt(
    attempt_dir: Path,
    chunk_id: str,
    source_chunk: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], Path] | None:
    attempts = sorted(
        attempt_dir.glob(f"{chunk_id}.round-*.raw.txt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for raw_path in attempts:
        try:
            candidate = parse_json_response(raw_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        candidate["chunk_id"] = chunk_id
        compact, renderer, issues = detect_issues(candidate, source_chunk)
        if not issues and renderer is not None:
            return compact, renderer, raw_path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", default="sishu-jizhu-aginti")
    parser.add_argument("--start-chunk", type=int, default=1)
    parser.add_argument("--max-chunks", type=int, default=0, help="0 = no limit")
    parser.add_argument("--review-rounds", type=int, default=int(os.environ.get("AGINTI_DYNAMIC_REVIEW_ROUNDS", "2")))
    parser.add_argument("--delay", type=float, default=float(os.environ.get("AGINTI_DYNAMIC_REVIEW_DELAY", "1")))
    parser.add_argument("--sleep", type=float, default=float(os.environ.get("AGINTI_DYNAMIC_REVIEW_SLEEP", "600")))
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--issue-only", action="store_true", help="Detect/report issues without API repair")
    parser.add_argument("--failed-only", action="store_true", help="Only review chunks currently listed in status.json failed_ids")
    parser.add_argument("--reviewed-dir", default="")
    parser.add_argument("--api-timeout", type=float, default=float(os.environ.get("AGINTI_API_TIMEOUT", "180")))
    parser.add_argument("--api-retries", type=int, default=int(os.environ.get("AGINTI_API_RETRIES", "2")))
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("AGINTI_MAX_TOKENS", "16384")))
    parser.add_argument("--compile-every", type=int, default=0)
    parser.add_argument("--compile-at-end", action="store_true")
    args = parser.parse_args()

    book_id = args.book
    chunks = load_chunks(book_id)
    chunks_by_subsection: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        chunks_by_subsection.setdefault(chunk.get("subsection_id", "__unknown__"), []).append(chunk)

    chunk_out_dir = ROOT / "data" / "interlinear" / book_id / "chunks"
    reviewed_dir = reviewed_dir_for(book_id, args.reviewed_dir)
    work_dir = ROOT / "books" / book_id / "work" / "bilingual" / "dynamic-review"
    issue_dir = work_dir / "issues"
    attempt_dir = work_dir / "attempts"
    lock_dir = work_dir / "locks"
    log_path = work_dir / "dynamic-review.log"
    status_path = ROOT / "data" / "interlinear" / book_id / "dynamic-review-status.json"
    book_status_path = ROOT / "data" / "interlinear" / book_id / "status.json"
    for path in (chunk_out_dir, reviewed_dir, issue_dir, attempt_dir, lock_dir):
        path.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    model = os.environ.get("AGINTI_REVIEW_MODEL") or os.environ.get("AGINTI_DEEPSEEK_MODEL", "deepseek-chat")
    client = None
    if not args.dry_run and not args.issue_only:
        if not api_key:
            print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
            return 1
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1", timeout=args.api_timeout)

    def log(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    promoted_since_compile = 0

    def run_once() -> dict[str, Any]:
        nonlocal promoted_since_compile
        scanned = valid = fixed = unresolved = missing = locked = api_errors = 0
        fixed_ids: set[str] = set()
        selected = chunks[max(0, args.start_chunk - 1):]
        if args.max_chunks:
            selected = selected[: args.max_chunks]
        if args.failed_only:
            failed_filter = set(load_status(book_status_path).get("failed_ids", []))
            selected = [chunk for chunk in selected if chunk.get("chunk_id") in failed_filter]
        for index, source_chunk in enumerate(selected, start=args.start_chunk):
            chunk_id = source_chunk["chunk_id"]
            with chunk_lock(lock_dir, chunk_id) as got_lock:
                if not got_lock:
                    locked += 1
                    continue
                compact, loaded_from = load_current_compact(chunk_id, chunk_out_dir, reviewed_dir)
                if compact is None:
                    report: dict[str, Any] = {
                        "book": book_id,
                        "chunk_id": chunk_id,
                        "chunk_index": index,
                        "loaded_from": "",
                        "checked_at": now_iso(),
                        "initial_issue_count": 1,
                        "initial_issues": ["missing or corrupt compact JSON; rebuilding from source"],
                        "rounds": [],
                    }
                    if args.dry_run or args.issue_only:
                        missing += 1
                        write_issue_report(issue_dir, chunk_id, report)
                        log(f"{chunk_id}: missing current compact; not rebuilding")
                        continue
                    prompt = build_write_user_prompt(source_chunk, build_context(chunks_by_subsection, source_chunk))
                    prompt_path = attempt_dir / f"{chunk_id}.rebuild.prompt.md"
                    raw_path = attempt_dir / f"{chunk_id}.rebuild.raw.txt"
                    prompt_path.write_text(prompt, encoding="utf-8")
                    raw_response = ""
                    for attempt in range(1, max(1, args.api_retries + 1) + 1):
                        try:
                            raw_response = call_deepseek(
                                client,
                                model,
                                WRITE_SYSTEM_PROMPT,
                                prompt,
                                args.max_tokens,
                            )
                            break
                        except Exception as exc:
                            if attempt <= args.api_retries:
                                wait_seconds = min(90.0, max(args.delay, 2.0) * attempt)
                                log(
                                    f"{chunk_id}: rebuild API error attempt={attempt}/{args.api_retries + 1}: "
                                    f"{type(exc).__name__}: {exc}; retrying in {wait_seconds:.1f}s"
                                )
                                time.sleep(wait_seconds)
                                continue
                            api_errors += 1
                            report["rounds"].append({
                                "round": "rebuild",
                                "api_error": f"{type(exc).__name__}: {exc}",
                            })
                    if not raw_response:
                        missing += 1
                        report["final_issue_count"] = 1
                        report["final_issues"] = ["missing or corrupt compact JSON; rebuild API returned no response"]
                        write_issue_report(issue_dir, chunk_id, report)
                        continue
                    raw_path.write_text(raw_response, encoding="utf-8")
                    try:
                        candidate = parse_json_response(raw_response)
                    except Exception as exc:
                        missing += 1
                        report["rounds"].append({
                            "round": "rebuild",
                            "parse_error": str(exc),
                        })
                        report["final_issue_count"] = 1
                        report["final_issues"] = [f"JSON parse error from rebuild: {exc}"]
                        write_issue_report(issue_dir, chunk_id, report)
                        continue
                    candidate["chunk_id"] = chunk_id
                    candidate, candidate_renderer, next_issues = detect_issues(candidate, source_chunk)
                    report["rounds"].append({
                        "round": "rebuild",
                        "issues_after": next_issues,
                    })
                    if not next_issues and candidate_renderer is not None:
                        promote_valid(candidate, candidate_renderer, chunk_out_dir, reviewed_dir, chunk_id)
                        fixed += 1
                        fixed_ids.add(chunk_id)
                        promoted_since_compile += 1
                        report["final_issue_count"] = 0
                        report["final_issues"] = []
                        write_issue_report(issue_dir, chunk_id, report)
                        log(f"{chunk_id}: rebuilt missing compact and promoted")
                        continue
                    missing += 1
                    report["final_issue_count"] = len(next_issues)
                    report["final_issues"] = next_issues
                    write_issue_report(issue_dir, chunk_id, report)
                    log(f"{chunk_id}: rebuild left {len(next_issues)} issues")
                    continue
                scanned += 1
                compact, renderer, issues = detect_issues(compact, source_chunk)
                report: dict[str, Any] = {
                    "book": book_id,
                    "chunk_id": chunk_id,
                    "chunk_index": index,
                    "loaded_from": loaded_from,
                    "checked_at": now_iso(),
                    "initial_issue_count": len(issues),
                    "initial_issues": issues,
                    "rounds": [],
                }
                if not issues and renderer is not None:
                    if not args.dry_run and not args.issue_only:
                        promote_valid(compact, renderer, chunk_out_dir, reviewed_dir, chunk_id)
                    valid += 1
                    write_issue_report(issue_dir, chunk_id, report)
                    continue

                if args.dry_run or args.issue_only:
                    unresolved += 1
                    write_issue_report(issue_dir, chunk_id, report)
                    log(f"{chunk_id}: detected {len(issues)} issues; not repairing")
                    continue

                salvaged = salvage_previous_attempt(attempt_dir, chunk_id, source_chunk)
                if salvaged is not None:
                    salvaged_compact, salvaged_renderer, raw_attempt_path = salvaged
                    promote_valid(salvaged_compact, salvaged_renderer, chunk_out_dir, reviewed_dir, chunk_id)
                    fixed += 1
                    fixed_ids.add(chunk_id)
                    promoted_since_compile += 1
                    report["rounds"].append({
                        "round": "salvage_previous_attempt",
                        "raw_attempt": str(raw_attempt_path.relative_to(ROOT)),
                        "issues_after": [],
                    })
                    report["final_issue_count"] = 0
                    report["final_issues"] = []
                    write_issue_report(issue_dir, chunk_id, report)
                    log(f"{chunk_id}: salvaged previous dynamic review attempt and promoted")
                    continue

                current = compact
                current_issues = issues
                current_renderer = renderer
                for review_round in range(1, max(1, args.review_rounds) + 1):
                    prompt = build_review_prompt(
                        source_chunk,
                        current,
                        current_issues,
                        build_context(chunks_by_subsection, source_chunk),
                    )
                    prompt_path = attempt_dir / f"{chunk_id}.round-{review_round}.prompt.md"
                    raw_path = attempt_dir / f"{chunk_id}.round-{review_round}.raw.txt"
                    prompt_path.write_text(prompt, encoding="utf-8")
                    raw_response = ""
                    for attempt in range(1, max(1, args.api_retries + 1) + 1):
                        try:
                            raw_response = call_deepseek(
                                client,
                                model,
                                REVIEW_SYSTEM_PROMPT,
                                prompt,
                                args.max_tokens,
                            )
                            break
                        except Exception as exc:
                            if attempt <= args.api_retries:
                                wait_seconds = min(90.0, max(args.delay, 2.0) * attempt)
                                log(
                                    f"{chunk_id}: API error round={review_round} "
                                    f"attempt={attempt}/{args.api_retries + 1}: {type(exc).__name__}: {exc}; "
                                    f"retrying in {wait_seconds:.1f}s"
                                )
                                time.sleep(wait_seconds)
                                continue
                            api_errors += 1
                            report["rounds"].append({
                                "round": review_round,
                                "api_error": f"{type(exc).__name__}: {exc}",
                                "issues_before": current_issues,
                            })
                    if not raw_response:
                        break
                    raw_path.write_text(raw_response, encoding="utf-8")
                    try:
                        candidate = parse_json_response(raw_response)
                    except Exception as exc:
                        current_issues = [f"JSON parse error from dynamic reviewer: {exc}"]
                        report["rounds"].append({
                            "round": review_round,
                            "parse_error": str(exc),
                            "issues_after": current_issues,
                        })
                        continue
                    candidate["chunk_id"] = chunk_id
                    candidate, candidate_renderer, next_issues = detect_issues(candidate, source_chunk)
                    report["rounds"].append({
                        "round": review_round,
                        "issues_before": current_issues,
                        "issues_after": next_issues,
                    })
                    current = candidate
                    current_renderer = candidate_renderer
                    current_issues = next_issues
                    if not current_issues and current_renderer is not None:
                        promote_valid(current, current_renderer, chunk_out_dir, reviewed_dir, chunk_id)
                        fixed += 1
                        fixed_ids.add(chunk_id)
                        promoted_since_compile += 1
                        log(f"{chunk_id}: dynamic review fixed and promoted")
                        break
                    log(f"{chunk_id}: dynamic review round {review_round} left {len(current_issues)} issues")
                    time.sleep(args.delay)

                report["final_issue_count"] = len(current_issues)
                report["final_issues"] = current_issues
                write_issue_report(issue_dir, chunk_id, report)
                if current_issues:
                    unresolved += 1
                if args.compile_every and promoted_since_compile >= args.compile_every:
                    compile_previews(book_id, log)
                    promoted_since_compile = 0

        summary = {
            "book": book_id,
            "checked_at": now_iso(),
            "scanned": scanned,
            "valid": valid,
            "fixed": fixed,
            "unresolved": unresolved,
            "missing": missing,
            "locked": locked,
            "api_errors": api_errors,
        }
        if not args.dry_run and not args.issue_only:
            failed_ids = set(load_status(book_status_path).get("failed_ids", []))
            failed_ids.difference_update(fixed_ids)
            save_computed_status(book_status_path, book_id, chunks, reviewed_dir, failed_ids)
        status_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log(
            "summary: "
            f"scanned={scanned} valid={valid} fixed={fixed} unresolved={unresolved} "
            f"missing={missing} locked={locked} api_errors={api_errors}"
        )
        return summary

    while True:
        run_once()
        if args.compile_at_end:
            compile_previews(book_id, log)
        if not args.loop:
            break
        log(f"sleeping {args.sleep:.0f}s before next dynamic review pass")
        time.sleep(args.sleep)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
