#!/usr/bin/env python3
"""Backfill monitor: checks contiguous valid prefix and backfills the first blocker.

Run periodically from the monitor loop. If the contiguous valid prefix is shorter
than the latest generated chunk, this script regenerates the first invalid chunk
before forward generation continues.

Usage:
    python3 backfill_monitor.py [--max-retries 5] [--check-limit 100]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

VALIDATOR = Path(__file__).resolve().parent / "validate_shiji_chunk.py"
GENERATOR = Path(__file__).resolve().parent / "generate_chunk.py"
CHUNKS_DIR = Path("data/interlinear/shiji-aginti/chunks")
MAX_BACKFILL_PER_RUN = 3


def _contiguous_valid_prefix(limit: int = 100) -> tuple[int, int | None]:
    """Return (count, first_failing_index) where all chunks 1..count are valid.
    first_failing_index is the 1-based index of the first failing chunk, or None.
    """
    for n in range(1, limit + 1):
        path = CHUNKS_DIR / f"shiji-chunk-{n:04d}.json"
        if not path.exists():
            return n - 1, n
        r = subprocess.run(
            [sys.executable, str(VALIDATOR), str(path), "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return n - 1, n
    return limit, None


def _regenerate_chunk(chunk_id: str, chunk_idx: int, max_retries: int) -> bool:
    """Regenerate one chunk by ID. Returns True if validation passes."""
    print(f"  Backfilling {chunk_id} (chunk {chunk_idx})...", flush=True)
    r = subprocess.run(
        [sys.executable, str(GENERATOR), "--chunk-id", chunk_id,
         "--max-retries", str(max_retries), "--force"],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode == 0:
        print(f"  {chunk_id}: OK", flush=True)
        return True
    # Check if it was written despite non-zero exit (status update issues)
    path = CHUNKS_DIR / f"{chunk_id}.json"
    if path.exists():
        vr = subprocess.run(
            [sys.executable, str(VALIDATOR), str(path), "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        if vr.returncode == 0:
            print(f"  {chunk_id}: OK (validated on disk)", flush=True)
            return True
        print(f"  {chunk_id}: FAIL after regeneration", flush=True)
        if r.stderr:
            print(f"  stderr: {r.stderr[:500]}", flush=True)
    else:
        print(f"  {chunk_id}: not written", flush=True)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--check-limit", type=int, default=100)
    args = ap.parse_args()

    print("Backfill monitor: checking contiguous valid prefix...", flush=True)
    valid_count, first_bad = _contiguous_valid_prefix(args.check_limit)

    if first_bad is None:
        print(f"  All chunks 1..{args.check_limit} valid.", flush=True)
        return 0

    if valid_count == 0 and first_bad == 1:
        print("  No chunks exist yet.", flush=True)
        return 0

    print(f"  Contiguous valid prefix: {valid_count} chunks", flush=True)
    print(f"  First blocker: chunk {first_bad}", flush=True)

    backfilled = 0
    for _ in range(MAX_BACKFILL_PER_RUN):
        chunk_id = f"shiji-chunk-{first_bad:04d}"
        if _regenerate_chunk(chunk_id, first_bad, args.max_retries):
            backfilled += 1
            # Re-check from the start to find the new first blocker
            valid_count, first_bad = _contiguous_valid_prefix(args.check_limit)
            if first_bad is None:
                print(f"  All chunks 1..{args.check_limit} valid after backfill.", flush=True)
                return 0
            print(f"  Next blocker: chunk {first_bad}", flush=True)
        else:
            print(f"  Failed to fix chunk {first_bad}, aborting backfill.", flush=True)
            return 1

    if backfilled > 0:
        valid_count, first_bad = _contiguous_valid_prefix(args.check_limit)
        print(f"  Backfilled {backfilled} chunk(s). Contiguous prefix: {valid_count}", flush=True)
        if first_bad:
            print(f"  Remaining blocker: chunk {first_bad}", flush=True)
    else:
        print("  No backfill needed.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
