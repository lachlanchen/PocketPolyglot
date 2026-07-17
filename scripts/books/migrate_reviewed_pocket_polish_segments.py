#!/usr/bin/env python3
"""Promote valid legacy reviewed outputs into content-addressed segment cache."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex_pocket_polish_worker import (
    salvage_reviewed_chunk_segments,
    save_cached_segment,
)
from pocket_polished_common import (
    OUTPUT_ROOT,
    read_json,
    read_jsonl,
    validate_segment_output,
)


def migrate_book(book_id: str) -> tuple[int, int, int]:
    root = OUTPUT_ROOT / book_id
    tasks_path = root / "tasks/chunks.jsonl"
    if not tasks_path.is_file():
        return 0, 0, 0
    tasks = read_jsonl(tasks_path)
    promoted = 0
    reviewed = 0
    for task in tasks:
        output = root / "json" / f"{task['chunk_id']}.json"
        review = root / "review" / f"{task['chunk_id']}.json"
        if not output.is_file() or not review.is_file():
            continue
        reviewed += 1
        promoted += salvage_reviewed_chunk_segments(task, output, root)

    # A pipeline upgrade can replace sequential segment IDs or chunk
    # boundaries while retaining exactly the same source segments.  Recover
    # accepted legacy rows by immutable source hash, but only when that hash is
    # unique in the current manifest and the migrated row passes the current
    # deterministic validator.  Ambiguous or changed source is never guessed.
    current_by_hash: dict[str, list[tuple[dict, dict]]] = {}
    for task in tasks:
        for source in task.get("segments", []):
            source_hash = source.get("source_sha256")
            if isinstance(source_hash, str):
                current_by_hash.setdefault(source_hash, []).append((task, source))

    hash_promoted = 0
    for output_path in sorted((root / "json").glob("*.json")):
        review_path = root / "review" / output_path.name
        try:
            candidate = read_json(output_path)
            review = read_json(review_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(review, dict) or not review.get("accept"):
            continue
        rows = candidate.get("segments") if isinstance(candidate, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            source_hash = row.get("source_sha256")
            matches = current_by_hash.get(source_hash, [])
            if len(matches) != 1:
                continue
            task, source = matches[0]
            cache_path = root / "work/accepted-segments" / f"{source['segment_id']}.json"
            if cache_path.exists():
                continue
            migrated = dict(row)
            migrated["segment_id"] = source["segment_id"]
            migrated["source_sha256"] = source["source_sha256"]
            if validate_segment_output(task, source, migrated):
                continue
            save_cached_segment(
                task,
                source,
                migrated,
                {
                    "accept": True,
                    "issues": review.get("issues", []),
                    "summary": "Migrated from positively reviewed legacy output by unique source hash.",
                    "source_review": str(review_path),
                },
                root,
            )
            hash_promoted += 1
    return promoted, reviewed, hash_promoted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id", nargs="+")
    args = parser.parse_args()
    for book_id in args.book_id:
        promoted, reviewed, hash_promoted = migrate_book(book_id)
        print(
            f"{book_id}: promoted_segments={promoted} "
            f"hash_promoted_segments={hash_promoted} reviewed_chunks={reviewed}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
