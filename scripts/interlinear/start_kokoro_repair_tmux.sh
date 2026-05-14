#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-repair}"
start_index="${START_INDEX:-1}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-xhigh}"
max_chars="${MAX_CHARS:-450}"
chunk_mode="${CHUNK_MODE:-paragraph}"
reference_scope="${REFERENCE_SCOPE:-chapter}"
rechunk="${RECHUNK:-1}"
work_dir="books/kokoro/work/bilingual"
chunks_jsonl="$work_dir/chunks/chunks.jsonl"
manifest="$work_dir/chunks/manifest.json"
chunk_dir="$work_dir/interlinear/chunks"
log_dir="books/kokoro/work/logs"
mkdir -p "$log_dir"
log_path="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

if [[ "$rechunk" != "0" ]]; then
  python scripts/interlinear/chunk_bilingual_markdown_book.py \
    --zh-markdown books/kokoro/markdown/zh.md \
    --ja-markdown books/kokoro/markdown/ja.md \
    --book-id kokoro \
    --chunks-jsonl "$chunks_jsonl" \
    --manifest "$manifest" \
    --chunk-mode "$chunk_mode" \
    --reference-scope "$reference_scope" \
    --max-chars "$max_chars"
fi

tmux new-session -d -s "$session" -n repair "
cd '$root' &&
python -u scripts/interlinear/codex_bilingual_chunk_worker.py \
  --chunks-jsonl '$chunks_jsonl' \
  --output-dir '$chunk_dir' \
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
echo "chunk_mode: $chunk_mode"
echo "reference_scope: $reference_scope"
