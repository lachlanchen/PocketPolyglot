#!/usr/bin/env python3
"""Promote valid legacy reviewed outputs into content-addressed segment cache."""

from __future__ import annotations

import argparse
from pathlib import Path

from codex_pocket_polish_worker import salvage_reviewed_chunk_segments
from pocket_polished_common import OUTPUT_ROOT, read_jsonl


def migrate_book(book_id: str) -> tuple[int, int]:
    root = OUTPUT_ROOT / book_id
    tasks_path = root / "tasks/chunks.jsonl"
    if not tasks_path.is_file():
        return 0, 0
    promoted = 0
    reviewed = 0
    for task in read_jsonl(tasks_path):
        output = root / "json" / f"{task['chunk_id']}.json"
        review = root / "review" / f"{task['chunk_id']}.json"
        if not output.is_file() or not review.is_file():
            continue
        reviewed += 1
        promoted += salvage_reviewed_chunk_segments(task, output, root)
    return promoted, reviewed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_id", nargs="+")
    args = parser.parse_args()
    for book_id in args.book_id:
        promoted, reviewed = migrate_book(book_id)
        print(f"{book_id}: promoted_segments={promoted} reviewed_chunks={reviewed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
