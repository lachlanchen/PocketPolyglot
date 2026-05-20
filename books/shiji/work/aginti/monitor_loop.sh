#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$ROOT_DIR"

INTERVAL_SECONDS="${INTERVAL_SECONDS:-900}"
LOG_DIR="books/shiji/work/aginti/logs"
mkdir -p "$LOG_DIR"

count_valid_chunks() {
  python3 - <<'PY'
import subprocess
import sys
from pathlib import Path

chunks = Path("data/interlinear/shiji-aginti/chunks")
validator = Path("books/shiji/work/aginti/validate_shiji_chunk.py")
n = 1
while True:
    path = chunks / f"shiji-chunk-{n:04d}.json"
    if not path.exists():
        break
    result = subprocess.run(
        [sys.executable, str(validator), str(path), "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    if result.returncode != 0:
        break
    n += 1
print(n - 1)
PY
}

while true; do
  date -u
  count="$(count_valid_chunks)"
  echo "valid contiguous chunks: $count"
  if [[ "$count" -gt 0 ]]; then
    python3 -u books/shiji/work/aginti/review_chunks.py --start 1 --limit "$count" || true
    bash books/shiji/work/aginti/compile_pilot.sh || true
    bash books/shiji/work/aginti/compile_pilot.sh --blackwhite || true
  fi
  echo "sleeping ${INTERVAL_SECONDS}s"
  sleep "$INTERVAL_SECONDS"
done
