#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: prompt_tools/run_modern_nonfiction_trilingual_queues.sh [history|wealth|both]

Start prepared modern nonfiction EN-JP-ZH queues in tmux.

Defaults:
  history: MODEL=gpt-5.3-codex-spark REASONING=low WORKERS=10
  wealth:  MODEL=gpt-5.5             REASONING=low WORKERS=10

Override with HISTORY_WORKERS, WEALTH_WORKERS, INTERVAL_SECONDS,
MERGE_INTERVAL, COMPILE_INTERVAL_SECONDS, or MAX_ACTIVE_BOOKS.
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

target="${1:-both}"
if [[ "$target" == "-h" || "$target" == "--help" ]]; then
  usage
  exit 0
fi

queue_books() {
  local queue_json="$1"
  python - "$queue_json" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for task in sorted(data["tasks"], key=lambda item: item.get("priority", 999999)):
    print(task["book_id"])
PY
}

start_queue() {
  local name="$1"
  local queue_json="$2"
  local model="$3"
  local reasoning="$4"
  local workers="$5"
  local disable_features="${6:-}"
  local session="zhjpbook-${name}-trilingual-queue"

  if tmux has-session -t "=$session" 2>/dev/null; then
    echo "tmux_session_already_exists=$session"
    return 0
  fi

  mapfile -t books < <(queue_books "$queue_json")
  if [[ "${#books[@]}" -eq 0 ]]; then
    echo "queue_empty=$queue_json" >&2
    return 1
  fi
  local current="${books[0]}"
  local args=(--current-book-id "$current")
  local book
  for book in "${books[@]:1}"; do
    args+=(--book-id "$book")
  done
  mkdir -p "books/$current/work/trilingual/queue"

  tmux new-session -d -s "$session" -n queue \
    "cd '$root' && MODEL='$model' REASONING='$reasoning' WORKERS='$workers' \
      CODEX_EXEC_DISABLE_FEATURES='$disable_features' \
      INTERVAL_SECONDS='${INTERVAL_SECONDS:-900}' \
      MERGE_INTERVAL='${MERGE_INTERVAL:-120}' \
      COMPILE_INTERVAL_SECONDS='${COMPILE_INTERVAL_SECONDS:-1800}' \
      MAX_ACTIVE_BOOKS='${MAX_ACTIVE_BOOKS:-1}' \
      python scripts/interlinear/monitor_trilingual_queue.py ${args[*]} \
      2>&1 | tee 'books/$current/work/trilingual/queue/${session}.log'"

  echo "started_session=$session"
  echo "queue_json=$queue_json"
  echo "model=$model reasoning=$reasoning workers=$workers"
  echo "current=$current queued=${books[*]:1}"
}

case "$target" in
  history)
    start_queue \
      "modern-history" \
      "data/source-plan/modern-history-trilingual-queue.json" \
      "${HISTORY_MODEL:-gpt-5.3-codex-spark}" \
      "${HISTORY_REASONING:-low}" \
      "${HISTORY_WORKERS:-10}" \
      "${HISTORY_CODEX_EXEC_DISABLE_FEATURES:-image_generation}"
    ;;
  wealth)
    start_queue \
      "wealth-success" \
      "data/source-plan/wealth-success-trilingual-queue.json" \
      "${WEALTH_MODEL:-gpt-5.5}" \
      "${WEALTH_REASONING:-low}" \
      "${WEALTH_WORKERS:-10}" \
      "${WEALTH_CODEX_EXEC_DISABLE_FEATURES:-}"
    ;;
  both)
    "$0" history
    "$0" wealth
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
