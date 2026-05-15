#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-parallel-json}"
workers="${WORKERS:-10}"
start_index="${START_INDEX:-26}"
end_index="${END_INDEX:-0}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-xhigh}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
merge_interval="${MERGE_INTERVAL:-180}"
work_root="books/kokoro/work/bilingual/parallel-json"
candidate_dir="$work_root/candidates"
merged_dir="$work_root/merged"
log_dir="books/kokoro/work/logs"
run_script="$work_root/${session}.run.sh"
mkdir -p "$work_root" "$candidate_dir" "$merged_dir" "$log_dir"

if tmux has-session -t "$session" 2>/dev/null; then
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
mkdir -p '$work_root/logs'

pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf 'worker-%02d' "\$i")"
  python -u scripts/interlinear/codex_bilingual_parallel_json_worker.py \
    --chunks-jsonl books/kokoro/work/bilingual/chunks/chunks.jsonl \
    --canonical-dir books/kokoro/work/bilingual/interlinear/chunks \
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
  pids+=("\$!")
done

merge_once() {
  python scripts/interlinear/merge_parallel_json_candidates.py \
    --chunks-jsonl books/kokoro/work/bilingual/chunks/chunks.jsonl \
    --candidate-dir '$candidate_dir' \
    --canonical-dir books/kokoro/work/bilingual/interlinear/chunks \
    --merged-dir '$merged_dir' \
    --after-merge-command 'bash scripts/interlinear/review_compile_kokoro_merged.sh'
}

while true; do
  merge_once
  running="\$(jobs -pr | wc -l | tr -d ' ')"
  if [[ "\$running" -eq 0 ]]; then
    break
  fi
  sleep '$merge_interval'
done

status=0
for pid in "\${pids[@]}"; do
  if ! wait "\$pid"; then
    status=1
  fi
done
merge_once
exit "\$status"
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n parallel-json "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "workers: $workers"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "max_chunks_per_worker: $max_chunks_per_worker"
echo "merge_interval: $merge_interval"
echo "codex_timeout_seconds: $codex_timeout_seconds"
echo "run_script: $run_script"
