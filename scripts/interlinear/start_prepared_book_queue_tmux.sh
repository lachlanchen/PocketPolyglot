#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${QUEUE_SESSION:-zhjpbook-prepared-queue}"
ready_book_id="${READY_BOOK_ID:-rashomon-stories}"
interval="${INTERVAL_SECONDS:-900}"
workers="${WORKERS:-10}"
review_workers="${REVIEW_WORKERS:-6}"
max_active_books="${MAX_ACTIVE_BOOKS:-1}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"
log_dir="books/$ready_book_id/work/monitor"
mkdir -p "$log_dir"

if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux prepared queue already exists: $session"
  exit 0
fi

book_ids="${BOOK_IDS:-the-old-capital izu-no-odori genji-modern kojiki woman-in-the-dunes chumon-no-ooi-ryoriten ginga-tetsudo}"
book_args=()
read -r -a ids <<< "$book_ids"
for id in "${ids[@]}"; do
  book_args+=(--book-id "$id")
done

log="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"
tmux new-session -d -s "$session" -n queue "\
cd '$root' && \
python -u scripts/interlinear/monitor_sichuan_then_start_batch.py \
  --current-book-id '$ready_book_id' \
  --interval-seconds '$interval' \
  --workers '$workers' \
  --review-workers '$review_workers' \
  --max-active-books '$max_active_books' \
  --model '$model' \
  --reasoning '$reasoning' \
  ${book_args[*]} \
  2>&1 | tee -a '$log'"

echo "tmux prepared queue: $session"
echo "ready_book_id: $ready_book_id"
echo "book_ids: $book_ids"
echo "interval_seconds: $interval"
echo "workers_per_book: $workers"
echo "review_workers_per_book: $review_workers"
echo "max_active_books: $max_active_books"
echo "model: $model"
echo "reasoning: $reasoning"
echo "log: $log"
