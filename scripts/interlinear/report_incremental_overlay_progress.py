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


def superseded_progress(book: dict[str, Any]) -> tuple[int, int, str] | None:
    replacement = book.get("superseded_by") or {}
    if not replacement:
        return None
    manifest_path = replacement.get("manifest")
    chunk_dir = replacement.get("chunk_dir")
    chunks_jsonl = replacement.get("chunks_jsonl")
    if not manifest_path or not chunk_dir:
        return None
    manifest_file = ROOT / manifest_path
    chunk_root = ROOT / chunk_dir
    if not manifest_file.exists() or not chunk_root.exists():
        return None

    manifest = load_json(manifest_file)
    chunk_ids = [
        item.get("chunk_id")
        for item in manifest.get("chunks", [])
        if isinstance(item, dict) and item.get("chunk_id")
    ]
    if not chunk_ids and chunks_jsonl:
        chunks_file = ROOT / chunks_jsonl
        if chunks_file.exists():
            chunk_ids = [
                json.loads(line).get("chunk_id")
                for line in chunks_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
    total = len(chunk_ids)
    done = sum(1 for chunk_id in chunk_ids if (chunk_root / f"{chunk_id}.json").exists())
    note = f"superseded_by:{replacement.get('book_id', 'replacement')}"
    return done, total, note


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
        replacement = superseded_progress(book)
        if replacement is not None:
            complete, count, replacement_note = replacement
            total += count
            done += min(complete, count)
            rows.append((book["book_id"], "superseded", complete, count, replacement_note))
            continue
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
