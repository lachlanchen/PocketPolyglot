#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_quadrilingual_wenyan_tmux.sh <book-id> [session]

Environment:
  WORKERS=6
  MODEL=gpt-5.5
  REASONING=high
  START_INDEX=1
  END_INDEX=0
  MAX_CHUNKS_PER_WORKER=0
  MERGE_INTERVAL=180
  COMPILE_INTERVAL_SECONDS=1800
  MAIN_LAYERS="wenyan"
  RETRY_FAILED=0
  FAILED_RETRY_AGE_SECONDS=1800
USAGE
}

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="$1"
session="${2:-zhjpbook-${book_id}-quadrilingual}"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
manifest="$(jq -r '.chunks_manifest' "$plan")"
raw_chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
workers="${WORKERS:-6}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-high}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-0}"
max_chunks="${MAX_CHUNKS_PER_WORKER:-0}"
merge_interval="${MERGE_INTERVAL:-180}"
compile_interval="${COMPILE_INTERVAL_SECONDS:-1800}"
main_layers="${MAIN_LAYERS:-wenyan}"
timeout="${CODEX_TIMEOUT_SECONDS:-7200}"
retry_failed="${RETRY_FAILED:-0}"
failed_retry_age="${FAILED_RETRY_AGE_SECONDS:-1800}"

work_root="books/$book_id/work/quadrilingual/parallel-json"
candidate_dir="$work_root/candidates"
log_dir="books/$book_id/work/logs"
run_script="$work_root/${session}.run.sh"
mkdir -p "$work_root/logs" "$candidate_dir" "$raw_chunk_dir" "$log_dir"

end_arg=""
if [[ "$end_index" != "0" ]]; then
  end_arg="--end-index '$end_index'"
fi
retry_failed_arg=""
if [[ "$retry_failed" == "1" || "$retry_failed" == "true" ]]; then
  retry_failed_arg="--retry-failed --failed-retry-age-seconds '$failed_retry_age'"
fi

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$work_root/logs' '$candidate_dir' '$raw_chunk_dir'

pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf 'quad-worker-%02d' "\$i")"
  python -u scripts/interlinear/codex_quadrilingual_wenyan_worker.py \
    --chunks-jsonl '$chunks_jsonl' \
    --canonical-dir '$raw_chunk_dir' \
    --candidate-dir '$candidate_dir' \
    --work-dir "$work_root/\$worker_id" \
    --worker-id "\$worker_id" \
    --model '$model' \
    --reasoning '$reasoning' \
    --start-index '$start_index' \
    $end_arg \
    --max-chunks '$max_chunks' \
    --codex-timeout-seconds '$timeout' \
    $retry_failed_arg \
    --retries 4 \
    > "$work_root/logs/\$worker_id.log" 2>&1 &
  pids+=("\$!")
done

running_count() {
  local count=0
  local pid
  for pid in "\$@"; do
    if kill -0 "\$pid" 2>/dev/null; then
      count=\$((count + 1))
    fi
  done
  echo "\$count"
}

compile_once() {
  python scripts/interlinear/report_quadrilingual_progress.py --manifest '$manifest' --chunks-jsonl '$chunks_jsonl' --chunk-dir '$raw_chunk_dir' || true
  if ! find '$raw_chunk_dir' -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
    echo "compile_skipped=no_quadrilingual_chunks"
    return 0
  fi
  for layer in $main_layers; do
    ALLOW_MISSING=1 bash scripts/interlinear/compile_quadrilingual_wenyan_book.sh --book-id '$book_id' --main-layer "\$layer" --color-mode color --allow-missing || true
    ALLOW_MISSING=1 bash scripts/interlinear/compile_quadrilingual_wenyan_book.sh --book-id '$book_id' --main-layer "\$layer" --color-mode blackwhite --allow-missing || true
  done
}

last_compile=0
while [[ "\$(running_count "\${pids[@]}")" -gt 0 ]]; do
  now="\$(date +%s)"
  if [[ '$compile_interval' -gt 0 && \$((now - last_compile)) -ge '$compile_interval' ]]; then
    compile_once
    last_compile="\$now"
  fi
  sleep '$merge_interval'
done

status=0
for pid in "\${pids[@]}"; do
  if ! wait "\$pid"; then
    status=1
  fi
done
compile_once
exit "\$status"
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n quadrilingual-json "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "book_id: $book_id"
echo "workers: $workers"
echo "model: $model"
echo "reasoning: $reasoning"
echo "main_layers: $main_layers"
echo "retry_failed: $retry_failed"
echo "run_script: $run_script"
