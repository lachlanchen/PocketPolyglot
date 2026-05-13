#!/usr/bin/env python3
"""Split cleaned Markdown into ordered paragraph chunks for LLM conversion."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def slugify(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", "-", text.strip())
    cleaned = re.sub(r"[^\w\-\u4e00-\u9fffぁ-ゟ゠-ヿ一-龯]+", "", cleaned)
    return cleaned[:48] or fallback


def parse_markdown(path: Path, book_id: str) -> list[dict[str, Any]]:
    section = {"id": "front", "title": "前言"}
    subsection = {"id": "front", "title": ""}
    story = {"id": "front", "title": "前言", "index": 0}
    story_index = 0
    paragraph_index = 0
    buffer: list[str] = []
    paragraphs: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal paragraph_index
        text = " ".join(part.strip() for part in buffer if part.strip()).strip()
        buffer.clear()
        if not text:
            return
        paragraph_index += 1
        paragraphs.append(
            {
                "id": f"{book_id}-p{paragraph_index:05d}",
                "section_id": section["id"],
                "section_title": section["title"],
                "subsection_id": subsection["id"],
                "subsection_title": subsection["title"],
                "story_id": story["id"],
                "story_title": story["title"],
                "story_index": story["index"],
                "text": text,
            }
        )

    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            if level == 1:
                section = {"id": slugify(title, f"section-{len(paragraphs) + 1}"), "title": title}
                subsection = {"id": "main", "title": ""}
                story_index += 1
                story = {"id": f"{section['id']}-intro", "title": title, "index": story_index}
            elif level == 2:
                subsection = {"id": slugify(title, f"subsection-{len(paragraphs) + 1}"), "title": title}
                story_index += 1
                story = {"id": f"{section['id']}-{subsection['id']}-intro", "title": title, "index": story_index}
            else:
                story_index += 1
                story = {
                    "id": f"{section['id']}-{subsection['id']}-{slugify(title, f'chapter-{story_index}')}",
                    "title": title,
                    "index": story_index,
                }
            continue
        if line.strip():
            buffer.append(line.strip())
        else:
            flush()
    flush()
    return paragraphs


def make_chunks(paragraphs: list[dict[str, Any]], book_id: str, max_chars: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    current_path: tuple[str, str, str] | None = None

    def flush() -> None:
        nonlocal current, current_chars, current_path
        if not current:
            return
        first = current[0]
        chunks.append(
            {
                "chunk_id": f"{book_id}-chunk-{len(chunks) + 1:04d}",
                "section_id": first["section_id"],
                "section_title": first["section_title"],
                "subsection_id": first["subsection_id"],
                "subsection_title": first["subsection_title"],
                "story_id": first["story_id"],
                "story_title": first["story_title"],
                "story_index": first["story_index"],
                "paragraphs": current,
            }
        )
        current = []
        current_chars = 0
        current_path = None

    for paragraph in paragraphs:
        path = (paragraph["section_id"], paragraph["subsection_id"], paragraph["story_id"])
        size = len(paragraph["text"])
        if current and (path != current_path or current_chars + size > max_chars):
            flush()
        current.append(paragraph)
        current_chars += size
        current_path = path
    flush()
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", help="cleaned Markdown input")
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--max-chars", type=int, default=1800)
    args = parser.parse_args()

    markdown = Path(args.markdown)
    paragraphs = parse_markdown(markdown, args.book_id)
    chunks = make_chunks(paragraphs, args.book_id, args.max_chars)

    chunks_path = Path(args.chunks_jsonl)
    manifest_path = Path(args.manifest)
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path.write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")

    manifest = {
        "book_id": args.book_id,
        "markdown": str(markdown),
        "source_sha256": hashlib.sha256(markdown.read_bytes()).hexdigest(),
        "paragraph_count": len(paragraphs),
        "chunk_count": len(chunks),
        "chunks_jsonl": str(chunks_path),
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "story_id": chunk["story_id"],
                "paragraph_ids": [paragraph["id"] for paragraph in chunk["paragraphs"]],
            }
            for chunk in chunks
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"paragraphs={len(paragraphs)} chunks={len(chunks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
