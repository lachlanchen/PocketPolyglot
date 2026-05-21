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
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path

VALIDATOR = Path(__file__).resolve().parent / "validate_shiji_chunk.py"
GENERATOR = Path(__file__).resolve().parent / "generate_chunk.py"
CHUNKS_DIR = Path("data/interlinear/shiji-aginti/chunks")
JSONL = Path("books/shiji/work/bilingual/chunks/chunks.jsonl")


def _generator_timeout_seconds() -> int:
    raw = os.environ.get("SHIJI_GENERATOR_TIMEOUT_SECONDS", "1800")
    try:
        value = int(raw)
    except ValueError:
        value = 1800
    return max(600, value)


def _contiguous_valid_prefix(limit: int) -> tuple[int, int | None]:
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
    cmd = [
        sys.executable,
        str(GENERATOR),
        "--chunk-id",
        chunk_id,
        "--max-retries",
        str(max_retries),
        "--force",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    timeout_seconds = _generator_timeout_seconds()
    deadline = time.monotonic() + timeout_seconds
    tail: list[str] = []

    while proc.poll() is None:
        if time.monotonic() > deadline:
            proc.kill()
            print(f"  {chunk_id}: generator timed out after {timeout_seconds}s", flush=True)
            break
        for key, _ in selector.select(timeout=1):
            line = key.fileobj.readline()
            if not line:
                continue
            tail.append(line)
            tail = tail[-20:]
            print("    " + line, end="", flush=True)

    for line in proc.stdout.readlines():
        tail.append(line)
        tail = tail[-20:]
        print("    " + line, end="", flush=True)
    returncode = proc.wait()
    selector.close()

    if returncode == 0:
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
        if tail:
            print("  generator tail:", flush=True)
            for line in tail[-10:]:
                print("    " + line, end="", flush=True)
    else:
        print(f"  {chunk_id}: not written", flush=True)
    return False


def _highest_chunk_index() -> int:
    """Find the highest existing chunk index from the chunks directory."""
    max_idx = 0
    if CHUNKS_DIR.exists():
        for f in CHUNKS_DIR.iterdir():
            if f.suffix == ".json" and f.stem.startswith("shiji-chunk-"):
                try:
                    idx = int(f.stem.split("-")[-1])
                    if idx > max_idx:
                        max_idx = idx
                except ValueError:
                    pass
    return max_idx


def _manifest_chunk_count() -> int:
    if not JSONL.exists():
        return 0
    count = 0
    with JSONL.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _resolve_check_limit(value: int) -> int:
    if value > 0:
        return value
    return max(_highest_chunk_index(), _manifest_chunk_count(), 100)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument(
        "--check-limit",
        type=int,
        default=0,
        help="highest chunk number to scan; 0 means highest generated or manifest count",
    )
    ap.add_argument("--max-backfill-per-run", type=int, default=3)
    args = ap.parse_args()

    print("Backfill monitor: checking contiguous valid prefix...", flush=True)
    check_limit = _resolve_check_limit(args.check_limit)
    print(f"  Check limit: {check_limit}", flush=True)
    valid_count, first_bad = _contiguous_valid_prefix(check_limit)

    if first_bad is None:
        print(f"  All chunks 1..{check_limit} valid.", flush=True)
        return 0

    if valid_count == 0 and first_bad == 1:
        print("  No chunks exist yet.", flush=True)
        return 0

    print(f"  Contiguous valid prefix: {valid_count} chunks", flush=True)
    print(f"  First blocker: chunk {first_bad}", flush=True)

    backfilled = 0
    for _ in range(max(1, args.max_backfill_per_run)):
        chunk_id = f"shiji-chunk-{first_bad:04d}"
        if _regenerate_chunk(chunk_id, first_bad, args.max_retries):
            backfilled += 1
            # Re-check from the start to find the new first blocker
            valid_count, first_bad = _contiguous_valid_prefix(check_limit)
            if first_bad is None:
                print(f"  All chunks 1..{check_limit} valid after backfill.", flush=True)
                return 0
            print(f"  Next blocker: chunk {first_bad}", flush=True)
        else:
            print(f"  Failed to fix chunk {first_bad}, aborting backfill.", flush=True)
            return 1

    if backfilled > 0:
        valid_count, first_bad = _contiguous_valid_prefix(check_limit)
        print(f"  Backfilled {backfilled} chunk(s). Contiguous prefix: {valid_count}", flush=True)
        if first_bad:
            print(f"  Remaining blocker: chunk {first_bad}", flush=True)
    else:
        print("  No backfill needed.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
