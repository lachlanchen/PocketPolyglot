#!/usr/bin/env python3
"""Split a quadrilingual manifest into contiguous part manifests."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chunk_ranges(chunks: list[dict[str, Any]], part_count: int) -> list[list[dict[str, Any]]]:
    if part_count < 1:
        raise ValueError("part_count must be positive")
    target = max(1, round(len(chunks) / part_count))
    parts: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        current.append(chunk)
        next_chunk = chunks[index + 1] if index + 1 < len(chunks) else None
        at_chapter_boundary = next_chunk is None or next_chunk.get("chapter_id") != chunk.get("chapter_id")
        remaining_parts = part_count - len(parts) - 1
        remaining_chunks = len(chunks) - index - 1
        should_close = (
            len(current) >= target
            and at_chapter_boundary
            and remaining_parts > 0
            and remaining_chunks >= remaining_parts
        )
        if should_close:
            parts.append(current)
            current = []
    if current:
        parts.append(current)
    while len(parts) > part_count:
        tail = parts.pop()
        parts[-1].extend(tail)
    return parts


def title_for(chunks_by_id: dict[str, dict[str, Any]], chunk_id: str, key: str) -> str:
    source = chunks_by_id.get(chunk_id, {})
    return str(source.get(key) or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--chunks-jsonl", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--part-count", required=True, type=int)
    parser.add_argument("--source-manifest", default="")
    parser.add_argument("--source-chunks-jsonl", default="")
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    sources = load_jsonl(args.chunks_jsonl)
    manifest_ids = [
        item.get("chunk_id") if isinstance(item, dict) else item
        for item in manifest.get("chunks", [])
    ]
    if manifest_ids:
        id_set = set(manifest_ids)
        sources = [source for source in sources if source.get("chunk_id") in id_set]
    source_by_id = {source["chunk_id"]: source for source in sources}
    source_manifest = args.source_manifest or args.manifest.as_posix()
    source_chunks_jsonl = args.source_chunks_jsonl or args.chunks_jsonl.as_posix()

    parts = chunk_ranges(sources, args.part_count)
    for part_number, part_chunks in enumerate(parts, start=1):
        first = part_chunks[0]
        last = part_chunks[-1]
        part_manifest = deepcopy(manifest)
        part_manifest["chunk_count"] = len(part_chunks)
        part_manifest["chunks"] = [
            {
                "chunk_id": chunk["chunk_id"],
                "chapter_number": chunk.get("chapter_number"),
            }
            for chunk in part_chunks
        ]
        part_manifest["part"] = {
            "part_number": part_number,
            "part_count": len(parts),
            "start_index": source_by_id[first["chunk_id"]].get("index", part_number),
            "end_index": source_by_id[last["chunk_id"]].get("index", part_number),
            "first_chunk_id": first["chunk_id"],
            "last_chunk_id": last["chunk_id"],
            "first_chapter_number": first.get("chapter_number"),
            "last_chapter_number": last.get("chapter_number"),
            "first_chapter_title_wenyan": title_for(source_by_id, first["chunk_id"], "chapter_title_wenyan"),
            "last_chapter_title_wenyan": title_for(source_by_id, last["chunk_id"], "chapter_title_wenyan"),
            "source_manifest": source_manifest,
            "source_chunks_jsonl": source_chunks_jsonl,
        }
        write_json(args.output_dir / f"part-{part_number:02d}" / "manifest.json", part_manifest)
        print(
            f"part-{part_number:02d}: chunks={len(part_chunks)} "
            f"{first['chunk_id']}..{last['chunk_id']} "
            f"chapters={first.get('chapter_number')}..{last.get('chapter_number')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
