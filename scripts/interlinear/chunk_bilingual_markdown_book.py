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


def chapter_key(paragraph: dict[str, Any]) -> str:
    return f"{part_index(paragraph.get('subsection_title', ''))}:{paragraph.get('story_title', '').strip()}"


def reference_key(paragraph: dict[str, Any], scope: str) -> str:
    if scope == "chapter":
        return chapter_key(paragraph)
    if scope == "subsection":
        return f"{part_index(paragraph.get('subsection_title', ''))}:{paragraph.get('subsection_title', '').strip()}"
    if scope == "section":
        return paragraph.get("section_title", "").strip()
    raise ValueError(f"unknown reference scope: {scope}")


def attach_japanese_reference(
    chunks: list[dict[str, Any]], jp_paragraphs: list[dict[str, Any]], reference_scope: str
) -> list[dict[str, Any]]:
    jp_by_reference: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paragraph in jp_paragraphs:
        jp_by_reference[reference_key(paragraph, reference_scope)].append(
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
        key = reference_key(chunk, reference_scope)
        item = dict(chunk)
        item["paired_story_key"] = chapter_key(chunk)
        item["paired_reference_key"] = key
        item["jp_reference_scope"] = reference_scope
        item["jp_reference"] = jp_by_reference.get(key, [])
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
    parser.add_argument(
        "--chunk-mode",
        choices=["paragraph", "size"],
        default="paragraph",
        help="paragraph creates one LLM task per Chinese source paragraph; size groups paragraphs up to --max-chars",
    )
    parser.add_argument(
        "--reference-scope",
        choices=["chapter", "subsection", "section"],
        default="chapter",
        help="amount of Japanese original context attached to each Chinese chunk",
    )
    args = parser.parse_args()

    zh_markdown = Path(args.zh_markdown)
    ja_markdown = Path(args.ja_markdown)
    zh_paragraphs = parse_markdown(zh_markdown, f"{args.book_id}-zh")
    ja_paragraphs = parse_markdown(ja_markdown, f"{args.book_id}-ja")
    chunks = attach_japanese_reference(
        make_chunks(zh_paragraphs, args.book_id, args.max_chars, chunk_mode=args.chunk_mode),
        ja_paragraphs,
        args.reference_scope,
    )

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
        "chunk_mode": args.chunk_mode,
        "max_chars": args.max_chars if args.chunk_mode == "size" else None,
        "jp_reference_scope": args.reference_scope,
        "chunk_count": len(chunks),
        "chunks_jsonl": str(chunks_path),
        "missing_jp_reference_chunks": missing_reference,
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "story_id": chunk["story_id"],
                "paired_story_key": chunk["paired_story_key"],
                "paired_reference_key": chunk["paired_reference_key"],
                "jp_reference_scope": chunk["jp_reference_scope"],
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
