#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-repair}"
start_index="${START_INDEX:-1}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-xhigh}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
max_chars="${MAX_CHARS:-450}"
chunk_mode="${CHUNK_MODE:-paragraph}"
reference_scope="${REFERENCE_SCOPE:-chapter}"
work_dir="books/kokoro/work/bilingual"
chunks_jsonl="$work_dir/chunks/chunks.jsonl"
manifest="$work_dir/chunks/manifest.json"
chunk_dir="$work_dir/interlinear/chunks"
log_dir="books/kokoro/work/logs"
mkdir -p "$log_dir"
log_path="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"

if [[ -v RECHUNK ]]; then
  rechunk="$RECHUNK"
elif [[ -f "$manifest" && -f "$chunks_jsonl" ]]; then
  rechunk=0
else
  rechunk=1
fi

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

if [[ "$rechunk" != "0" ]]; then
  existing_chunks="$(find "$chunk_dir" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l)"
  if [[ "$existing_chunks" -gt 0 && "${CONFIRM_RECHUNK:-0}" != "1" ]]; then
    echo "Refusing to rechunk: $chunk_dir already contains $existing_chunks generated chunks." >&2
    echo "Use RECHUNK=0 to resume the current manifest, or CONFIRM_RECHUNK=1 to intentionally rebuild it." >&2
    exit 1
  fi
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
  --codex-timeout-seconds '$codex_timeout_seconds' \
  --retries 4 \
  --after-chunk-command 'bash scripts/interlinear/compile_kokoro_both_previews.sh' \
  2>&1 | tee '$log_path'
"

echo "tmux: $session"
echo "log: $log_path"
echo "rechunk: $rechunk"
echo "chunk_mode: $chunk_mode"
echo "reference_scope: $reference_scope"
echo "codex_timeout_seconds: $codex_timeout_seconds"
