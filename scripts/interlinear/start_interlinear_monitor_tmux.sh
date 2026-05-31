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
repair_command="${REPAIR_COMMAND:-python scripts/interlinear/repair_mechanical_furigana_prefix.py --book-id $book_id --merge}"
reviewed_stage="${REVIEWED_STAGE:-1}"
monitor_dir="books/$book_id/work/monitor"
mkdir -p "$monitor_dir"

if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux monitor already exists: $session"
  exit 0
fi

log="$monitor_dir/${session}_$(date +%Y%m%d_%H%M%S).log"
runner="$monitor_dir/${session}.run.sh"
finish_dir="books/$book_id/work/bilingual/reviewed/chunks"
if [[ "$reviewed_stage" == "0" ]]; then
  finish_dir="books/$book_id/work/bilingual/interlinear/chunks"
fi
reviewed_stage_arg=()
if [[ "$reviewed_stage" == "0" ]]; then
  reviewed_stage_arg=(--no-reviewed-stage)
fi
{
  printf '#!/usr/bin/env bash\n'
  printf 'set -uo pipefail\n'
  printf 'cd %q\n' "$root"
  printf 'while true; do\n'
  printf '  python -u scripts/interlinear/monitor_interlinear_pipeline.py \\\n'
  printf '    --book-id %q \\\n' "$book_id"
  printf '    --worker-session %q \\\n' "$worker_session"
  printf '    --review-session %q \\\n' "$review_session"
  printf '    --compile-command %q \\\n' "$compile_command"
  printf '    --start-command %q \\\n' "$start_command"
  printf '    --repair-command %q \\\n' "$repair_command"
  printf '    --claim-ttl-seconds %q \\\n' "$claim_ttl_seconds"
  printf '    --interval-seconds %q \\\n' "$interval_seconds"
  printf '    --stall-seconds %q \\\n' "$stall_seconds"
  if [[ "$reviewed_stage" == "0" ]]; then
    printf '    --no-reviewed-stage \\\n'
  fi
  printf '    --heal \\\n'
  printf '    --clear-stale-claims \\\n'
  printf '    --loop\n'
  printf '  code=$?\n'
  printf '  echo "monitor_exit_code=$code timestamp=$(date -Is)"\n'
  printf '  if python scripts/interlinear/report_interlinear_progress.py --manifest %q --chunk-dir %q | grep -q "^missing_chunks=0$"; then\n' \
    "books/$book_id/work/bilingual/chunks/manifest.json" "$finish_dir"
  printf '    echo "monitor_complete=1 timestamp=$(date -Is)"\n'
  printf '    break\n'
  printf '  fi\n'
  printf '  sleep 60\n'
  printf 'done\n'
} > "$runner"
chmod +x "$runner"

tmux new-session -d -s "$session" -n monitor "bash '$runner' 2>&1 | tee -a '$log'"

echo "tmux monitor: $session"
echo "book_id: $book_id"
echo "worker_session: $worker_session"
echo "review_session: $review_session"
echo "interval_seconds: $interval_seconds"
echo "stall_seconds: $stall_seconds"
echo "claim_ttl_seconds: $claim_ttl_seconds"
echo "reviewed_stage: $reviewed_stage"
echo "log: $log"
echo "runner: $runner"
