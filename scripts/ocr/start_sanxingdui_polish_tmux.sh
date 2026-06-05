#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SESSION="${SESSION:-zhjpbook-sanxingdui-polish}"
MODEL="${MODEL:-gpt-5.5}"
REASONING="${REASONING:-high}"

cd "$ROOT"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "session_exists=$SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" \
  "cd '$ROOT' && CODEX_USAGE_LIMIT_WAIT=1 python scripts/ocr/codex_polish_sanxingdui_pages.py --model '$MODEL' --reasoning '$REASONING' --compile $*"

echo "started=$SESSION"
echo "attach: tmux attach -t $SESSION"
