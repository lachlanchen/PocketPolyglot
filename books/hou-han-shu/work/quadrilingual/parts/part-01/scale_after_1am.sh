#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$ROOT"

BOOK_ID="hou-han-shu"
PART_DIR="books/hou-han-shu/work/quadrilingual/parts/part-01"
MANIFEST="$PART_DIR/manifest.json"
CHUNKS_JSONL="books/hou-han-shu/work/quadrilingual/chunks/chunks.jsonl"
CHUNK_DIR="books/hou-han-shu/work/quadrilingual/interlinear/chunks"
START_SCRIPT="$PART_DIR/start_part.sh"
EXTRA_SESSION="${EXTRA_SESSION:-zhjpbook-hou-han-shu-part-01-90-after1am-low}"
EXTRA_WORKERS="${EXTRA_WORKERS:-90}"
EXTRA_PREFIX="${EXTRA_PREFIX:-quad-after1}"
SCALE_AFTER_HOUR="${SCALE_AFTER_HOUR:-1}"
THRESHOLD="${CODEX_5H_MIN_LEFT_PERCENT:-25}"
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-600}"
LIMIT_BACKOFF_SECONDS="${LIMIT_BACKOFF_SECONDS:-3600}"
RECENT_LIMIT_MINUTES="${RECENT_LIMIT_MINUTES:-30}"
QUOTA_FILE="${QUOTA_FILE:-$PART_DIR/quota/status.txt}"
LOG="$PART_DIR/scale_after_1am.log"

mkdir -p "$PART_DIR/quota"

log() {
  printf '[%s] %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"
}

next_scale_epoch() {
  python3 - <<'PY'
import os
from datetime import datetime, timedelta
hour = int(os.environ.get("SCALE_AFTER_HOUR", "1"))
now = datetime.now()
target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
if target <= now:
    target += timedelta(days=1)
print(int(target.timestamp()))
PY
}

part_complete() {
  python scripts/interlinear/report_quadrilingual_progress.py \
    --manifest "$MANIFEST" \
    --chunks-jsonl "$CHUNKS_JSONL" \
    --chunk-dir "$CHUNK_DIR" >/tmp/hou-han-shu-part-01-progress.txt 2>&1
}

recent_usage_limit_seen() {
  find "$PART_DIR/parallel-json" "books/$BOOK_ID/work/logs" \
    -type f -mmin "-$RECENT_LIMIT_MINUTES" 2>/dev/null \
    -print0 |
    xargs -0r rg -i -q \
      "you.?ve hit your usage limit|you have hit your usage limit|usage limit|purchase more credits|try again at"
}

five_hour_left_percent() {
  [[ -f "$QUOTA_FILE" ]] || return 1
  python3 - "$QUOTA_FILE" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
match = re.search(r"5h limit:[^\n]*?(\d{1,3})%\s+left", text, re.I)
if match:
    print(match.group(1))
    raise SystemExit(0)
raise SystemExit(1)
PY
}

quota_too_low() {
  local percent
  percent="$(five_hour_left_percent 2>/dev/null || true)"
  [[ -n "$percent" ]] || return 1
  if (( percent < THRESHOLD )); then
    log "5h quota snapshot is ${percent}% left, below ${THRESHOLD}%; holding extra workers"
    return 0
  fi
  return 1
}

extra_running() {
  tmux has-session -t "=$EXTRA_SESSION" 2>/dev/null
}

start_extra() {
  if extra_running; then
    log "extra worker session already running: $EXTRA_SESSION"
    return 0
  fi
  log "starting extra workers: session=$EXTRA_SESSION workers=$EXTRA_WORKERS prefix=$EXTRA_PREFIX"
  WORKERS="$EXTRA_WORKERS" \
  MODEL="${MODEL:-gpt-5.5}" \
  REASONING="${REASONING:-low}" \
  WORKER_PREFIX="$EXTRA_PREFIX" \
  "$START_SCRIPT" "$EXTRA_SESSION" >>"$LOG" 2>&1
}

stop_extra() {
  if extra_running; then
    log "stopping extra worker session to slow down: $EXTRA_SESSION"
    tmux kill-session -t "=$EXTRA_SESSION" || true
  fi
}

target="$(next_scale_epoch)"
now="$(date +%s)"
if (( now < target )); then
  log "waiting until $(date -d "@$target" '+%F %T %Z') before adding extra workers"
  sleep "$((target - now))"
fi

while true; do
  if part_complete; then
    log "part complete; scaler exiting"
    stop_extra
    exit 0
  fi

  if recent_usage_limit_seen; then
    log "recent usage-limit marker found; keeping only baseline workers and backing off"
    stop_extra
    sleep "$LIMIT_BACKOFF_SECONDS"
    continue
  fi

  if quota_too_low; then
    stop_extra
    sleep "$LIMIT_BACKOFF_SECONDS"
    continue
  fi

  start_extra
  sleep "$CHECK_INTERVAL_SECONDS"
done
