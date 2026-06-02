#!/usr/bin/env python3
"""Assemble trilingual chunk JSON files into one book JSON."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from validate_trilingual_interlinear_json import validate_chunk


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_chunks_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def plain_title(text: str) -> list[dict[str, str]]:
    return [{"t": text}]


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

    source_note = (
        "English is the alignment spine. Chinese uses both supplied Chinese translations as references. "
        "Japanese uses supplied Japanese volumes where available; later Japanese is generated from English plus Chinese references."
    )
    book = {
        "schema_version": "0.1",
        "mode": "trilingual_standard",
        "title": {
            "en": plain_title(manifest.get("book_title_en", "Gone With the Wind")),
            "zh": [{"t": "飘", "r": "piāo"}],
            "ja": [
                {"t": "風", "r": "かぜ"},
                {"t": "と", "r": ""},
                {"t": "共", "r": "とも"},
                {"t": "に", "r": ""},
                {"t": "去", "r": "さ"},
                {"t": "りぬ", "r": ""},
            ],
        },
        "author": {
            "name": manifest.get("author", "Margaret Mitchell"),
            "reading_ja": "マーガレット ミッチェル",
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
