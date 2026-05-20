#!/usr/bin/env python3
"""Validate generated three-layer chunk JSONs and report pass/fail."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

VALIDATOR = str(Path(__file__).resolve().parent / "validate_shiji_chunk.py")
CHUNKS_DIR = Path("data/interlinear/shiji-aginti/chunks")


def validate_one(chunk_id: str) -> tuple[bool, str]:
    path = CHUNKS_DIR / f"{chunk_id}.json"
    if not path.exists():
        return False, "file not found"
    r = subprocess.run(
        [sys.executable, VALIDATOR, str(path), "--quiet"],
        capture_output=True, text=True, timeout=30,
    )
    return r.returncode == 0, r.stderr.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-id")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    if args.chunk_id:
        ids = [args.chunk_id]
    else:
        ids = [f"shiji-chunk-{n:04d}" for n in range(args.start, args.start + args.limit)]

    passed = 0
    failed = 0
    for cid in ids:
        ok, msg = validate_one(cid)
        if ok:
            print(f"PASS {cid}")
            passed += 1
        else:
            print(f"FAIL {cid}: {msg[:200]}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
