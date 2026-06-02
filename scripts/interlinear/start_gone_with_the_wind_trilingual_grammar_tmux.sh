#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="gone-with-the-wind"
session="${1:-zhjpbook-${book_id}-trilingual-grammar}"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

manifest="$(jq -r '.chunks_manifest' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"

workers="${WORKERS:-4}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-0}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-high}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
idle_sleep_seconds="${IDLE_SLEEP_SECONDS:-60}"
compile_interval_seconds="${COMPILE_INTERVAL_SECONDS:-1800}"

work_root="books/$book_id/work/trilingual/grammar-role-repair"
log_dir="books/$book_id/work/logs"
run_script="$work_root/${session}.run.sh"
mkdir -p "$work_root/logs" "$log_dir"

if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

end_arg=()
if [[ "$end_index" != "0" ]]; then
  end_arg=(--end-index "$end_index")
fi

force_arg=()
if [[ "${FORCE:-0}" == "1" ]]; then
  force_arg=(--force)
fi

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$work_root/logs'

worker_pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf 'tri-grammar-%02d' "\$i")"
  python -u scripts/interlinear/codex_trilingual_grammar_role_worker.py \
    --manifest '$manifest' \
    --chunks-jsonl '$chunks_jsonl' \
    --chunk-dir '$chunk_dir' \
    --work-dir '$work_root' \
    --worker-id "\$worker_id" \
    --model '$model' \
    --reasoning '$reasoning' \
    --start-index '$start_index' \
    ${end_arg[*]} \
    --max-chunks '$max_chunks_per_worker' \
    --codex-timeout-seconds '$codex_timeout_seconds' \
    --idle-sleep-seconds '$idle_sleep_seconds' \
    ${force_arg[*]} \
    --watch \
    --retries 4 \
    > "$work_root/logs/\$worker_id.log" 2>&1 &
  worker_pids+=("\$!")
done

compile_once() {
  if ! find '$chunk_dir' -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
    echo "compile_skipped=no_chunks"
    return 0
  fi
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

last_compile="\$(date +%s)"
while [[ "\$(running_count "\${worker_pids[@]}")" -gt 0 ]]; do
  now="\$(date +%s)"
  if [[ '$compile_interval_seconds' -gt 0 && \$((now - last_compile)) -ge '$compile_interval_seconds' ]]; then
    compile_once || true
    last_compile="\$now"
  fi
  sleep 120
done

status=0
for pid in "\${worker_pids[@]}"; do
  if ! wait "\$pid"; then
    status=1
  fi
done
compile_once || true
exit "\$status"
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n trilingual-grammar "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "book_id: $book_id"
echo "workers: $workers"
echo "model: $model"
echo "reasoning: $reasoning"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "max_chunks_per_worker: $max_chunks_per_worker"
echo "compile_interval_seconds: $compile_interval_seconds"
echo "run_script: $run_script"
