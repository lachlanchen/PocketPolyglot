#!/usr/bin/env python3
"""Generate trilingual plain alignment chunks, then promote them to strict token JSON."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pykakasi
from pypinyin import Style, pinyin

from codex_chunk_worker import compact, extract_json, load_chunks, mentions_usage_limit, run_codex
from codex_trilingual_parallel_json_worker import claim_chunk, iter_selected, release_claim, valid_existing
from validate_trilingual_interlinear_json import HAN_RE, KANA_RE, SINGLE_HAN_RE, validate_chunk


SPACE_RE = re.compile(r"\s+")
EN_TOKEN_RE = re.compile(r"\s+|[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+(?:[.,]\d+)*|[^\sA-Za-z0-9]+")
EN_SENTENCE_BOUNDARY_RE = re.compile(r'[.!?]["”’)]*\s+')
SOURCE_SPINE_LANGS = {"en", "zh", "ja"}
CJK_SENTENCE_END = set("。！？!?；;")
CJK_CLOSERS = set("」』”’）)]〉》")
KAKASI = pykakasi.kakasi()
JA_READING_CACHE: dict[str, str] = {}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status_record(status: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "updated_at": datetime.now(timezone.utc).isoformat(), **extra}


def normalize_space(text: str) -> str:
    return SPACE_RE.sub(" ", str(text or "")).strip()


def plain_text(value: Any) -> str:
    return normalize_space(str(value or "").replace("\n", " "))


def split_english_units(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for match in EN_SENTENCE_BOUNDARY_RE.finditer(text):
        end = match.end()
        piece = text[start:end]
        if piece.strip():
            parts.append(piece)
        start = end
    tail = text[start:]
    if tail.strip():
        parts.append(tail)
    return parts or [text]


def split_cjk_units(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] not in CJK_SENTENCE_END:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in CJK_CLOSERS:
            end += 1
        piece = text[start:end]
        if piece.strip():
            parts.append(piece)
        start = end
        index = end
    tail = text[start:]
    if tail.strip():
        parts.append(tail)
    return parts or [text]


def source_spine_lang(chunk: dict[str, Any]) -> str:
    lang = str(chunk.get("source_spine_lang") or "en")
    return lang if lang in SOURCE_SPINE_LANGS else "en"


def paragraph_source_text(paragraph: dict[str, Any], spine_lang: str) -> str:
    for lang in (spine_lang, "en", "zh", "ja"):
        text = str(paragraph.get(lang) or "")
        if text.strip():
            return text
    return ""


def split_source_units(text: str, lang: str) -> list[str]:
    if lang == "en":
        return split_english_units(text)
    return split_cjk_units(text)


def source_unit_plan(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    spine_lang = source_spine_lang(chunk)
    paragraphs: list[dict[str, Any]] = []
    for paragraph in chunk["paragraphs"]:
        source_text = paragraph_source_text(paragraph, spine_lang)
        units = [
            {"unit_id": f"{paragraph['id']}-u{unit_index:03d}", spine_lang: unit}
            for unit_index, unit in enumerate(split_source_units(source_text, spine_lang), start=1)
        ]
        paragraphs.append({"id": paragraph["id"], "units": units})
    return paragraphs


def prompt_for_plain_chunk(chunk: dict[str, Any], previous_errors: list[str] | None = None) -> str:
    error_block = ""
    if previous_errors:
        error_block = "\nPrevious output failed validation. Fix these exact issues:\n" + "\n".join(
            f"- {error}" for error in previous_errors[:80]
        )
    spine_lang = source_spine_lang(chunk)
    reference = chunk.get("reference", {})
    ja_ref = reference.get("ja", {})
    ja_instruction = (
        "Use the supplied Japanese source window when it matches this chunk."
        if ja_ref.get("available")
        else "No Japanese source window is available for this chapter; translate natural Japanese from the available source spine and references."
    )
    if spine_lang == "en":
        shape = """{{
          "schema_version": "0.1-plain",
          "mode": "trilingual_plain_alignment",
          "chunk_id": "{chunk_id}",
          "paragraphs": [
            {{
              "id": "source paragraph id",
              "units": [
                {{
                  "unit_id": "exact supplied unit id",
                  "zh": "faithful Chinese text for that unit",
                  "ja": "faithful Japanese text for that unit"
                }}
              ]
            }}
          ]
        }}"""
        spine_requirements = """
        - English is already supplied and will be preserved by the pipeline; do not include English in unit output.
        - Chinese must be real Chinese prose, not a summary. Prefer the supplied Chinese reference translations when they match the English.
        - Japanese: {ja_instruction}
        - Japanese must be real Japanese prose with kana or natural Japanese inflection. Use clear, common modern Japanese unless a supplied Japanese source requires otherwise. Never put Chinese prose in "ja"."""
    else:
        source_name = {"zh": "Chinese", "ja": "Japanese"}[spine_lang]
        copy_requirement = (
            'Copy each supplied "zh" source unit exactly into the output "zh" field.'
            if spine_lang == "zh"
            else 'Copy each supplied "ja" source unit exactly into the output "ja" field.'
        )
        shape = """{{
          "schema_version": "0.1-plain",
          "mode": "trilingual_plain_alignment",
          "chunk_id": "{chunk_id}",
          "paragraphs": [
            {{
              "id": "source paragraph id",
              "units": [
                {{
                  "unit_id": "exact supplied unit id",
                  "en": "faithful English translation for that unit",
                  "zh": "faithful Chinese text for that unit",
                  "ja": "faithful Japanese text for that unit"
                }}
              ]
            }}
          ]
        }}"""
        spine_requirements = f"""
        - Source spine language is {source_name}. {copy_requirement}
        - English must be natural literary English corresponding to the source unit and references.
        - Chinese must be real Chinese prose, not a summary.
        - Japanese: {ja_instruction}
        - Japanese must be real Japanese prose with kana or natural Japanese inflection. Use clear, common modern Japanese unless a supplied Japanese source requires otherwise. Never put Chinese prose in "ja"."""
    return textwrap.dedent(
        f"""
        You are aligning one chunk of a trilingual pocket book.

        Return exactly one JSON object. No Markdown fences. No explanation.

        Use the supplied source unit plan for alignment. Use the Chinese/Japanese/English source windows for faithful corresponding text.

        Required object shape:
        {shape.format(chunk_id=chunk['chunk_id'])}

        Hard requirements:
        - Preserve paragraph ids and order exactly.
        - Preserve unit_id values and order exactly.
        {spine_requirements.format(ja_instruction=ja_instruction)}
        - Do not include ruby, pinyin, token arrays, grammar colors, Markdown, commentary, or footnotes.
        - Keep chunk id and paragraph ids exactly as provided.
        {error_block}

        Chunk metadata:
        {json.dumps({key: chunk[key] for key in ('chunk_id', 'chapter_id', 'chapter_number', 'chapter_title_en', 'chapter_part_en')}, ensure_ascii=False, indent=2)}

        Source unit plan:
        {json.dumps(source_unit_plan(chunk), ensure_ascii=False, indent=2)}

        Reference windows:
        {json.dumps(reference, ensure_ascii=False, indent=2)}
        """
    ).strip()


def validate_plain_chunk(source: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("chunk_id") != source["chunk_id"]:
        errors.append(f"chunk_id mismatch: expected {source['chunk_id']!r}")
    if result.get("mode") not in {"trilingual_plain_alignment", None}:
        errors.append("mode must be trilingual_plain_alignment when present")
    paragraphs = result.get("paragraphs")
    if not isinstance(paragraphs, list):
        return errors + ["paragraphs must be a list"]
    expected_ids = [paragraph["id"] for paragraph in source["paragraphs"]]
    got_ids = [paragraph.get("id") for paragraph in paragraphs if isinstance(paragraph, dict)]
    if got_ids != expected_ids:
        errors.append(f"paragraph id/order mismatch: expected {expected_ids}, got {got_ids}")
    source_plan_by_id = {paragraph["id"]: paragraph["units"] for paragraph in source_unit_plan(source)}
    spine_lang = source_spine_lang(source)
    zh_required = spine_lang != "zh"
    ja_required = spine_lang != "ja"
    for paragraph_index, paragraph in enumerate(paragraphs):
        where = f"paragraphs[{paragraph_index}]"
        if not isinstance(paragraph, dict):
            errors.append(f"{where}: must be an object")
            continue
        paragraph_id = paragraph.get("id")
        if paragraph_id not in source_plan_by_id:
            continue
        units = paragraph.get("units")
        if not isinstance(units, list) or not units:
            errors.append(f"{paragraph_id}: missing units")
            continue
        expected_unit_ids = [unit["unit_id"] for unit in source_plan_by_id[paragraph_id]]
        got_unit_ids = [unit.get("unit_id") for unit in units if isinstance(unit, dict)]
        if got_unit_ids != expected_unit_ids:
            errors.append(f"{paragraph_id}: unit id/order mismatch: expected {expected_unit_ids}, got {got_unit_ids}")
        for unit_index, unit in enumerate(units):
            unit_where = f"{where}.units[{unit_index}]"
            if not isinstance(unit, dict):
                errors.append(f"{unit_where}: must be an object")
                continue
            zh = plain_text(unit.get("zh", ""))
            ja = plain_text(unit.get("ja", ""))
            en = plain_text(unit.get("en", ""))
            if zh_required and not zh:
                errors.append(f"{unit_where}.zh: empty")
            if ja_required and not ja:
                errors.append(f"{unit_where}.ja: empty")
            if spine_lang != "en" and not en:
                errors.append(f"{unit_where}.en: empty")
            if zh_required and zh and not HAN_RE.search(zh):
                errors.append(f"{unit_where}.zh: Chinese text must contain Han characters")
            if zh_required and zh and KANA_RE.search(zh):
                errors.append(f"{unit_where}.zh: Chinese row contains Japanese kana")
            if ja_required and ja and not KANA_RE.search(ja) and len("".join(ja.split())) > 12:
                errors.append(f"{unit_where}.ja: Japanese row must contain kana; pure Han text is usually Chinese, not Japanese")
    return errors


def tokenize_en(text: str) -> list[dict[str, str]]:
    tokens = [{"t": match.group(0)} for match in EN_TOKEN_RE.finditer(text)]
    return tokens or [{"t": text}]


def tokenize_zh(text: str) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            tokens.append({"t": "".join(buffer)})
            buffer.clear()

    for char in str(text):
        if SINGLE_HAN_RE.fullmatch(char):
            flush()
            reading = pinyin(char, style=Style.TONE, heteronym=False, strict=False)[0][0]
            tokens.append({"t": char, "r": reading})
        else:
            buffer.append(char)
    flush()
    return tokens


def japanese_reading_for_char(char: str) -> str:
    cached = JA_READING_CACHE.get(char)
    if cached is not None:
        return cached
    reading = ""
    try:
        converted = KAKASI.convert(char)
        if converted:
            reading = str(converted[0].get("hira") or "")
    except Exception:
        reading = ""
    if not reading or reading == char:
        reading = "よみ"
    JA_READING_CACHE[char] = reading
    return reading


def japanese_reading_for_text(text: str) -> str:
    try:
        return "".join(str(item.get("hira") or "") for item in KAKASI.convert(text))
    except Exception:
        return ""


def kana_to_hira(text: str) -> str:
    out: list[str] = []
    for char in text:
        code = ord(char)
        if 0x30A1 <= code <= 0x30FA:
            out.append(chr(code - 0x60))
        else:
            out.append(char)
    return "".join(out)


def split_kanji_readings(chars: list[str], reading: str) -> list[str]:
    reading = kana_to_hira(reading)
    if not chars:
        return []
    if len(chars) == 1:
        return [reading or japanese_reading_for_char(chars[0])]
    readings: list[str] = []
    cursor = 0
    matched_prefix = True
    for index, char in enumerate(chars[:-1]):
        standalone = japanese_reading_for_char(char)
        if reading.startswith(standalone, cursor) and len(reading) - cursor - len(standalone) >= len(chars) - index - 1:
            readings.append(standalone)
            cursor += len(standalone)
            continue
        matched_prefix = False
        break
    if matched_prefix:
        remainder = reading[cursor:]
        readings.append(remainder or japanese_reading_for_char(chars[-1]))
        return readings

    readings = []
    cursor = 0
    for index, _char in enumerate(chars):
        remaining_chars = len(chars) - index
        remaining_reading = len(reading) - cursor
        if remaining_chars == 1:
            piece = reading[cursor:]
        else:
            piece_len = max(1, (remaining_reading + remaining_chars - 1) // remaining_chars)
            piece = reading[cursor : cursor + piece_len]
        readings.append(piece or japanese_reading_for_char(chars[index]))
        cursor += len(piece)
    return readings


def segment_kanji_reading(orig: str, hira: str) -> str:
    reading = kana_to_hira(hira)
    chars = list(orig)
    first_kanji = next((index for index, char in enumerate(chars) if SINGLE_HAN_RE.fullmatch(char)), 0)
    last_kanji = len(chars) - 1 - next(
        (index for index, char in enumerate(reversed(chars)) if SINGLE_HAN_RE.fullmatch(char)),
        0,
    )
    prefix = kana_to_hira("".join(chars[:first_kanji]))
    suffix = kana_to_hira("".join(chars[last_kanji + 1 :]))
    if prefix and reading.startswith(prefix):
        reading = reading[len(prefix) :]
    if suffix and reading.endswith(suffix):
        reading = reading[: -len(suffix)]
    return reading


def append_ja_text(tokens: list[dict[str, str]], text: str) -> None:
    if not text:
        return
    if tokens and "r" not in tokens[-1]:
        tokens[-1]["t"] += text
    else:
        tokens.append({"t": text})


def tokenize_ja_segment(orig: str, hira: str) -> list[dict[str, str]]:
    if not HAN_RE.search(orig):
        return [{"t": orig}]
    tokens: list[dict[str, str]] = []
    kanji_chars = [char for char in orig if SINGLE_HAN_RE.fullmatch(char)]
    readings = split_kanji_readings(kanji_chars, segment_kanji_reading(orig, hira))
    reading_index = 0
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            append_ja_text(tokens, "".join(buffer))
            buffer.clear()

    for char in orig:
        if SINGLE_HAN_RE.fullmatch(char):
            flush()
            reading = readings[reading_index] if reading_index < len(readings) else japanese_reading_for_char(char)
            tokens.append({"t": char, "r": reading})
            reading_index += 1
        else:
            buffer.append(char)
    flush()
    return tokens


def tokenize_ja(text: str) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    try:
        segments = KAKASI.convert(str(text))
    except Exception:
        segments = [{"orig": str(text), "hira": japanese_reading_for_text(str(text))}]
    for segment in segments:
        for token in tokenize_ja_segment(str(segment.get("orig") or ""), str(segment.get("hira") or "")):
            if "r" in token:
                tokens.append(token)
            else:
                append_ja_text(tokens, token.get("t", ""))
    return tokens


def chapter_title_text(source: dict[str, Any], lang: str) -> str:
    reference = source.get("reference", {})
    if lang == "en":
        return str(source.get("chapter_title_en") or f"Chapter {source['chapter_number']}")
    if lang == "zh":
        ref = reference.get("zh_primary") or {}
        return str(ref.get("chapter") or f"第{source['chapter_number']}章")
    ref = reference.get("ja") or {}
    return str(ref.get("chapter") or f"第{source['chapter_number']}章")


def promote_plain_chunk(source: dict[str, Any], plain: dict[str, Any]) -> dict[str, Any]:
    spine_lang = source_spine_lang(source)
    source_paragraphs = {paragraph["id"]: paragraph for paragraph in source["paragraphs"]}
    unit_plan_by_paragraph = {paragraph["id"]: paragraph["units"] for paragraph in source_unit_plan(source)}
    strict = {
        "schema_version": "0.1",
        "mode": "trilingual_standard",
        "chunk_id": source["chunk_id"],
        "chapter": {
            "id": source["chapter_id"],
            "number": source["chapter_number"],
            "title": {
                "en": tokenize_en(chapter_title_text(source, "en")),
                "zh": tokenize_zh(chapter_title_text(source, "zh")),
                "ja": tokenize_ja(chapter_title_text(source, "ja")),
            },
        },
        "paragraphs": [],
    }
    for paragraph in plain.get("paragraphs", []):
        paragraph_id = paragraph["id"]
        source_paragraph = source_paragraphs[paragraph_id]
        source_units = unit_plan_by_paragraph[paragraph_id]
        source_units_by_id = {unit["unit_id"]: unit for unit in source_units}
        strict_paragraph = {
            "id": paragraph_id,
            "source_en": source_paragraph.get("en", ""),
            "units": [],
        }
        if source_paragraph.get("zh"):
            strict_paragraph["source_zh"] = source_paragraph["zh"]
        if source_paragraph.get("ja"):
            strict_paragraph["source_ja"] = source_paragraph["ja"]
        generated_en_parts: list[str] = []
        plain_units = paragraph.get("units", [])
        for unit_index, unit in enumerate(plain_units):
            source_unit = source_units_by_id[unit["unit_id"]]
            if spine_lang == "en":
                en = str(source_unit.get("en", "")) or plain_text(unit.get("en", ""))
            else:
                en = plain_text(source_unit.get("en", "")) or plain_text(unit.get("en", ""))
            if not source_paragraph.get("en") and unit_index < len(plain_units) - 1 and not en.endswith(" "):
                en = en + " "
            zh = plain_text(source_unit.get("zh", "")) if spine_lang == "zh" else plain_text(unit.get("zh", ""))
            ja = plain_text(source_unit.get("ja", "")) if spine_lang == "ja" else plain_text(unit.get("ja", ""))
            generated_en_parts.append(en)
            strict_unit = {
                "source_en": en,
                "en": tokenize_en(en),
                "zh": tokenize_zh(zh),
                "ja": tokenize_ja(ja),
            }
            if source_unit.get("zh"):
                strict_unit["source_zh"] = source_unit["zh"]
            if source_unit.get("ja"):
                strict_unit["source_ja"] = source_unit["ja"]
            strict_paragraph["units"].append(strict_unit)
        if not strict_paragraph["source_en"]:
            strict_paragraph["source_en"] = "".join(part for part in generated_en_parts if part).strip()
        strict["paragraphs"].append(strict_paragraph)
    return strict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--canonical-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--claim-ttl-seconds", type=int, default=21600)
    parser.add_argument("--codex-timeout-seconds", type=int, default=7200)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    cwd = Path.cwd()
    chunks = load_chunks(Path(args.chunks_jsonl))
    canonical_dir = Path(args.canonical_dir)
    candidate_dir = Path(args.candidate_dir)
    work_dir = Path(args.work_dir)
    claim_dir = candidate_dir / "claims"
    accepted_dir = candidate_dir / "accepted"
    plain_dir = candidate_dir / "plain-accepted"
    rejected_dir = candidate_dir / "rejected"
    failed_dir = candidate_dir / "failed"
    status_dir = candidate_dir / "status"
    for path in (claim_dir, accepted_dir, plain_dir, rejected_dir, failed_dir, status_dir, canonical_dir, work_dir):
        path.mkdir(parents=True, exist_ok=True)

    completed = 0
    failed = 0
    while True:
        claimed: tuple[int, dict[str, Any]] | None = None
        for item in iter_selected(chunks, args.start_index, args.end_index):
            _index, chunk = item
            chunk_id = chunk["chunk_id"]
            canonical_path = canonical_dir / f"{chunk_id}.json"
            candidate_path = accepted_dir / f"{chunk_id}.json"
            if valid_existing(canonical_path, chunk) or valid_existing(candidate_path, chunk):
                continue
            if not args.retry_failed and (failed_dir / f"{chunk_id}.json").exists():
                continue
            if claim_chunk(claim_dir, chunk_id, args.worker_id, args.claim_ttl_seconds):
                if args.retry_failed:
                    (failed_dir / f"{chunk_id}.json").unlink(missing_ok=True)
                claimed = item
                break
        if claimed is None:
            print(f"{args.worker_id}: no claimable chunks; accepted={completed} failed={failed}", flush=True)
            return 0

        _index, chunk = claimed
        chunk_id = chunk["chunk_id"]
        canonical_path = canonical_dir / f"{chunk_id}.json"
        candidate_path = accepted_dir / f"{chunk_id}.json"
        errors: list[str] | None = None
        try:
            for attempt in range(1, args.retries + 2):
                if valid_existing(canonical_path, chunk) or valid_existing(candidate_path, chunk):
                    completed += 1
                    break
                prompt = prompt_for_plain_chunk(chunk, errors)
                prompt_path = work_dir / "prompts" / f"{chunk_id}.attempt{attempt}.md"
                message_path = work_dir / "messages" / f"{chunk_id}.attempt{attempt}.md"
                log_path = work_dir / "logs" / f"{chunk_id}.log"
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(prompt, encoding="utf-8")
                print(f"{args.worker_id}: codex plain trilingual {chunk_id} attempt {attempt}", flush=True)
                result: dict[str, Any] | None = None
                strict: dict[str, Any] | None = None
                try:
                    run_codex(
                        prompt,
                        message_path,
                        log_path,
                        first=True,
                        model=args.model,
                        reasoning=args.reasoning,
                        cwd=cwd,
                        timeout_seconds=args.codex_timeout_seconds,
                    )
                    result = extract_json(message_path.read_text(encoding="utf-8"))
                    errors = validate_plain_chunk(chunk, result)
                    if not errors:
                        strict = promote_plain_chunk(chunk, result)
                        errors = validate_chunk(chunk, strict)
                except Exception as exc:
                    if mentions_usage_limit(str(exc)):
                        write_json(status_dir / f"{chunk_id}.json", status_record("usage_limit", worker_id=args.worker_id, attempt=attempt))
                        print(f"{args.worker_id}: usage limit detected; stopping worker", flush=True)
                        return 86
                    errors = [f"codex, parse, promote, or validate step failed: {exc}"]
                if errors:
                    print(f"{args.worker_id}: validation failed {chunk_id}: {'; '.join(errors[:12])}", flush=True)
                    reject_path = rejected_dir / f"{chunk_id}.{args.worker_id}.attempt{attempt}.json"
                    if result is not None:
                        write_json(reject_path, result)
                    else:
                        reject_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
                    write_json(status_dir / f"{chunk_id}.json", status_record("attempt_failed", worker_id=args.worker_id, attempt=attempt, errors=errors[:80]))
                    continue
                if result is not None:
                    write_json(plain_dir / f"{chunk_id}.json", result)
                tmp_path = candidate_path.with_suffix(f".{args.worker_id}.tmp")
                tmp_path.write_text(json.dumps(strict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                tmp_path.replace(candidate_path)
                write_json(status_dir / f"{chunk_id}.json", status_record("accepted", worker_id=args.worker_id, attempt=attempt))
                print(f"{args.worker_id}: accepted candidate {chunk_id}", flush=True)
                completed += 1
                break
            else:
                write_json(failed_dir / f"{chunk_id}.json", status_record("failed", worker_id=args.worker_id, attempts=args.retries + 1, errors=(errors or [])[:80]))
                failed += 1
        finally:
            release_claim(claim_dir, chunk_id)
        if args.max_chunks and completed >= args.max_chunks:
            print(f"{args.worker_id}: max chunks reached ({args.max_chunks})", flush=True)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
