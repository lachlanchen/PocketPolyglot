#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="${BOOK_ID:-${1:-}}"
if [[ -z "$book_id" ]]; then
  echo "Usage: BOOK_ID=<book-id> scripts/interlinear/start_interlinear_monitor_tmux.sh [book-id]" >&2
  exit 1
fi

session="${MONITOR_SESSION:-zhjpbook-${book_id}-monitor}"
worker_session="${WORKER_SESSION:-zhjpbook-${book_id}-json}"
review_session="${REVIEW_SESSION:-zhjpbook-${book_id}-review}"
interval_seconds="${INTERVAL_SECONDS:-1800}"
stall_seconds="${STALL_SECONDS:-3600}"
claim_ttl_seconds="${CLAIM_TTL_SECONDS:-21600}"
compile_command="${COMPILE_COMMAND:-}"
start_command="${START_COMMAND:-}"
repair_command="${REPAIR_COMMAND:-}"
reviewed_stage="${REVIEWED_STAGE:-1}"
monitor_dir="books/$book_id/work/monitor"
mkdir -p "$monitor_dir"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux monitor already exists: $session"
  exit 0
fi

log="$monitor_dir/${session}_$(date +%Y%m%d_%H%M%S).log"
reviewed_stage_arg=()
if [[ "$reviewed_stage" == "0" ]]; then
  reviewed_stage_arg=(--no-reviewed-stage)
fi
tmux new-session -d -s "$session" -n monitor "\
cd '$root' && \
python -u scripts/interlinear/monitor_interlinear_pipeline.py \
  --book-id '$book_id' \
  --worker-session '$worker_session' \
  --review-session '$review_session' \
  --compile-command '$compile_command' \
  --start-command '$start_command' \
  --repair-command '$repair_command' \
  --claim-ttl-seconds '$claim_ttl_seconds' \
  --interval-seconds '$interval_seconds' \
  --stall-seconds '$stall_seconds' \
  ${reviewed_stage_arg[*]} \
  --heal \
  --clear-stale-claims \
  --loop \
  2>&1 | tee -a '$log'"

echo "tmux monitor: $session"
echo "book_id: $book_id"
echo "worker_session: $worker_session"
echo "review_session: $review_session"
echo "interval_seconds: $interval_seconds"
echo "stall_seconds: $stall_seconds"
echo "claim_ttl_seconds: $claim_ttl_seconds"
echo "reviewed_stage: $reviewed_stage"
echo "log: $log"
