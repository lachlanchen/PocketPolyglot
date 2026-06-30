#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$ROOT"

BOOK_ID="hou-han-shu"
PART_ROOT="books/hou-han-shu/work/quadrilingual/parts"
CHUNKS_JSONL="books/hou-han-shu/work/quadrilingual/chunks/chunks.jsonl"
CHUNK_DIR="books/hou-han-shu/work/quadrilingual/interlinear/chunks"
WORKERS="${WORKERS:-10}"
MODEL="${MODEL:-gpt-5.5}"
REASONING="${REASONING:-low}"
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-600}"
RETRY_FAILED="${RETRY_FAILED:-1}"
FAILED_RETRY_AGE_SECONDS="${FAILED_RETRY_AGE_SECONDS:-600}"
LOG="$PART_ROOT/run_parts_sequential.log"

mkdir -p "$PART_ROOT"

log() {
  printf '[%s] %s\n' "$(date '+%F %T %Z')" "$*" | tee -a "$LOG"
}

part_manifest() {
  printf '%s/part-%02d/manifest.json' "$PART_ROOT" "$1"
}

part_script() {
  printf '%s/part-%02d/start_part.sh' "$PART_ROOT" "$1"
}

part_session() {
  printf 'zhjpbook-%s-part-%02d-%s-low' "$BOOK_ID" "$1" "$WORKERS"
}

part_complete() {
  local part="$1"
  python scripts/interlinear/report_quadrilingual_progress.py \
    --manifest "$(part_manifest "$part")" \
    --chunks-jsonl "$CHUNKS_JSONL" \
    --chunk-dir "$CHUNK_DIR" >/tmp/hou-han-shu-part-"$part"-progress.txt 2>&1
}

print_progress() {
  local part="$1"
  cat /tmp/hou-han-shu-part-"$part"-progress.txt 2>/dev/null || true
}

session_exists() {
  tmux has-session -t "=$(part_session "$1")" 2>/dev/null
}

any_part_session_exists() {
  local part="$1"
  tmux list-sessions 2>/dev/null | rg -q "zhjpbook-${BOOK_ID}-part-0?${part}-"
}

start_part() {
  local part="$1"
  local session
  session="$(part_session "$part")"
  if tmux has-session -t "=$session" 2>/dev/null; then
    log "part $part already running in $session"
    return 0
  fi
  log "starting part $part with $WORKERS workers: $session"
  WORKERS="$WORKERS" \
  MODEL="$MODEL" \
  REASONING="$REASONING" \
  RETRY_FAILED="$RETRY_FAILED" \
  FAILED_RETRY_AGE_SECONDS="$FAILED_RETRY_AGE_SECONDS" \
  WORKER_PREFIX="quad-p$(printf '%02d' "$part")" \
  "$(part_script "$part")" "$session" >>"$LOG" 2>&1
}

wait_for_part() {
  local part="$1"
  while true; do
    if part_complete "$part"; then
      log "part $part complete"
      print_progress "$part" | tee -a "$LOG"
      return 0
    fi
    print_progress "$part" | tee -a "$LOG"
    if ! session_exists "$part" && ! any_part_session_exists "$part"; then
      start_part "$part"
    else
      log "part $part is still running; checking again in ${CHECK_INTERVAL_SECONDS}s"
    fi
    sleep "$CHECK_INTERVAL_SECONDS"
  done
}

for part in 1 2 3; do
  wait_for_part "$part"
done

log "all three Houhanshu parts are complete"
