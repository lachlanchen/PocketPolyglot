#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="gone-with-the-wind"
session="${1:-zhjpbook-${book_id}-trilingual}"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan; run scripts/interlinear/prepare_gone_with_the_wind_trilingual.py first." >&2
  exit 1
fi

chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
raw_chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
if [[ ! -f "$chunks_jsonl" ]]; then
  echo "Missing chunks jsonl: $chunks_jsonl" >&2
  exit 1
fi

workers="${WORKERS:-10}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-0}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-high}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
merge_interval="${MERGE_INTERVAL:-180}"
compile_interval_seconds="${COMPILE_INTERVAL_SECONDS:-1200}"

work_root="books/$book_id/work/trilingual/parallel-json"
candidate_dir="$work_root/candidates"
merged_dir="$work_root/merged"
log_dir="books/$book_id/work/logs"
run_script="$work_root/${session}.run.sh"
mkdir -p "$work_root" "$work_root/logs" "$candidate_dir" "$merged_dir" "$raw_chunk_dir" "$log_dir"

if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

end_arg=()
if [[ "$end_index" != "0" ]]; then
  end_arg=(--end-index "$end_index")
fi
retry_failed_arg=()
if [[ "${RETRY_FAILED:-0}" == "1" ]]; then
  retry_failed_arg=(--retry-failed)
fi

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$work_root/logs' '$candidate_dir' '$merged_dir' '$raw_chunk_dir'

gen_pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf 'tri-worker-%02d' "\$i")"
  python -u scripts/interlinear/codex_trilingual_parallel_json_worker.py \
    --chunks-jsonl '$chunks_jsonl' \
    --canonical-dir '$raw_chunk_dir' \
    --candidate-dir '$candidate_dir' \
    --work-dir "$work_root/\$worker_id" \
    --worker-id "\$worker_id" \
    --model '$model' \
    --reasoning '$reasoning' \
    --start-index '$start_index' \
    ${end_arg[*]} \
    --max-chunks '$max_chunks_per_worker' \
    --codex-timeout-seconds '$codex_timeout_seconds' \
    ${retry_failed_arg[*]} \
    --retries 4 \
    > "$work_root/logs/\$worker_id.log" 2>&1 &
  gen_pids+=("\$!")
done

merge_once() {
  python scripts/interlinear/merge_trilingual_json_candidates.py \
    --chunks-jsonl '$chunks_jsonl' \
    --candidate-dir '$candidate_dir' \
    --canonical-dir '$raw_chunk_dir' \
    --merged-dir '$merged_dir'
}

compile_once() {
  ALLOW_MISSING=1 bash scripts/interlinear/compile_gone_with_the_wind_12_previews.sh
}

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

last_compile=0
while [[ "\$(running_count "\${gen_pids[@]}")" -gt 0 ]]; do
  merge_once
  now="\$(date +%s)"
  if [[ '$compile_interval_seconds' -gt 0 && \$((now - last_compile)) -ge '$compile_interval_seconds' ]]; then
    compile_once || true
    last_compile="\$now"
  fi
  sleep '$merge_interval'
done

status=0
for pid in "\${gen_pids[@]}"; do
  if ! wait "\$pid"; then
    status=1
  fi
done
merge_once
compile_once || true
exit "\$status"
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n trilingual-json "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "book_id: $book_id"
echo "workers: $workers"
echo "model: $model"
echo "reasoning: $reasoning"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "max_chunks_per_worker: $max_chunks_per_worker"
echo "merge_interval: $merge_interval"
echo "compile_interval_seconds: $compile_interval_seconds"
echo "run_script: $run_script"
