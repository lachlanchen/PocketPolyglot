#!/usr/bin/env python3
"""Assemble quadrilingual chunk JSON files into one book JSON."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from codex_trilingual_plain_json_worker import tokenize_en, tokenize_ja, tokenize_zh
from validate_quadrilingual_interlinear_json import validate_chunk


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    sources = load_jsonl(Path(args.chunks_jsonl))
    chunk_dir = Path(args.chunk_dir)
    chapters: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    missing: list[str] = []
    stale: list[dict[str, Any]] = []
    assembled = 0
    for source in sources:
        chunk_id = source["chunk_id"]
        path = chunk_dir / f"{chunk_id}.json"
        if not path.exists():
            if args.allow_missing:
                missing.append(chunk_id)
                continue
            raise FileNotFoundError(path)
        data = load_json(path)
        errors = validate_chunk(source, data)
        if errors:
            if args.allow_missing:
                stale.append({"chunk_id": chunk_id, "errors": errors[:30]})
                continue
            raise ValueError(f"{path}: " + "; ".join(errors[:40]))
        chapter_id = source["chapter_id"]
        chapter = chapters.setdefault(
            chapter_id,
            {
                "id": chapter_id,
                "number": source["chapter_number"],
                "title": data["chapter"]["title"],
                "paragraphs": [],
            },
        )
        chapter["paragraphs"].extend(data["paragraphs"])
        assembled += 1

    if assembled == 0:
        raise RuntimeError("no chunk JSON files were assembled")
    book = {
        "schema_version": "0.1",
        "mode": "quadrilingual_wenyan_main",
        "title": {
            "wenyan": tokenize_zh(manifest.get("book_title_wenyan", "日本書紀")),
            "zh_modern": tokenize_zh(manifest.get("book_title_zh_modern", "日本书纪")),
            "ja_modern": tokenize_ja(manifest.get("book_title_ja_modern", "日本書紀")),
            "en": tokenize_en(manifest.get("book_title_en", "Nihon Shoki")),
        },
        "author": {
            "name": manifest.get("author", ""),
            "reading_zh": manifest.get("author_reading_zh", ""),
            "reading_ja": manifest.get("author_reading_ja", ""),
        },
        "source": {
            "source_paths": manifest.get("source_paths", {}),
            "source_sha256": manifest.get("source_sha256", {}),
            "assembled_chunk_count": assembled,
            "total_chunk_count": manifest.get("chunk_count", len(sources)),
            "missing_chunk_count": len(missing),
            "missing_chunks": missing,
            "stale_chunk_count": len(stale),
            "stale_chunks": stale,
            "note": "Wenyan is the canonical source stream. Modern Chinese, modern Japanese, and English are aligned overlays.",
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
