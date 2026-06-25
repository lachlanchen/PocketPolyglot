#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

check_interval="${CHECK_INTERVAL_SECONDS:-1800}"
workers="${WORKERS:-6}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-high}"
compile_interval="${COMPILE_INTERVAL_SECONDS:-1800}"
merge_interval="${MERGE_INTERVAL:-180}"
max_restarts="${MAX_RESTARTS_PER_BOOK:-8}"
main_layers="${MAIN_LAYERS:-wenyan}"

progress_complete() {
  local book_id="$1"
  python scripts/interlinear/report_quadrilingual_progress.py \
    --manifest "books/$book_id/work/quadrilingual/chunks/manifest.json" \
    --chunks-jsonl "books/$book_id/work/quadrilingual/chunks/chunks.jsonl" \
    --chunk-dir "books/$book_id/work/quadrilingual/interlinear/chunks"
}

ensure_running() {
  local book_id="$1"
  local restart_count="$2"
  local session="zhjpbook-$book_id-quadrilingual"
  if tmux has-session -t "=$session" 2>/dev/null; then
    return 0
  fi
  if [[ "$restart_count" -gt "$max_restarts" ]]; then
    echo "max_restarts_reached book_id=$book_id restarts=$restart_count" >&2
    return 1
  fi
  echo "starting book_id=$book_id session=$session restart=$restart_count"
  WORKERS="$workers" \
  MODEL="$model" \
  REASONING="$reasoning" \
  COMPILE_INTERVAL_SECONDS="$compile_interval" \
  MERGE_INTERVAL="$merge_interval" \
  MAIN_LAYERS="$main_layers" \
  RETRY_FAILED=1 \
  scripts/interlinear/start_quadrilingual_wenyan_tmux.sh "$book_id" "$session"
}

run_book_until_complete() {
  local book_id="$1"
  local restarts=0
  while true; do
    if progress_complete "$book_id"; then
      echo "complete book_id=$book_id"
      return 0
    fi
    if ! tmux has-session -t "=zhjpbook-$book_id-quadrilingual" 2>/dev/null; then
      restarts=$((restarts + 1))
      ensure_running "$book_id" "$restarts"
    fi
    sleep "$check_interval"
  done
}

run_book_until_complete zhuangzi
run_book_until_complete sanguozhi

