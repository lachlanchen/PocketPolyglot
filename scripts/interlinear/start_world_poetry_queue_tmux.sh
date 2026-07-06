#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_world_poetry_queue_tmux.sh [session]

Starts the world-poetry queue monitor immediately, independent of the classical
queue. It starts only launchable poetry book plans; source-only plans remain
waiting at waiting_for_poetry_preparation=<book-id>.

Environment:
  WORKERS=10
  MODEL=gpt-5.5
  REASONING=low
  INTERVAL_SECONDS=1800
  MERGE_INTERVAL=120
  COMPILE_INTERVAL_SECONDS=1200
  MAX_ACTIVE_BOOKS=1
  POETRY_BATCH=data/source-plan/world-poetry-source-batch.json
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-world-poetry-queue}"
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

log_dir="logs"
mkdir -p "$log_dir"

export WORKERS="${WORKERS:-10}"
export MODEL="${MODEL:-gpt-5.5}"
export REASONING="${REASONING:-low}"
export INTERVAL_SECONDS="${INTERVAL_SECONDS:-1800}"
export MERGE_INTERVAL="${MERGE_INTERVAL:-120}"
export COMPILE_INTERVAL_SECONDS="${COMPILE_INTERVAL_SECONDS:-1200}"
export MAX_ACTIVE_BOOKS="${MAX_ACTIVE_BOOKS:-1}"
export POETRY_BATCH="${POETRY_BATCH:-data/source-plan/world-poetry-source-batch.json}"
export SKIP_CLASSICAL_GATE=1
export STATE_DIR="${STATE_DIR:-books/_queues/world-poetry-queue}"

tmux new-session -d -s "$session" -n world-poetry-queue \
  "cd '$root' && python -u scripts/interlinear/monitor_world_poetry_after_classics.py --skip-classical-gate --state-dir '$STATE_DIR' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "workers: $WORKERS"
echo "model: $MODEL"
echo "reasoning: $REASONING"
echo "max_active_books: $MAX_ACTIVE_BOOKS"
echo "poetry_batch: $POETRY_BATCH"
echo "state: $STATE_DIR/state.json"
