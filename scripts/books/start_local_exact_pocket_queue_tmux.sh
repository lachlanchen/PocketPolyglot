#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QUEUE="${1:-data/source-plan/nutstore-share-books-local-exact-queue.json}"
SESSION="${2:-nutstore-share-local-tex}"
LOG="${3:-build-pocket/logs/${SESSION}.log}"

cd "$ROOT"
mkdir -p "$(dirname "$LOG")"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session already exists: $SESSION" >&2
  exit 2
fi

tmux new-session -d -s "$SESSION" -c "$ROOT" \
  "python scripts/books/build_pocket_tex_queue.py --queue '$QUEUE' --continue-on-blocked 2>&1 | tee -a '$LOG'"

echo "started tmux session: $SESSION"
echo "log: $ROOT/$LOG"
echo "attach: tmux attach -t $SESSION"
