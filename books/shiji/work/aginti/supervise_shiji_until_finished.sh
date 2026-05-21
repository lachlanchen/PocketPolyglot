#!/usr/bin/env bash
set -u

ROOT_DIR="/home/lachlan/ProjectsLFS/ZhJpBook"
cd "$ROOT_DIR"

TOTAL_CHUNKS="${TOTAL_CHUNKS:-4622}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-900}"
MAX_BACKFILL_PER_RUN="${MAX_BACKFILL_PER_RUN:-50}"
LOG_DIR="books/shiji/work/aginti/logs"
MONITOR_SESSION="zhjpbook-shiji-aginti-monitor"

mkdir -p "$LOG_DIR"

range_next_start() {
  python3 - "$1" "$2" <<'PY'
import subprocess
import sys
from pathlib import Path

start = int(sys.argv[1])
end = int(sys.argv[2])
validator = Path("books/shiji/work/aginti/validate_shiji_chunk.py")
chunk_dir = Path("data/interlinear/shiji-aginti/chunks")

for n in range(start, end + 1):
    path = chunk_dir / f"shiji-chunk-{n:04d}.json"
    if not path.exists():
        print(n)
        raise SystemExit(0)
    result = subprocess.run(
        [sys.executable, str(validator), str(path), "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    if result.returncode:
        print(n)
        raise SystemExit(0)

print("COMPLETE")
PY
}

prefix_count() {
  python3 - "$TOTAL_CHUNKS" <<'PY'
import subprocess
import sys
from pathlib import Path

total = int(sys.argv[1])
validator = Path("books/shiji/work/aginti/validate_shiji_chunk.py")
chunk_dir = Path("data/interlinear/shiji-aginti/chunks")

count = 0
for n in range(1, total + 1):
    path = chunk_dir / f"shiji-chunk-{n:04d}.json"
    if not path.exists():
        break
    result = subprocess.run(
        [sys.executable, str(validator), str(path), "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    if result.returncode:
        break
    count = n
print(count)
PY
}

start_monitor_if_needed() {
  if tmux has-session -t "$MONITOR_SESSION" 2>/dev/null; then
    return
  fi
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local generator_timeout
  generator_timeout="${SHIJI_GENERATOR_TIMEOUT_SECONDS:-1800}"
  tmux new-session -d -s "$MONITOR_SESSION" -c "$ROOT_DIR" \
    "INTERVAL_SECONDS=60 MAX_BACKFILL_PER_RUN=$MAX_BACKFILL_PER_RUN SHIJI_GENERATOR_TIMEOUT_SECONDS=$generator_timeout bash books/shiji/work/aginti/monitor_loop.sh 2>&1 | tee -a $LOG_DIR/monitor-loop-${ts}-supervised.log"
  echo "restarted monitor at $ts"
}

start_writer_if_needed() {
  local idx="$1"
  local start="$2"
  local end="$3"
  local session
  session="$(printf 'zhjpbook-shiji-aginti-writer-%02d' "$idx")"
  if tmux has-session -t "$session" 2>/dev/null; then
    return
  fi

  local next
  next="$(range_next_start "$start" "$end")"
  if [[ "$next" == "COMPLETE" ]]; then
    echo "$session complete range $start-$end"
    return
  fi

  local prefix_guard="${CURRENT_PREFIX:-0}"
  local monitor_guard=$((prefix_guard + MAX_BACKFILL_PER_RUN))
  if [[ "$next" -le "$monitor_guard" ]]; then
    echo "$session deferred at $next; monitor owns prefix window through $monitor_guard"
    return
  fi

  local limit ts log
  limit=$((end - next + 1))
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  log="$(printf '%s/writer-shard-%02d-%s-%04d-%04d-resume.log' "$LOG_DIR" "$idx" "$ts" "$next" "$end")"
  tmux new-session -d -s "$session" -c "$ROOT_DIR" \
    "python3 -u books/shiji/work/aginti/generate_chunk.py --start $next --limit $limit --max-retries 3 2>&1 | tee -a $log"
  echo "restarted $session at $next-$end"
}

echo "Shiji supervisor started at $(date -u)"

while true; do
  start_monitor_if_needed

  CURRENT_PREFIX="$(prefix_count)"
  base=421
  size=421
  for idx in $(seq 0 9); do
    start=$((base + idx * size))
    [[ "$start" -gt "$TOTAL_CHUNKS" ]] && break
    end=$((start + size - 1))
    [[ "$end" -gt "$TOTAL_CHUNKS" ]] && end="$TOTAL_CHUNKS"
    start_writer_if_needed "$idx" "$start" "$end"
  done

  prefix="$CURRENT_PREFIX"
  echo "$(date -u) contiguous_valid=$prefix/$TOTAL_CHUNKS"
  if [[ "$prefix" -ge "$TOTAL_CHUNKS" ]]; then
    echo "All chunks validate; compiling final Shiji PDFs."
    bash books/shiji/work/aginti/compile_pilot.sh || true
    bash books/shiji/work/aginti/compile_pilot.sh --blackwhite || true
    echo "Shiji complete at $(date -u)"
    exit 0
  fi

  sleep "$INTERVAL_SECONDS"
done
