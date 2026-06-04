#!/usr/bin/env python3
"""Assemble trilingual chunk JSON files into one book JSON."""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pykakasi
from pypinyin import Style, pinyin

from validate_trilingual_interlinear_json import validate_chunk


HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SINGLE_HAN_RE = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")
KAKASI = pykakasi.kakasi()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_chunks_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def plain_title(text: str) -> list[dict[str, str]]:
    return [{"t": text}]


def tokenize_zh_title(text: str) -> list[dict[str, str]]:
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
    return tokens or plain_title(text)


def append_ja_text(tokens: list[dict[str, str]], text: str) -> None:
    if not text:
        return
    if tokens and "r" not in tokens[-1]:
        tokens[-1]["t"] += text
    else:
        tokens.append({"t": text})


def tokenize_ja_title(text: str) -> list[dict[str, str]]:
    tokens: list[dict[str, str]] = []
    try:
        segments = KAKASI.convert(str(text))
    except Exception:
        segments = [{"orig": str(text), "hira": ""}]
    for segment in segments:
        orig = str(segment.get("orig") or "")
        hira = str(segment.get("hira") or "")
        if not HAN_RE.search(orig):
            append_ja_text(tokens, orig)
            continue
        kanji_count = sum(1 for char in orig if SINGLE_HAN_RE.fullmatch(char))
        reading_parts = [hira] if kanji_count == 1 and hira else (list(hira) if len(hira) >= kanji_count else [])
        reading_index = 0
        for char in orig:
            if SINGLE_HAN_RE.fullmatch(char):
                if reading_parts:
                    reading = reading_parts[min(reading_index, len(reading_parts) - 1)]
                else:
                    reading = str(KAKASI.convert(char)[0].get("hira") or "よみ")
                tokens.append({"t": char, "r": reading})
                reading_index += 1
            else:
                append_ja_text(tokens, char)
    return tokens or plain_title(text)


def title_tokens(manifest: dict[str, Any], lang: str) -> list[dict[str, str]]:
    text = str(manifest.get(f"book_title_{lang}") or "")
    if lang == "en":
        return plain_title(text or "Untitled")
    if lang == "zh":
        return tokenize_zh_title(text or "未命名")
    return tokenize_ja_title(text or "無題")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    chunk_sources = load_chunks_jsonl(Path(args.chunks_jsonl))
    chunk_dir = Path(args.chunk_dir)
    chapters: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    missing_chunks: list[str] = []
    stale_chunks: list[dict[str, Any]] = []
    assembled_count = 0

    for source in chunk_sources:
        chunk_id = source["chunk_id"]
        chunk_path = chunk_dir / f"{chunk_id}.json"
        if not chunk_path.exists():
            if args.allow_missing:
                missing_chunks.append(chunk_id)
                continue
            raise FileNotFoundError(chunk_path)
        chunk = load_json(chunk_path)
        errors = validate_chunk(source, chunk)
        if errors:
            if args.allow_missing:
                stale_chunks.append({"chunk_id": chunk_id, "errors": errors})
                continue
            raise ValueError(f"{chunk_path}: " + "; ".join(errors[:40]))
        assembled_count += 1
        chapter_source = chunk["chapter"]
        chapter_id = chapter_source["id"]
        chapter = chapters.setdefault(
            chapter_id,
            {
                "id": chapter_id,
                "number": source["chapter_number"],
                "title": chapter_source["title"],
                "paragraphs": [],
            },
        )
        chapter["paragraphs"].extend(chunk["paragraphs"])

    if assembled_count == 0:
        raise RuntimeError("no chunk JSON files were assembled")

    source_note = str(
        manifest.get("source_note")
        or (
            "English is the alignment spine. Chinese and Japanese use supplied source/reference windows "
            "where available; missing target-language rows are generated from the spine and references."
        )
    )
    book = {
        "schema_version": "0.1",
        "mode": "trilingual_standard",
        "title": {
            "en": title_tokens(manifest, "en"),
            "zh": title_tokens(manifest, "zh"),
            "ja": title_tokens(manifest, "ja"),
        },
        "author": {
            "name": manifest.get("author", ""),
            "reading_ja": manifest.get("author_reading_ja", ""),
        },
        "source": {
            "source_paths": manifest.get("source_paths", {}),
            "source_sha256": manifest.get("source_sha256", {}),
            "assembled_chunk_count": assembled_count,
            "total_chunk_count": manifest.get("chunk_count", 0),
            "missing_chunk_count": len(missing_chunks),
            "missing_chunks": missing_chunks,
            "stale_chunk_count": len(stale_chunks),
            "stale_chunks": stale_chunks,
            "note": source_note,
        },
        "chapters": list(chapters.values()),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
