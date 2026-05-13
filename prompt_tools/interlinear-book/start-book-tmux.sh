#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: prompt_tools/interlinear-book/start-book-tmux.sh [options] [-- pipeline options]

Start a tmux session that runs run-book-pipeline.sh. Unknown options after
-- are passed through to the pipeline.

Options:
  --session <name>   tmux session name (default: zhjpbook-interlinear)
  --kill             kill existing session first
  --no-attach        start detached
  -h, --help         show help

Example:
  prompt_tools/interlinear-book/start-book-tmux.sh --kill --no-attach -- \\
    --epub sources/心.epub --book-id kokoro --model gpt-5.5 --reasoning high
USAGE
}

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
session="zhjpbook-interlinear"
kill_existing=0
attach=1
pipeline_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session) session="${2:-}"; shift 2 ;;
    --kill|--restart) kill_existing=1; shift ;;
    --no-attach|--detached) attach=0; shift ;;
    --) shift; pipeline_args=("$@"); break ;;
    -h|--help) usage; exit 0 ;;
    *) pipeline_args+=("$1"); shift ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found." >&2
  exit 1
fi

book_id="kokoro"
for ((i = 0; i < ${#pipeline_args[@]}; i++)); do
  if [[ "${pipeline_args[$i]}" == "--book-id" && $((i + 1)) -lt ${#pipeline_args[@]} ]]; then
    book_id="${pipeline_args[$((i + 1))]}"
    break
  fi
done

log_dir="$root/books/$book_id/work/logs"
mkdir -p "$log_dir"
log_path="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"

if tmux has-session -t "$session" 2>/dev/null; then
  if [[ "$kill_existing" -eq 1 ]]; then
    tmux kill-session -t "$session"
  else
    echo "tmux session already running: $session"
    echo "attach: tmux attach -t $session"
    [[ "$attach" -eq 1 ]] && exec tmux attach -t "$session"
    exit 0
  fi
fi

cmd=(bash "$root/prompt_tools/interlinear-book/run-book-pipeline.sh" "${pipeline_args[@]}")
printf -v quoted_cmd '%q ' "${cmd[@]}"
tmux new-session -d -s "$session" -c "$root" "bash -lc 'cd \"$root\" && $quoted_cmd 2>&1 | tee \"$log_path\"'"
tmux rename-window -t "$session:0" "interlinear"
tmux set-option -t "$session" -g mouse on

echo "tmux session: $session"
echo "log: $log_path"
echo "attach: tmux attach -t $session"

if [[ "$attach" -eq 1 ]]; then
  exec tmux attach -t "$session"
fi
