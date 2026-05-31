#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="sichuan-folk-stories-vol1"
session="${1:-zhjpbook-sichuan-folk-json}"
workers="${WORKERS:-10}"
review_workers="${REVIEW_WORKERS:-6}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-0}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
merge_interval="${MERGE_INTERVAL:-180}"
review_merge_interval="${REVIEW_MERGE_INTERVAL:-300}"
enable_legacy_sanitizer="${ENABLE_LEGACY_SANITIZER:-0}"

work_root="books/$book_id/work/bilingual/parallel-json"
candidate_dir="$work_root/candidates"
merged_dir="$work_root/merged"
raw_chunk_dir="books/$book_id/work/bilingual/interlinear/chunks"
review_root="books/$book_id/work/bilingual/parallel-review"
review_candidate_dir="$review_root/candidates"
review_merged_dir="$review_root/merged"
review_rejected_dir="$review_root/merge-rejected"
review_done_file="$review_root/generation.done"
reviewed_chunk_dir="${SICHUAN_FOLK_CHUNK_DIR:-books/$book_id/work/bilingual/reviewed-v2/chunks}"
log_dir="books/$book_id/work/logs"
run_script="$work_root/${session}.run.sh"

mkdir -p \
  "$work_root" "$work_root/logs" "$candidate_dir" "$merged_dir" \
  "$review_root" "$review_root/logs" "$review_candidate_dir" "$review_merged_dir" "$review_rejected_dir" \
  "$reviewed_chunk_dir" "$log_dir"

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
if [[ "${RETRY_FAILED:-0}" == "1" ]]; then
  retry_failed_arg=(--retry-failed)
fi

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$work_root/logs' '$review_root/logs' '$review_candidate_dir' '$review_merged_dir' '$review_rejected_dir' '$reviewed_chunk_dir'
rm -f '$review_done_file'

gen_pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf 'worker-%02d' "\$i")"
  python -u scripts/interlinear/codex_bilingual_parallel_json_worker.py \
    --chunks-jsonl books/$book_id/work/bilingual/chunks/chunks.jsonl \
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

review_pids=()
for i in \$(seq 1 '$review_workers'); do
  worker_id="\$(printf 'review-%02d' "\$i")"
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
    --idle-sleep 30 \
    --done-file '$review_done_file' \
    > "$review_root/logs/\$worker_id.log" 2>&1 &
  review_pids+=("\$!")
done

merge_once() {
  python scripts/interlinear/merge_parallel_json_candidates.py \
    --chunks-jsonl books/$book_id/work/bilingual/chunks/chunks.jsonl \
    --candidate-dir '$candidate_dir' \
    --canonical-dir '$raw_chunk_dir' \
    --merged-dir '$merged_dir'
}

review_merge_once() {
  python scripts/interlinear/merge_reviewed_chunks.py \
    --chunks-jsonl books/$book_id/work/bilingual/chunks/chunks.jsonl \
    --candidate-dir '$review_candidate_dir' \
    --final-dir '$reviewed_chunk_dir' \
    --merged-dir '$review_merged_dir' \
    --rejected-dir '$review_rejected_dir' \
    --after-merge-command 'SICHUAN_FOLK_CHUNK_DIR="$reviewed_chunk_dir" bash scripts/interlinear/compile_sichuan_folk_both_previews.sh'
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

while [[ "\$(running_count "\${gen_pids[@]}")" -gt 0 ]]; do
  merge_once
  review_merge_once
  sleep '$merge_interval'
done

status=0
for pid in "\${gen_pids[@]}"; do
  if ! wait "\$pid"; then
    status=1
  fi
done
merge_once
touch '$review_done_file'

while [[ "\$(running_count "\${review_pids[@]}")" -gt 0 ]]; do
  review_merge_once
  sleep '$review_merge_interval'
done

for pid in "\${review_pids[@]}"; do
  if ! wait "\$pid"; then
    status=1
  fi
done
review_merge_once
exit "\$status"
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n parallel-json "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

if [[ "${AUTOREPAIR_COMPANION:-1}" != "0" ]]; then
  sanitizer_session_arg=""
  sanitizer_command_arg=""
  if [[ "$enable_legacy_sanitizer" == "1" ]]; then
    sanitizer_session_arg="${SANITIZER_SESSION:-zhjpbook-sichuan-folk-sanitizer}"
    sanitizer_command_arg="MODEL=$model REASONING=$reasoning RETRY_FAILED=1 bash scripts/interlinear/start_sichuan_folk_sanitizer_tmux.sh $sanitizer_session_arg"
  fi
  if ! BOOK_ID="$book_id" \
    GUARDIAN_SESSION="${session}-autorepair" \
    WORKER_SESSION="$session" \
    REVIEW_SESSION="$session" \
    SANITIZER_SESSION="$sanitizer_session_arg" \
    START_COMMAND="SICHUAN_FOLK_CHUNK_DIR=$reviewed_chunk_dir MODEL=$model REASONING=$reasoning RETRY_FAILED=1 bash scripts/interlinear/start_sichuan_folk_parallel_json_tmux.sh $session" \
    SANITIZER_COMMAND="$sanitizer_command_arg" \
    COMPILE_COMMAND="SICHUAN_FOLK_CHUNK_DIR=$reviewed_chunk_dir bash scripts/interlinear/compile_sichuan_folk_both_previews.sh" \
    COMMIT_COMMAND="SICHUAN_FOLK_CHUNK_DIR=$reviewed_chunk_dir bash scripts/interlinear/commit_sichuan_folk_progress.sh" \
    INTERVAL_SECONDS="${AUTOREPAIR_INTERVAL_SECONDS:-900}" \
    STALL_SECONDS="${AUTOREPAIR_STALL_SECONDS:-3600}" \
    MODEL="$model" \
    REASONING="$reasoning" \
    bash scripts/interlinear/start_autorepair_companion_tmux.sh "$book_id"; then
    echo "warning: autorepair companion did not start" >&2
  fi
fi

echo "tmux: $session"
echo "workers: $workers"
echo "review_workers: $review_workers"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "max_chunks_per_worker: $max_chunks_per_worker"
echo "merge_interval: $merge_interval"
echo "review_merge_interval: $review_merge_interval"
echo "codex_timeout_seconds: $codex_timeout_seconds"
echo "run_script: $run_script"
