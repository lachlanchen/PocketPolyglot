#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_world_poetry_after_classics_tmux.sh [session]

Starts a tmux monitor that waits for the classical quadrilingual queue to
complete before launching the prepared world-poetry trilingual queue in order.

The monitor does not prepare Markdown/chunks by itself. If the next poetry
book is still source-only, it records waiting_for_poetry_preparation and waits.

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

session="${1:-zhjpbook-world-poetry-after-classics}"
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

tmux new-session -d -s "$session" -n poetry-after-classics \
  "cd '$root' && python -u scripts/interlinear/monitor_world_poetry_after_classics.py 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "workers: $WORKERS"
echo "model: $MODEL"
echo "reasoning: $REASONING"
echo "max_active_books: $MAX_ACTIVE_BOOKS"
echo "poetry_batch: $POETRY_BATCH"
echo "state: books/_queues/world-poetry-after-classics/state.json"
