#!/usr/bin/env python3
"""Report resumable local exact/pocket conversion progress for a queue."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE = ROOT / "data/source-plan/nutstore-share-books-local-exact-queue.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pdf_pages(path: Path) -> int | None:
    result = subprocess.run(
        ["pdfinfo", str(path)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    return None


def extracted_pages(task_dir: Path) -> tuple[int, int]:
    done = 0
    shards = 0
    for status_path in sorted((task_dir / "work/marker-shards").glob("*/status.json")):
        status = read_json(status_path)
        if status.get("status") != "complete":
            continue
        start = int(status["page_start"])
        end = int(status["page_end"])
        done += end - start + 1
        shards += 1
    return done, shards


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    queue_path = args.queue if args.queue.is_absolute() else ROOT / args.queue
    queue = read_json(queue_path)
    rows: list[dict[str, Any]] = []
    for task in queue.get("tasks", []):
        book_id = str(task["book_id"])
        source = ROOT / str(task["source"])
        task_dir = ROOT / "build-pocket" / book_id
        status_path = task_dir / "review/status.json"
        status = read_json(status_path) if status_path.exists() else {}
        total_pages = pdf_pages(source) if source.suffix.lower() == ".pdf" else None
        done_pages, done_shards = extracted_pages(task_dir)
        rows.append(
            {
                "book_id": book_id,
                "status": status.get("status", "pending"),
                "extracted_pages": done_pages,
                "source_pages": total_pages,
                "completed_shards": done_shards,
                "exact_pdf": (task_dir / "exact/book.pdf").exists(),
                "pocket_pdf": (task_dir / "pocket-large-font/book.pdf").exists(),
                "reason": status.get("reason", ""),
            }
        )

    if args.json:
        print(json.dumps({"queue": str(queue_path), "books": rows}, ensure_ascii=False, indent=2))
        return 0

    print("BOOK\tSTATUS\tEXTRACTION\tEXACT\tPOCKET")
    for row in rows:
        if row["source_pages"] is None:
            extraction = "EPUB"
        else:
            extraction = f"{row['extracted_pages']}/{row['source_pages']} ({row['completed_shards']} shards)"
        print(
            f"{row['book_id']}\t{row['status']}\t{extraction}\t"
            f"{'yes' if row['exact_pdf'] else 'no'}\t{'yes' if row['pocket_pdf'] else 'no'}"
        )
        if row["reason"]:
            print(f"  reason: {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
