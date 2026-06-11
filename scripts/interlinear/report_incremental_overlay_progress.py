#!/usr/bin/env python3
"""Report progress for incremental English / modern-Japanese overlays."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-manifest", default="data/source-plan/incremental-english-modern-japanese.json")
    parser.add_argument("--include-waiting-dependencies", action="store_true")
    args = parser.parse_args()

    manifest = load_json(ROOT / args.global_manifest)
    total = 0
    done = 0
    rows = []
    for book in sorted(manifest.get("books", []), key=lambda item: item.get("priority", 9999)):
        dependency = book.get("dependency", "")
        if dependency != "base_chunks_exist" and not args.include_waiting_dependencies:
            rows.append((book["book_id"], "deferred", 0, int(book.get("chunk_count", 0)), dependency))
            continue
        book_id = book["book_id"]
        count = int(book.get("chunk_count", 0))
        durable_dir = ROOT / "data" / "interlinear-overlays" / "en-modern-ja" / book_id / "chunks"
        work_dir = ROOT / "books" / book_id / "work" / "incremental" / "en-modern-ja" / "overlays" / "chunks"
        completed_ids = set()
        for directory in (durable_dir, work_dir):
            if directory.exists():
                completed_ids.update(path.stem for path in directory.glob("*.json"))
        complete = len(completed_ids)
        total += count
        done += min(complete, count)
        rows.append((book_id, "active", complete, count, dependency))

    print(f"incremental overlay progress: {done}/{total} active chunks")
    print("book_id\tstatus\tdone\ttotal\tdependency")
    for book_id, status, complete, count, dependency in rows:
        print(f"{book_id}\t{status}\t{complete}\t{count}\t{dependency}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
