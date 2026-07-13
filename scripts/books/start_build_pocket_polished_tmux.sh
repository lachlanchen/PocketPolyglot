#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-build-pocket-polished}"
workers="${WORKERS:-5}"
model="${MODEL:-gpt-5.6-sol}"
reasoning="${REASONING:-low}"
start_book="${START_BOOK:-}"
smoke_book="${SMOKE_BOOK:-black-holes-string-theory-revolution}"
queue="${QUEUE:-build-pocket-polished/tasks/queue.json}"
status="${STATUS:-build-pocket-polished/status.json}"

if [[ ! -f "$queue" ]]; then
  echo "missing prepared queue: $queue" >&2
  exit 1
fi

if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session"
  exit 0
fi

mkdir -p build-pocket-polished/logs
log="build-pocket-polished/logs/${session}_$(date +%Y%m%d_%H%M%S).log"
start_arg=""
if [[ -n "$start_book" ]]; then
  start_arg="--start-book '$start_book'"
fi

tmux new-session -d -s "$session" -n polished "\
cd '$root' && \
{ python -u scripts/books/codex_pocket_polish_worker.py '$smoke_book' \
  --worker-index 1 --workers 1 --max-chunks 1 \
  --model '$model' --reasoning '$reasoning' && \
python -u scripts/books/run_build_pocket_polished_queue.py \
  --queue '$queue' \
  --status '$status' \
  --workers '$workers' \
  --model '$model' \
  --reasoning '$reasoning' \
  $start_arg; } \
  2>&1 | tee -a '$log'"

echo "tmux: $session"
echo "workers: $workers"
echo "model: $model"
echo "reasoning: $reasoning"
echo "smoke_book: $smoke_book"
echo "queue: $queue"
echo "status: $status"
echo "log: $log"
