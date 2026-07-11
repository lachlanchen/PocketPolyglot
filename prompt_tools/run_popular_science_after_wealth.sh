#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: prompt_tools/run_popular_science_after_wealth.sh [session]

Wait for the wealth-success trilingual queue to finish, then start the
Hawking/Brian Greene popular-science trilingual queue.

Environment:
  WAIT_INTERVAL_SECONDS       wait poll interval, default 900
  POPULAR_SCIENCE_WORKERS     worker count when science starts, default 10
  POPULAR_SCIENCE_MODEL       model when science starts, default gpt-5.5
  POPULAR_SCIENCE_REASONING   reasoning when science starts, default low
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

session="${1:-zhjpbook-popular-science-after-wealth}"
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux_session_already_exists=$session"
  exit 0
fi

state_dir="books/_queues/popular-science-after-wealth"
mkdir -p "$state_dir"
log="$state_dir/${session}_$(date +%Y%m%d_%H%M%S).log"

tmux new-session -d -s "$session" -n wait-wealth "\
cd '$root' && \
echo 'waiting_for_queue=wealth-success started_at='\"\$(date -Is)\" && \
python -u scripts/interlinear/wait_for_trilingual_queue_completion.py \
  --queue data/source-plan/wealth-success-trilingual-queue.json \
  --interval-seconds '${WAIT_INTERVAL_SECONDS:-900}' && \
echo 'starting_queue=popular-science started_at='\"\$(date -Is)\" && \
INTERVAL_SECONDS='${INTERVAL_SECONDS:-900}' \
MERGE_INTERVAL='${MERGE_INTERVAL:-120}' \
COMPILE_INTERVAL_SECONDS='${COMPILE_INTERVAL_SECONDS:-1800}' \
MAX_ACTIVE_BOOKS='${MAX_ACTIVE_BOOKS:-1}' \
POPULAR_SCIENCE_MODEL='${POPULAR_SCIENCE_MODEL:-gpt-5.5}' \
POPULAR_SCIENCE_REASONING='${POPULAR_SCIENCE_REASONING:-low}' \
POPULAR_SCIENCE_WORKERS='${POPULAR_SCIENCE_WORKERS:-10}' \
POPULAR_SCIENCE_CODEX_EXEC_DISABLE_FEATURES='${POPULAR_SCIENCE_CODEX_EXEC_DISABLE_FEATURES:-}' \
bash prompt_tools/run_modern_nonfiction_trilingual_queues.sh science \
2>&1 | tee -a '$log'"

echo "started_session=$session"
echo "wait_queue=data/source-plan/wealth-success-trilingual-queue.json"
echo "then_queue=data/source-plan/popular-science-trilingual-queue.json"
echo "log=$log"
