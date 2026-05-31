#!/usr/bin/env python3
"""Prune non-book chunks from an interlinear chunks JSONL and manifest.

This is intended for source-prep mistakes such as public-domain boilerplate that
was already chunked before the cleaned source bundle existed. It preserves chunk
IDs for all remaining chunks so existing reviewed JSON can still be reused.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def chunk_text(chunk: dict[str, Any]) -> str:
    return "\n".join(str(paragraph.get("text", "")) for paragraph in chunk.get("paragraphs", []))


def base_paragraph_id(paragraph_id: str) -> str:
    return re.sub(r"-part-\d+$", "", paragraph_id)


def paragraph_bases(chunks: list[dict[str, Any]]) -> set[str]:
    return {
        base_paragraph_id(str(paragraph.get("id", "")))
        for chunk in chunks
        for paragraph in chunk.get("paragraphs", [])
        if paragraph.get("id")
    }


def backup(path: Path, stamp: str) -> Path:
    target = path.with_suffix(path.suffix + f".bak-{stamp}")
    shutil.copy2(path, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks-jsonl", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--pattern",
        action="append",
        required=True,
        help="Regex matched against concatenated paragraph text. Repeat for OR behavior.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    chunks = load_chunks(args.chunks_jsonl)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    regexes = [re.compile(pattern) for pattern in args.pattern]

    def should_prune(chunk: dict[str, Any]) -> bool:
        text = chunk_text(chunk)
        return any(regex.search(text) for regex in regexes)

    pruned = [chunk for chunk in chunks if should_prune(chunk)]
    keep_ids = {chunk["chunk_id"] for chunk in chunks if not should_prune(chunk)}
    kept = [chunk for chunk in chunks if chunk["chunk_id"] in keep_ids]
    manifest_chunks = [item for item in manifest.get("chunks", []) if item.get("chunk_id") in keep_ids]

    print(f"input_chunks={len(chunks)}")
    print(f"pruned_chunks={len(pruned)}")
    for chunk in pruned:
        print(f"prune {chunk['chunk_id']}: {chunk_text(chunk)[:120]}")
    print(f"output_chunks={len(kept)}")

    if args.dry_run:
        return 0
    if not pruned:
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    chunks_backup = backup(args.chunks_jsonl, stamp)
    manifest_backup = backup(args.manifest, stamp)

    args.chunks_jsonl.write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in kept) + "\n",
        encoding="utf-8",
    )
    manifest["chunk_count"] = len(kept)
    old_paragraph_count = int(manifest.get("paragraph_count") or 0)
    pruned_bases = paragraph_bases(pruned) - paragraph_bases(kept)
    if old_paragraph_count:
        manifest["paragraph_count"] = max(0, old_paragraph_count - len(pruned_bases))
    else:
        manifest["paragraph_count"] = len(paragraph_bases(kept))
    manifest["chunks"] = manifest_chunks
    manifest.setdefault("pruned_chunks", [])
    manifest["pruned_chunks"].extend(
        {
            "chunk_id": chunk["chunk_id"],
            "text": chunk_text(chunk),
            "pruned_at": datetime.now(timezone.utc).isoformat(),
            "reason": "matched prune pattern",
        }
        for chunk in pruned
    )
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"backup_chunks={chunks_backup}")
    print(f"backup_manifest={manifest_backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
