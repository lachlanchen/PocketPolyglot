#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-repair}"
start_index="${START_INDEX:-1}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-xhigh}"
log_dir="books/kokoro/work/logs"
mkdir -p "$log_dir"
log_path="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

tmux new-session -d -s "$session" -n repair "
cd '$root' &&
python scripts/interlinear/codex_bilingual_chunk_worker.py \
  --chunks-jsonl books/kokoro/work/bilingual/chunks/chunks.jsonl \
  --output-dir books/kokoro/work/bilingual/interlinear/chunks \
  --work-dir books/kokoro/work/bilingual/codex-repair \
  --model '$model' \
  --reasoning '$reasoning' \
  --start-index '$start_index' \
  --max-chunks 0 \
  --retries 4 \
  --after-chunk-command 'bash scripts/interlinear/compile_kokoro_both_previews.sh' \
  2>&1 | tee '$log_path'
"

echo "tmux: $session"
echo "log: $log_path"
