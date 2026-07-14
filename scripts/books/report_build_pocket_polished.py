#!/usr/bin/env python3
"""Report validated coverage and model-call amplification for polished books."""

from __future__ import annotations

import argparse
from pathlib import Path

from pocket_polished_common import (
    OUTPUT_ROOT,
    read_json,
    read_jsonl,
    validate_chunk_output,
)


def book_report(book_id: str) -> dict[str, int | str]:
    root = OUTPUT_ROOT / book_id
    tasks = read_jsonl(root / "tasks/chunks.jsonl")
    valid = 0
    invalid = 0
    for task in tasks:
        path = root / "json" / f"{task['chunk_id']}.json"
        if not path.exists():
            continue
        try:
            errors = validate_chunk_output(task, read_json(path))
        except (OSError, ValueError):
            errors = ["unreadable output"]
        if errors:
            invalid += 1
        else:
            valid += 1

    metrics = []
    for path in (root / "work/metrics").glob("*.json"):
        try:
            payload = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            metrics.append(payload)
    return {
        "book_id": book_id,
        "valid": valid,
        "total": len(tasks),
        "invalid": invalid,
        "writer_calls": sum(int(row.get("writer_calls", 0) or 0) for row in metrics),
        "reviewer_calls": sum(int(row.get("reviewer_calls", 0) or 0) for row in metrics),
        "writer_tokens": sum(int(row.get("writer_tokens", 0) or 0) for row in metrics),
        "reviewer_tokens": sum(int(row.get("reviewer_tokens", 0) or 0) for row in metrics),
        "cache_hits": sum(int(row.get("cache_hits", 0) or 0) for row in metrics),
        "retried_chunks": sum(
            int(row.get("writer_calls", 0) or 0) > 1
            or int(row.get("reviewer_calls", 0) or 0) > 1
            for row in metrics
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queue",
        type=Path,
        default=OUTPUT_ROOT / "tasks/queue.json",
    )
    parser.add_argument("--book-id", action="append", default=[])
    args = parser.parse_args()

    if args.book_id:
        book_ids = args.book_id
    else:
        queue = read_json(args.queue)
        book_ids = [row["book_id"] for row in queue.get("books", [])]

    print(
        "book_id\tvalid/total\tinvalid\twriter_calls\treviewer_calls\t"
        "retried_chunks\tcache_hits\treported_tokens"
    )
    for book_id in book_ids:
        row = book_report(book_id)
        tokens = int(row["writer_tokens"]) + int(row["reviewer_tokens"])
        print(
            f"{book_id}\t{row['valid']}/{row['total']}\t{row['invalid']}\t"
            f"{row['writer_calls']}\t{row['reviewer_calls']}\t"
            f"{row['retried_chunks']}\t{row['cache_hits']}\t{tokens}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
