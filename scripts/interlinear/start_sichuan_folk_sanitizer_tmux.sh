#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="sichuan-folk-stories-vol1"
session="${1:-zhjpbook-sichuan-folk-sanitizer}"
workers="${SANITIZER_WORKERS:-4}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-816}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
work_root="books/$book_id/work/bilingual/sanitizer"
raw_chunk_dir="books/$book_id/work/bilingual/interlinear/chunks"
reviewed_chunk_dir="books/$book_id/work/bilingual/reviewed/chunks"
log_dir="books/$book_id/work/logs"
session_log_dir="$work_root/logs/$session"
run_script="$work_root/${session}.run.sh"

mkdir -p "$work_root" "$session_log_dir" "$raw_chunk_dir" "$reviewed_chunk_dir" "$log_dir"

if [[ ! -f "books/$book_id/work/bilingual/chunks/chunks.jsonl" ]]; then
  echo "Sichuan folk story chunks are missing; run scripts/interlinear/prepare_sichuan_folk_sources.sh first." >&2
  exit 1
fi

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

retry_failed_arg=()
if [[ "${RETRY_FAILED:-0}" == "1" ]]; then
  retry_failed_arg=(--retry-failed)
fi

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$session_log_dir'

pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf 'sanitizer-%02d' "\$i")"
  python -u scripts/interlinear/codex_sanitize_interlinear_range_worker.py \
    --chunks-jsonl books/$book_id/work/bilingual/chunks/chunks.jsonl \
    --read-dir '$reviewed_chunk_dir' \
    --read-dir '$raw_chunk_dir' \
    --write-dir '$raw_chunk_dir' \
    --write-dir '$reviewed_chunk_dir' \
    --work-dir '$work_root/shared' \
    --worker-id "\$worker_id" \
    --model '$model' \
    --reasoning '$reasoning' \
    --start-index '$start_index' \
    --end-index '$end_index' \
    --max-chunks '$max_chunks_per_worker' \
    --codex-timeout-seconds '$codex_timeout_seconds' \
    ${retry_failed_arg[*]} \
    --retries 2 \
    > "$session_log_dir/\$worker_id.log" 2>&1 &
  pids+=("\$!")
done

status=0
for pid in "\${pids[@]}"; do
  if ! wait "\$pid"; then
    status=1
  fi
done

bash scripts/interlinear/compile_sichuan_folk_both_previews.sh || status=1
exit "\$status"
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n sanitizer "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "workers: $workers"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "max_chunks_per_worker: $max_chunks_per_worker"
echo "model: $model"
echo "reasoning: $reasoning"
echo "codex_timeout_seconds: $codex_timeout_seconds"
echo "run_script: $run_script"
