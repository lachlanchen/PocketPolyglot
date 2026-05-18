#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="sichuan-folk-stories-vol1"
session="${1:-zhjpbook-sichuan-folk-review-v2}"
workers="${REVIEW_WORKERS:-4}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-0}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
merge_interval="${REVIEW_MERGE_INTERVAL:-300}"
restart_interval="${REVIEW_RESTART_INTERVAL_SECONDS:-3600}"
retry_failed="${RETRY_FAILED:-0}"
raw_chunk_dir="${RAW_CHUNK_DIR:-books/$book_id/work/bilingual/interlinear/chunks}"
review_root="${REVIEW_ROOT:-books/$book_id/work/bilingual/parallel-review-v2}"
review_candidate_dir="$review_root/candidates"
review_merged_dir="$review_root/merged"
review_rejected_dir="$review_root/merge-rejected"
reviewed_chunk_dir="${REVIEWED_CHUNK_DIR:-books/$book_id/work/bilingual/reviewed-v2/chunks}"
done_file="$review_root/generation.done"
log_dir="books/$book_id/work/logs"
run_script="$review_root/${session}.run.sh"

mkdir -p \
  "$review_root" "$review_root/logs" "$review_candidate_dir" "$review_merged_dir" \
  "$review_rejected_dir" "$reviewed_chunk_dir" "$log_dir"

if [[ ! -f "books/$book_id/work/bilingual/chunks/chunks.jsonl" ]]; then
  echo "Sichuan folk story chunks are missing; run scripts/interlinear/prepare_sichuan_folk_sources.sh first." >&2
  exit 1
fi

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

end_arg=()
if [[ "$end_index" != "0" ]]; then
  end_arg=(--end-index "$end_index")
fi
retry_failed_arg=()
if [[ "$retry_failed" == "1" ]]; then
  retry_failed_arg=(--retry-failed)
fi

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$review_root/logs' '$review_candidate_dir' '$review_merged_dir' '$review_rejected_dir' '$reviewed_chunk_dir'
rm -f '$done_file'

declare -A pids
declare -A last_start

spawn_worker() {
  local i="\$1"
  local worker_id
  worker_id="\$(printf 'review-v2-%02d' "\$i")"
  python -u scripts/interlinear/codex_parallel_review_worker.py \
    --chunks-jsonl books/$book_id/work/bilingual/chunks/chunks.jsonl \
    --raw-dir '$raw_chunk_dir' \
    --final-dir '$reviewed_chunk_dir' \
    --candidate-dir '$review_candidate_dir' \
    --work-dir "$review_root/\$worker_id" \
    --worker-id "\$worker_id" \
    --model '$model' \
    --reasoning '$reasoning' \
    --start-index '$start_index' \
    ${end_arg[*]} \
    --max-chunks '$max_chunks_per_worker' \
    --codex-timeout-seconds '$codex_timeout_seconds' \
    --retries 2 \
    ${retry_failed_arg[*]} \
    --idle-sleep 60 \
    --done-file '$done_file' \
    > "$review_root/logs/\$worker_id.log" 2>&1 &
  pids["\$i"]="\$!"
  last_start["\$i"]="\$(date +%s)"
  echo "started \$worker_id pid=\${pids[\$i]}"
}

merge_once() {
  python scripts/interlinear/merge_reviewed_chunks.py \
    --chunks-jsonl books/$book_id/work/bilingual/chunks/chunks.jsonl \
    --candidate-dir '$review_candidate_dir' \
    --final-dir '$reviewed_chunk_dir' \
    --merged-dir '$review_merged_dir' \
    --rejected-dir '$review_rejected_dir' \
    ${AFTER_MERGE_COMMAND:+--after-merge-command "$AFTER_MERGE_COMMAND"}
}

for i in \$(seq 1 '$workers'); do
  spawn_worker "\$i"
done

while true; do
  now="\$(date +%s)"
  for i in \$(seq 1 '$workers'); do
    pid="\${pids[\$i]:-}"
    if [[ -n "\$pid" ]] && kill -0 "\$pid" 2>/dev/null; then
      continue
    fi
    last="\${last_start[\$i]:-0}"
    if (( now - last >= '$restart_interval' )); then
      spawn_worker "\$i"
    else
      echo "review-v2-\$(printf '%02d' "\$i") is down; waiting for restart interval"
    fi
  done
  merge_once || true
  sleep '$merge_interval'
done
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n async-review "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "workers: $workers"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "review_root: $review_root"
echo "raw_chunk_dir: $raw_chunk_dir"
echo "reviewed_chunk_dir: $reviewed_chunk_dir"
echo "merge_interval: $merge_interval"
echo "restart_interval: $restart_interval"
echo "retry_failed: $retry_failed"
echo "model: $model"
echo "reasoning: $reasoning"
echo "run_script: $run_script"
