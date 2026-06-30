#!/usr/bin/env python3
"""Report quadrilingual chunk progress against the current manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_quadrilingual_interlinear_json import validate_chunk


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--chunks-jsonl", required=True)
    parser.add_argument("--chunk-dir", required=True)
    args = parser.parse_args()

    manifest = load_json(Path(args.manifest))
    sources = load_jsonl(Path(args.chunks_jsonl))
    chunk_dir = Path(args.chunk_dir)
    manifest_chunks = manifest.get("chunks")
    if isinstance(manifest_chunks, list) and manifest_chunks:
        selected_ids = {
            item.get("chunk_id") if isinstance(item, dict) else item
            for item in manifest_chunks
        }
        sources = [source for source in sources if source.get("chunk_id") in selected_ids]
    valid = 0
    missing = 0
    stale = 0
    first_missing: list[str] = []
    first_stale: list[str] = []
    for source in sources:
        path = chunk_dir / f"{source['chunk_id']}.json"
        if not path.exists():
            missing += 1
            if len(first_missing) < 8:
                first_missing.append(source["chunk_id"])
            continue
        errors = validate_chunk(source, load_json(path))
        if errors:
            stale += 1
            if len(first_stale) < 8:
                first_stale.append(f"{source['chunk_id']}: {errors[0]}")
            continue
        valid += 1
    total = manifest.get("chunk_count", len(sources))
    print(f"book_id={manifest.get('book_id')} valid={valid}/{total} missing={missing} stale={stale}")
    if first_missing:
        print("first_missing=" + ", ".join(first_missing))
    if first_stale:
        print("first_stale=" + " | ".join(first_stale))
    return 0 if valid == total and stale == 0 and missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
