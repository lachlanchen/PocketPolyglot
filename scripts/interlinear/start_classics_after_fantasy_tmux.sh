#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_classics_after_fantasy_tmux.sh [session]

Starts a tmux monitor that waits for the current fantasy trilingual queue
to finish before launching the classical quadrilingual queue:

  lunyu, mengzi, xunzi, mozi, hanfeizi, guiguzi, lushi-chunqiu,
  sunzi-bingfa, sunbin-bingfa, simafa, weiliaozi

Environment:
  WORKERS=100
  MODEL=gpt-5.5
  REASONING=low
  MAIN_LAYERS=wenyan
  INTERVAL_SECONDS=1800
  MERGE_INTERVAL=120
  COMPILE_INTERVAL_SECONDS=1200
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-classics-after-fantasy}"
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

log_dir="logs"
mkdir -p "$log_dir"

export WORKERS="${WORKERS:-100}"
export MODEL="${MODEL:-gpt-5.5}"
export REASONING="${REASONING:-low}"
export MAIN_LAYERS="${MAIN_LAYERS:-wenyan}"
export INTERVAL_SECONDS="${INTERVAL_SECONDS:-1800}"
export MERGE_INTERVAL="${MERGE_INTERVAL:-120}"
export COMPILE_INTERVAL_SECONDS="${COMPILE_INTERVAL_SECONDS:-1200}"

tmux new-session -d -s "$session" -n classics-after-fantasy \
  "cd '$root' && python -u scripts/interlinear/monitor_fantasy_then_classical_queue.py 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "workers: $WORKERS"
echo "model: $MODEL"
echo "reasoning: $REASONING"
echo "main_layers: $MAIN_LAYERS"
echo "state: books/_queues/fantasy-then-classics/state.json"
