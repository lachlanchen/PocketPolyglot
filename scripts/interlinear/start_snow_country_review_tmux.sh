#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-snow-country-review}"
review_workers="${REVIEW_WORKERS:-6}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-0}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-xhigh}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
review_merge_interval="${REVIEW_MERGE_INTERVAL:-300}"

raw_chunk_dir="books/snow-country/work/bilingual/interlinear/chunks"
review_root="books/snow-country/work/bilingual/parallel-review"
review_candidate_dir="$review_root/candidates"
review_merged_dir="$review_root/merged"
review_rejected_dir="$review_root/merge-rejected"
review_done_file="$review_root/generation.done"
reviewed_chunk_dir="books/snow-country/work/bilingual/reviewed/chunks"
log_dir="books/snow-country/work/logs"
run_script="$review_root/${session}.run.sh"

mkdir -p "$review_root/logs" "$review_candidate_dir" "$review_merged_dir" "$review_rejected_dir" "$reviewed_chunk_dir" "$log_dir"

if [[ ! -f books/snow-country/work/bilingual/chunks/chunks.jsonl ]]; then
  echo "Snow Country chunks are missing; run scripts/interlinear/prepare_snow_country_sources.sh first." >&2
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

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$review_root/logs' '$review_candidate_dir' '$review_merged_dir' '$review_rejected_dir' '$reviewed_chunk_dir'

review_pids=()
for i in \$(seq 1 '$review_workers'); do
  worker_id="\$(printf 'review-refresh-%02d' "\$i")"
  python -u scripts/interlinear/codex_parallel_review_worker.py \
    --chunks-jsonl books/snow-country/work/bilingual/chunks/chunks.jsonl \
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

review_merge_once() {
  python scripts/interlinear/merge_reviewed_chunks.py \
    --chunks-jsonl books/snow-country/work/bilingual/chunks/chunks.jsonl \
    --candidate-dir '$review_candidate_dir' \
    --final-dir '$reviewed_chunk_dir' \
    --merged-dir '$review_merged_dir' \
    --rejected-dir '$review_rejected_dir' \
    --after-merge-command 'bash scripts/interlinear/compile_snow_country_both_previews.sh'
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

status=0
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

tmux new-session -d -s "$session" -n review "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "review_workers: $review_workers"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "max_chunks_per_worker: $max_chunks_per_worker"
echo "review_merge_interval: $review_merge_interval"
echo "codex_timeout_seconds: $codex_timeout_seconds"
echo "run_script: $run_script"
