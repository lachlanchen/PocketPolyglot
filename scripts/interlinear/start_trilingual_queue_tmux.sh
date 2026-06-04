#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: CURRENT_BOOK_ID=<book-id> BOOK_IDS="book-a book-b" scripts/interlinear/start_trilingual_queue_tmux.sh [session]

Wait for CURRENT_BOOK_ID to complete, then start queued trilingual books one at a
time. The monitor exits when CURRENT_BOOK_ID and every queued book are complete.
Each queued book needs books/<book-id>/book-plan.json and is launched with
start_trilingual_book_tmux.sh plus start_trilingual_finalize_tmux.sh.

Environment:
  CURRENT_BOOK_ID            current book to wait on, required
  BOOK_IDS                   space-separated queued book ids, required
  WORKERS                    worker count for each queued book, default 10
  MODEL                      model for workers, default gpt-5.5
  REASONING                  reasoning effort, default high
  RETRY_FAILED=1             retry failed chunk records
  INTERVAL_SECONDS           monitor poll interval, default 1800
  MAX_ACTIVE_BOOKS           default 1
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

current="${CURRENT_BOOK_ID:-}"
book_ids="${BOOK_IDS:-}"
if [[ -z "$current" || -z "$book_ids" ]]; then
  usage >&2
  exit 1
fi

session="${1:-zhjpbook-trilingual-queue}"
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux trilingual queue already exists: $session"
  exit 0
fi

book_args=()
read -r -a ids <<< "$book_ids"
for id in "${ids[@]}"; do
  book_args+=(--book-id "$id")
done

retry_failed_arg=()
if [[ "${RETRY_FAILED:-0}" == "1" ]]; then
  retry_failed_arg=(--retry-failed)
fi

log_dir="books/$current/work/trilingual/queue"
mkdir -p "$log_dir"
log="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"

tmux new-session -d -s "$session" -n trilingual-queue "\
cd '$root' && \
python -u scripts/interlinear/monitor_trilingual_queue.py \
  --current-book-id '$current' \
  --workers '${WORKERS:-10}' \
  --model '${MODEL:-gpt-5.5}' \
  --reasoning '${REASONING:-high}' \
  --interval-seconds '${INTERVAL_SECONDS:-1800}' \
  --merge-interval-seconds '${MERGE_INTERVAL:-120}' \
  --compile-interval-seconds '${COMPILE_INTERVAL_SECONDS:-1200}' \
  --max-active-books '${MAX_ACTIVE_BOOKS:-1}' \
  ${retry_failed_arg[*]} \
  ${book_args[*]} \
  2>&1 | tee -a '$log'"

echo "tmux trilingual queue: $session"
echo "current_book_id: $current"
echo "book_ids: $book_ids"
echo "workers: ${WORKERS:-10}"
echo "model: ${MODEL:-gpt-5.5}"
echo "reasoning: ${REASONING:-high}"
echo "interval_seconds: ${INTERVAL_SECONDS:-1800}"
echo "max_active_books: ${MAX_ACTIVE_BOOKS:-1}"
echo "log: $log"
