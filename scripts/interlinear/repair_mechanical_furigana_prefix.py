#!/usr/bin/env python3
"""Repair the first missing raw chunk when it has a mechanical ruby failure."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def first_missing(manifest: Path, chunk_dir: Path) -> str:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for item in data.get("chunks", []):
        chunk_id = str(item.get("chunk_id", ""))
        if chunk_id and not (chunk_dir / f"{chunk_id}.json").exists():
            return chunk_id
    return ""


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout, end="")
    return proc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--merge", action="store_true")
    parser.add_argument(
        "--allow-active-rejected",
        action="store_true",
        help="also try rejected candidates before the worker has written a final failed marker",
    )
    args = parser.parse_args()

    root = Path("books") / args.book_id / "work" / "bilingual"
    manifest = root / "chunks" / "manifest.json"
    chunks_jsonl = root / "chunks" / "chunks.jsonl"
    raw_dir = root / "interlinear" / "chunks"
    reviewed_dir = root / "reviewed" / "chunks"
    gen_candidates = root / "parallel-json" / "candidates"
    review_candidates = root / "parallel-review" / "candidates"
    chunk_id = first_missing(manifest, raw_dir)
    if not chunk_id:
        print("no_missing_raw_chunk")
        return 0

    failed_marker = gen_candidates / "failed" / f"{chunk_id}.json"
    rejected = sorted((gen_candidates / "rejected").glob(f"{chunk_id}.*.json"))
    if not failed_marker.exists() and not (args.allow_active_rejected and rejected):
        print(f"first_missing={chunk_id} no_failed_marker")
        return 0

    repair = run(
        [
            "python",
            "scripts/interlinear/repair_mechanical_furigana_candidate.py",
            "--book-id",
            args.book_id,
            "--chunk-id",
            chunk_id,
            "--write-review-candidate",
        ]
    )
    if repair.returncode:
        return repair.returncode

    if args.merge:
        run(
            [
                "python",
                "scripts/interlinear/merge_parallel_json_candidates.py",
                "--chunks-jsonl",
                str(chunks_jsonl),
                "--candidate-dir",
                str(gen_candidates),
                "--canonical-dir",
                str(raw_dir),
                "--merged-dir",
                str(root / "parallel-json" / "merged"),
            ]
        )
        run(
            [
                "python",
                "scripts/interlinear/merge_reviewed_chunks.py",
                "--chunks-jsonl",
                str(chunks_jsonl),
                "--candidate-dir",
                str(review_candidates),
                "--final-dir",
                str(reviewed_dir),
                "--merged-dir",
                str(root / "parallel-review" / "merged"),
                "--rejected-dir",
                str(root / "parallel-review" / "merge-rejected"),
            ]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
