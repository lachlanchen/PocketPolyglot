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
FOOTNOTE_RE = re.compile(r"\[[0-9０-９]+\]|\[\\\[[0-9０-９]+\\\]\]\([^)]*\)")


def normalize_title(title: str) -> str:
    title = FOOTNOTE_RE.sub("", title or "")
    title = re.sub(r"\s+", " ", title)
    return title.strip()


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


def title_for_scope(paragraph: dict[str, Any], scope: str) -> str:
    if scope == "chapter":
        return normalize_title(paragraph.get("story_title", ""))
    if scope == "subsection":
        return normalize_title(paragraph.get("subsection_title", ""))
    if scope == "section":
        return normalize_title(paragraph.get("section_title", ""))
    raise ValueError(f"unknown reference scope: {scope}")


def mapped_reference_keys(chunk: dict[str, Any], reference_scope: str, title_map: dict[str, Any]) -> list[str]:
    direct = reference_key(chunk, reference_scope)
    title = title_for_scope(chunk, reference_scope)
    normalized_map = {normalize_title(key): value for key, value in title_map.items()}
    mapped = normalized_map.get(title, [])
    if isinstance(mapped, str):
        mapped_titles = [mapped]
    elif isinstance(mapped, list):
        mapped_titles = [str(item) for item in mapped]
    else:
        mapped_titles = []

    keys = [direct]
    if reference_scope in {"chapter", "subsection"}:
        prefix = f"{part_index(chunk.get('subsection_title', ''))}:"
        keys.extend(f"{prefix}{mapped_title}" for mapped_title in mapped_titles)
    else:
        keys.extend(mapped_titles)
    return keys


def attach_japanese_reference(
    chunks: list[dict[str, Any]],
    jp_paragraphs: list[dict[str, Any]],
    reference_scope: str,
    title_map: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    title_map = title_map or {}
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
        refs: list[dict[str, Any]] = []
        resolved_key = key
        for candidate_key in mapped_reference_keys(chunk, reference_scope, title_map):
            refs = jp_by_reference.get(candidate_key, [])
            if refs:
                resolved_key = candidate_key
                break
        item = dict(chunk)
        item["paired_story_key"] = chapter_key(chunk)
        item["paired_reference_key"] = key
        item["resolved_jp_reference_key"] = resolved_key
        item["jp_reference_scope"] = reference_scope
        item["jp_reference"] = refs
        item["jp_reference_char_count"] = sum(len(paragraph["text"]) for paragraph in item["jp_reference"])
        enriched.append(item)
    return enriched


def add_book_metadata(chunks: list[dict[str, Any]], metadata: dict[str, str]) -> list[dict[str, Any]]:
    if not any(metadata.values()):
        return chunks
    enriched: list[dict[str, Any]] = []
    for chunk in chunks:
        item = dict(chunk)
        for key, value in metadata.items():
            if value:
                item[key] = value
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
    parser.add_argument("--book-title-zh", default="")
    parser.add_argument("--book-title-zh-reading", default="")
    parser.add_argument("--book-title-ja", default="")
    parser.add_argument("--book-title-ja-reading", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--book-description", default="")
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
    parser.add_argument(
        "--title-map-json",
        help="optional JSON object mapping Chinese section/subsection/story titles to Japanese titles",
    )
    args = parser.parse_args()

    zh_markdown = Path(args.zh_markdown)
    ja_markdown = Path(args.ja_markdown)
    title_map = json.loads(Path(args.title_map_json).read_text(encoding="utf-8")) if args.title_map_json else {}
    zh_paragraphs = parse_markdown(zh_markdown, f"{args.book_id}-zh")
    ja_paragraphs = parse_markdown(ja_markdown, f"{args.book_id}-ja")
    chunks = add_book_metadata(
        attach_japanese_reference(
            make_chunks(zh_paragraphs, args.book_id, args.max_chars, chunk_mode=args.chunk_mode),
            ja_paragraphs,
            args.reference_scope,
            title_map,
        ),
        {
            "book_title_zh": args.book_title_zh,
            "book_title_zh_reading": args.book_title_zh_reading,
            "book_title_ja": args.book_title_ja,
            "book_title_ja_reading": args.book_title_ja_reading,
            "author": args.author,
            "book_description": args.book_description,
        },
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
        "title_map_json": str(Path(args.title_map_json)) if args.title_map_json else "",
        "chunk_count": len(chunks),
        "chunks_jsonl": str(chunks_path),
        "missing_jp_reference_chunks": missing_reference,
        "book_title_zh": args.book_title_zh,
        "book_title_zh_reading": args.book_title_zh_reading,
        "book_title_ja": args.book_title_ja,
        "book_title_ja_reading": args.book_title_ja_reading,
        "author": args.author,
        "book_description": args.book_description,
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
