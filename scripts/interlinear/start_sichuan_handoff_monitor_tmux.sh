#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${HANDOFF_SESSION:-zhjpbook-sichuan-handoff}"
interval="${INTERVAL_SECONDS:-1800}"
workers="${WORKERS:-10}"
review_workers="${REVIEW_WORKERS:-6}"
max_active_books="${MAX_ACTIVE_BOOKS:-0}"
log_dir="books/sichuan-folk-stories-vol1/work/monitor"
mkdir -p "$log_dir"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux handoff monitor already exists: $session"
  exit 0
fi

book_args=()
if [[ -n "${BOOK_IDS:-}" ]]; then
  read -r -a ids <<< "$BOOK_IDS"
  for id in "${ids[@]}"; do
    book_args+=(--book-id "$id")
  done
fi

log="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"
tmux new-session -d -s "$session" -n handoff "\
cd '$root' && \
python -u scripts/interlinear/monitor_sichuan_then_start_batch.py \
  --interval-seconds '$interval' \
  --workers '$workers' \
  --review-workers '$review_workers' \
  --max-active-books '$max_active_books' \
  ${book_args[*]} \
  2>&1 | tee -a '$log'"

echo "tmux handoff monitor: $session"
echo "interval_seconds: $interval"
echo "workers_per_book: $workers"
echo "review_workers_per_book: $review_workers"
echo "max_active_books: $max_active_books"
echo "log: $log"
