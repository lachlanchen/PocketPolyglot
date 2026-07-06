#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_trilingual_book_tmux.sh <book-id> [session]

Start a resumable tmux pipeline that writes trilingual EN/JP/ZH chunk JSON
with parallel Codex workers, merges accepted chunks in manifest order, and
periodically compiles the 12 standard pair PDFs.

Environment:
  WORKERS=10
  START_INDEX=1
  END_INDEX=0
  MAX_CHUNKS_PER_WORKER=0
  MODEL=gpt-5.5
  REASONING=high
  CODEX_TIMEOUT_SECONDS=7200
  MERGE_INTERVAL=180
  COMPILE_INTERVAL_SECONDS=1200
  WORKER_SCRIPT=scripts/interlinear/codex_trilingual_plain_json_worker.py
  BACKFILL_GRAMMAR_AFTER_MERGE=1
  RETRY_FAILED=0
  FAILED_RETRY_AGE_SECONDS=1800
  START_STALL_REPAIR=1
  REPAIR_SLEEP_SECONDS=300
  START_AUTOREPAIR_COMPANION=1
  AUTOREPAIR_ACTIVE_STALL_SECONDS=7200
USAGE
}

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="$1"
session="${2:-zhjpbook-${book_id}-trilingual}"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
manifest="$(jq -r '.chunks_manifest' "$plan")"
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
worker_script="${WORKER_SCRIPT:-scripts/interlinear/codex_trilingual_plain_json_worker.py}"

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
  retry_failed_arg=(--retry-failed --failed-retry-age-seconds "${FAILED_RETRY_AGE_SECONDS:-1800}")
fi

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$work_root/logs' '$candidate_dir' '$merged_dir' '$raw_chunk_dir'

gen_pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf 'tri-worker-%02d' "\$i")"
  python -u '$worker_script' \
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
  if [[ "\${BACKFILL_GRAMMAR_AFTER_MERGE:-1}" != "0" ]]; then
    if find '$raw_chunk_dir' -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
      python scripts/interlinear/backfill_trilingual_grammar_roles.py \
        --chunk-dir '$raw_chunk_dir' \
        --chunks-jsonl '$chunks_jsonl' \
        --overwrite-collapsed
    fi
  fi
}

compile_once() {
  if ! find '$raw_chunk_dir' -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
    echo "compile_skipped=no_merged_chunks"
    return 2
  fi
  ALLOW_MISSING=1 bash scripts/interlinear/compile_trilingual_book_12_previews.sh '$book_id'
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
    if compile_once; then
      last_compile="\$now"
    else
      compile_status="\$?"
      if [[ "\$compile_status" -eq 2 ]]; then
        # No merged chunks yet: keep the timer open so the first valid merge
        # compiles on the next monitor loop instead of waiting a full interval.
        last_compile=0
      else
        echo "compile_failed_status=\$compile_status retry_after_interval"
        last_compile="\$now"
      fi
    fi
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

if [[ "${START_STALL_REPAIR:-1}" != "0" ]]; then
  repair_session="${REPAIR_SESSION:-${session}-repair}"
  if tmux has-session -t "=$repair_session" 2>/dev/null; then
    echo "repair tmux already exists: $repair_session"
  else
    MODEL="$model" \
      REASONING="$reasoning" \
      CODEX_TIMEOUT_SECONDS="$codex_timeout_seconds" \
      REPAIR_SLEEP_SECONDS="${REPAIR_SLEEP_SECONDS:-300}" \
      WORKER_SCRIPT="$worker_script" \
      bash scripts/interlinear/start_trilingual_stall_repair_tmux.sh "$book_id" "$session" "$repair_session"
  fi
fi

shell_quote() {
  printf '%q' "$1"
}

if [[ "${START_AUTOREPAIR_COMPANION:-1}" != "0" ]]; then
  companion_session="${AUTOREPAIR_SESSION:-${session}-autorepair}"
  restart_cmd="START_AUTOREPAIR_COMPANION=0 START_STALL_REPAIR=1 RETRY_FAILED=1 START_INDEX={first_missing_index} WORKERS=$(shell_quote "$workers") MODEL=$(shell_quote "$model") REASONING=$(shell_quote "$reasoning") CODEX_TIMEOUT_SECONDS=$(shell_quote "$codex_timeout_seconds") MERGE_INTERVAL=$(shell_quote "$merge_interval") COMPILE_INTERVAL_SECONDS=$(shell_quote "$compile_interval_seconds") WORKER_SCRIPT=$(shell_quote "$worker_script") bash scripts/interlinear/start_trilingual_book_tmux.sh $(shell_quote "$book_id") $(shell_quote "$session")"
  bash scripts/interlinear/start_autorepair_companion_tmux.sh \
    --name "$session" \
    --session "$companion_session" \
    --state-dir "$work_root/autorepair" \
    --primary-session "$session" \
    --health-command "python scripts/interlinear/report_trilingual_progress.py --manifest $(shell_quote "$manifest") --chunk-dir $(shell_quote "$raw_chunk_dir")" \
    --health-nonzero-ok \
    --complete-key missing_chunks=0 \
    --complete-key stale_chunks=0 \
    --complete-key-eq manifest_chunks=valid_chunks \
    --watch "$raw_chunk_dir" \
    --watch "$candidate_dir" \
    --log "$work_root/logs/*.log" \
    --log "$log_dir/${session}_*.log" \
    --py-compile "$worker_script" \
    --py-compile scripts/interlinear/merge_trilingual_json_candidates.py \
    --py-compile scripts/interlinear/backfill_trilingual_grammar_roles.py \
    --start-command "$restart_cmd" \
    --allow-repair
fi

echo "tmux: $session"
echo "book_id: $book_id"
echo "workers: $workers"
echo "model: $model"
echo "reasoning: $reasoning"
echo "worker_script: $worker_script"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "max_chunks_per_worker: $max_chunks_per_worker"
echo "merge_interval: $merge_interval"
echo "compile_interval_seconds: $compile_interval_seconds"
echo "run_script: $run_script"
