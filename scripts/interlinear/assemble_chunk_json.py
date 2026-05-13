#!/usr/bin/env python3
"""Assemble validated chunk JSON files into one interlinear book JSON."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any


def plain_tokens(text: str, reading: str = "") -> list[dict[str, str]]:
    if not text:
        return []
    return [{"t": text, "r": reading}]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    chunk_dir = Path(args.chunk_dir)

    sections: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for item in manifest["chunks"]:
        chunk_path = chunk_dir / f"{item['chunk_id']}.json"
        chunk = load_json(chunk_path)

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

    data = {
        "schema_version": "0.2",
        "mode": "zh_main_ja_comment",
        "title": {
            "zh": plain_tokens(args.book_title_zh, args.book_title_zh_reading),
            "ja": plain_tokens(args.book_title_ja, args.book_title_ja_reading),
        },
        "source": {
            "source_epub": args.source_epub,
            "source_markdown": args.source_markdown,
            "source_sha256": manifest["source_sha256"],
            "paragraph_count": manifest["paragraph_count"],
            "chunk_count": manifest["chunk_count"],
            "note": "Generated chunk by chunk from cleaned Markdown. Paragraph source_text fields are kept for validation.",
        },
        "sections": section_list,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
