#!/usr/bin/env python3
"""Assemble validated chunk JSON files into one interlinear book JSON."""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any


HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SPLIT_READING_RE = re.compile(r"[\s/／・,，]+")


def reading_parts_for_text(text: str, reading: str) -> list[str]:
    parts = [part for part in SPLIT_READING_RE.split(reading.strip()) if part]
    han_count = len(HAN_RE.findall(text))
    if len(parts) == 1 and han_count > 1 and len(text) == han_count and len(parts[0]) == han_count:
        return list(parts[0])
    return parts


def plain_tokens(text: str, reading: str = "", *, reading_only_for_han: bool = False) -> list[dict[str, str]]:
    if not text:
        return []
    if reading_only_for_han and not HAN_RE.search(text):
        reading = ""
    reading_parts = reading_parts_for_text(text, reading)
    part_index = 0
    tokens: list[dict[str, str]] = []
    for char in text:
        if HAN_RE.fullmatch(char):
            token = {"t": char}
            if part_index < len(reading_parts):
                token["r"] = reading_parts[part_index]
                part_index += 1
            tokens.append(token)
            continue

        # Readings for mixed Japanese titles may include kana particles as
        # alignment hints, but ruby must not be attached to kana/punctuation.
        if part_index < len(reading_parts) and reading_parts[part_index] == char:
            part_index += 1
        tokens.append({"t": char})
    return tokens


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_chunk_errors(item: dict[str, Any], chunk: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if chunk.get("chunk_id") != item["chunk_id"]:
        errors.append(f"chunk_id is {chunk.get('chunk_id')!r}")
    expected_paragraph_ids = item.get("paragraph_ids", [])
    got_paragraph_ids = [paragraph.get("id") for paragraph in chunk.get("paragraphs", [])]
    if got_paragraph_ids != expected_paragraph_ids:
        errors.append(f"paragraph ids are stale: expected {expected_paragraph_ids}, got {got_paragraph_ids}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--book-title-zh", default="心")
    parser.add_argument("--book-title-zh-reading", default="xīn")
    parser.add_argument("--book-title-ja", default="心")
    parser.add_argument("--book-title-ja-reading", default="こころ")
    parser.add_argument("--source-markdown", required=True)
    parser.add_argument("--source-epub", required=True)
    parser.add_argument("--source-markdown-ja", default="")
    parser.add_argument("--source-epub-ja", default="")
    parser.add_argument("--allow-missing", action="store_true", help="skip missing chunk files for partial preview builds")
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    chunk_dir = Path(args.chunk_dir)

    sections: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    missing_chunks: list[str] = []
    stale_chunks: list[dict[str, Any]] = []
    assembled_chunk_count = 0
    for item in manifest["chunks"]:
        chunk_path = chunk_dir / f"{item['chunk_id']}.json"
        if not chunk_path.exists():
            if args.allow_missing:
                missing_chunks.append(item["chunk_id"])
                continue
            raise FileNotFoundError(chunk_path)
        chunk = load_json(chunk_path)
        manifest_errors = manifest_chunk_errors(item, chunk)
        if manifest_errors:
            if args.allow_missing:
                stale_chunks.append({"chunk_id": item["chunk_id"], "errors": manifest_errors})
                continue
            raise ValueError(f"{chunk_path}: " + "; ".join(manifest_errors))
        assembled_chunk_count += 1

        section = chunk["section"]
        subsection = chunk["subsection"]
        story = chunk["story"]

        section_entry = sections.setdefault(
            section["id"],
            {
                "id": section["id"],
                "title_zh": section.get("title_zh") or plain_tokens(section.get("title", "")),
                "title_ja": section.get("title_ja") or plain_tokens(section.get("title", "")),
                "subsections": OrderedDict(),
            },
        )
        subsections = section_entry["subsections"]
        subsection_entry = subsections.setdefault(
            subsection["id"],
            {
                "id": subsection["id"],
                "title_zh": subsection.get("title_zh") or plain_tokens(subsection.get("title", "")),
                "title_ja": subsection.get("title_ja") or plain_tokens(subsection.get("title", "")),
                "stories": OrderedDict(),
            },
        )
        stories = subsection_entry["stories"]
        story_entry = stories.setdefault(
            story["id"],
            {
                "id": story["id"],
                "title_zh": story.get("title_zh") or plain_tokens(story.get("title", "")),
                "title_ja": story.get("title_ja") or plain_tokens(story.get("title", "")),
                "place_zh": story.get("place_zh", []),
                "place_ja": story.get("place_ja", []),
                "paragraphs": [],
            },
        )
        story_entry["paragraphs"].extend(chunk["paragraphs"])

    section_list: list[dict[str, Any]] = []
    for section in sections.values():
        subsection_list: list[dict[str, Any]] = []
        for subsection in section["subsections"].values():
            story_list = list(subsection["stories"].values())
            subsection = {**subsection, "stories": story_list}
            subsection_list.append(subsection)
        section = {**section, "subsections": subsection_list}
        section_list.append(section)

    if assembled_chunk_count == 0:
        raise RuntimeError("no chunk JSON files were assembled")

    source = {
        "source_epub": args.source_epub,
        "source_markdown": args.source_markdown,
        "source_sha256": manifest["source_sha256"],
        "paragraph_count": manifest["paragraph_count"],
        "chunk_count": assembled_chunk_count,
        "total_chunk_count": manifest["chunk_count"],
        "note": "Generated chunk by chunk from cleaned Markdown. Paragraph source_text fields are kept for validation.",
    }
    if missing_chunks:
        source["missing_chunk_count"] = len(missing_chunks)
        source["missing_chunks"] = missing_chunks
    if stale_chunks:
        source["stale_chunk_count"] = len(stale_chunks)
        source["stale_chunks"] = stale_chunks
    if args.source_markdown_ja:
        source["source_markdown_ja"] = args.source_markdown_ja
    if args.source_epub_ja:
        source["source_epub_ja"] = args.source_epub_ja
    if manifest.get("source_sha256_zh"):
        source["source_sha256_zh"] = manifest["source_sha256_zh"]
    if manifest.get("source_sha256_ja"):
        source["source_sha256_ja"] = manifest["source_sha256_ja"]
    if manifest.get("jp_paragraph_count") is not None:
        source["jp_paragraph_count"] = manifest["jp_paragraph_count"]
    if manifest.get("mode") == "bilingual_source":
        source["note"] = "Generated from Chinese Markdown while using Japanese original Markdown as the comment source. Paragraph source_text fields are kept for validation."

    data = {
        "schema_version": "0.2",
        "mode": "zh_main_ja_comment",
        "title": {
            "zh": plain_tokens(args.book_title_zh, args.book_title_zh_reading),
            "ja": plain_tokens(args.book_title_ja, args.book_title_ja_reading, reading_only_for_han=True),
        },
        "source": source,
        "sections": section_list,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
