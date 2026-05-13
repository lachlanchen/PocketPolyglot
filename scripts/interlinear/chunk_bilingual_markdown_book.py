#!/usr/bin/env python3
"""Split Chinese Markdown chunks and attach Japanese source references."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from chunk_markdown_book import make_chunks, parse_markdown


PART_ORDER = {"上": 1, "中": 2, "下": 3}


def part_index(title: str) -> int:
    match = re.match(r"\s*([上中下])", title or "")
    if not match:
        return 0
    return PART_ORDER[match.group(1)]


def story_key(paragraph: dict[str, Any]) -> str:
    return f"{part_index(paragraph.get('subsection_title', ''))}:{paragraph.get('story_title', '').strip()}"


def attach_japanese_reference(
    chunks: list[dict[str, Any]], jp_paragraphs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    jp_by_story: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paragraph in jp_paragraphs:
        jp_by_story[story_key(paragraph)].append(
            {
                "id": paragraph["id"],
                "section_title": paragraph["section_title"],
                "subsection_title": paragraph["subsection_title"],
                "story_title": paragraph["story_title"],
                "text": paragraph["text"],
            }
        )

    enriched: list[dict[str, Any]] = []
    for chunk in chunks:
        key = story_key(chunk)
        item = dict(chunk)
        item["paired_story_key"] = key
        item["jp_reference"] = jp_by_story.get(key, [])
        item["jp_reference_char_count"] = sum(len(paragraph["text"]) for paragraph in item["jp_reference"])
        enriched.append(item)
    return enriched


def combined_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zh-markdown", required=True)
    parser.add_argument("--ja-markdown", required=True)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--max-chars", type=int, default=1400)
    args = parser.parse_args()

    zh_markdown = Path(args.zh_markdown)
    ja_markdown = Path(args.ja_markdown)
    zh_paragraphs = parse_markdown(zh_markdown, f"{args.book_id}-zh")
    ja_paragraphs = parse_markdown(ja_markdown, f"{args.book_id}-ja")
    chunks = attach_japanese_reference(make_chunks(zh_paragraphs, args.book_id, args.max_chars), ja_paragraphs)

    missing_reference = [chunk["chunk_id"] for chunk in chunks if not chunk["jp_reference"]]

    chunks_path = Path(args.chunks_jsonl)
    manifest_path = Path(args.manifest)
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")

    manifest = {
        "book_id": args.book_id,
        "mode": "bilingual_source",
        "zh_markdown": str(zh_markdown),
        "ja_markdown": str(ja_markdown),
        "source_sha256": combined_sha256([zh_markdown, ja_markdown]),
        "source_sha256_zh": hashlib.sha256(zh_markdown.read_bytes()).hexdigest(),
        "source_sha256_ja": hashlib.sha256(ja_markdown.read_bytes()).hexdigest(),
        "paragraph_count": len(zh_paragraphs),
        "jp_paragraph_count": len(ja_paragraphs),
        "chunk_count": len(chunks),
        "chunks_jsonl": str(chunks_path),
        "missing_jp_reference_chunks": missing_reference,
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "story_id": chunk["story_id"],
                "paired_story_key": chunk["paired_story_key"],
                "paragraph_ids": [paragraph["id"] for paragraph in chunk["paragraphs"]],
                "jp_reference_ids": [paragraph["id"] for paragraph in chunk["jp_reference"]],
            }
            for chunk in chunks
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"zh_paragraphs={len(zh_paragraphs)} ja_paragraphs={len(ja_paragraphs)} chunks={len(chunks)}")
    if missing_reference:
        print(f"warning: {len(missing_reference)} chunks have no Japanese reference")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
