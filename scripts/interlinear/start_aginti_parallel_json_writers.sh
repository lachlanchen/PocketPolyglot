#!/usr/bin/env bash
set -euo pipefail

book="${1:-${BOOK:-sishu-jizhu-aginti}}"
workers="${WORKERS:-10}"
start_chunk="${START_CHUNK:-}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
delay="${DELAY:-1}"
api_timeout="${AGINTI_API_TIMEOUT:-180}"
api_retries="${AGINTI_API_RETRIES:-2}"
invalid_retries="${AGINTI_INVALID_RETRIES:-2}"
max_tokens="${AGINTI_MAX_TOKENS:-16384}"
compile_at_end="${COMPILE_AT_END:-1}"
async_review="${ASYNC_REVIEW:-1}"
review_interval="${REVIEW_INTERVAL:-180}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
log_dir="${LOG_DIR:-logs/${book}-json-workers-${run_id}}"

if [[ -z "$start_chunk" ]]; then
  start_chunk="$(
    python3 - <<'PY' "$book"
import json
import sys
from pathlib import Path

book = sys.argv[1]
path = Path("data") / "interlinear" / book / "status.json"
try:
    status = json.loads(path.read_text(encoding="utf-8"))
    print(status.get("first_missing") or 1)
except Exception:
    print(1)
PY
  )"
fi

mkdir -p "$log_dir"

{
  echo "book=$book"
  echo "workers=$workers"
  echo "start_chunk=$start_chunk"
  echo "max_chunks_per_worker=$max_chunks_per_worker"
  echo "delay=$delay"
  echo "api_timeout=$api_timeout"
  echo "api_retries=$api_retries"
  echo "invalid_retries=$invalid_retries"
  echo "max_tokens=$max_tokens"
  echo "compile_at_end=$compile_at_end"
  echo "async_review=$async_review"
  echo "review_interval=$review_interval"
  echo "started=$(date -Is)"
} | tee "$log_dir/run.env"

done_file="$log_dir/generation.done"
review_pid=""
if [[ "$async_review" == "1" ]]; then
  (
    while true; do
      python3 scripts/interlinear/aginti_write_chunks.py \
        --book "$book" \
        --promote-existing-only \
        --retry-failed-passes 0 \
        --compile-every 0 \
        >>"$log_dir/async-review-promote.log" 2>&1 || true
      [[ -f "$done_file" ]] && break
      sleep "$review_interval"
    done
  ) &
  review_pid="$!"
  echo "async_review_pid=$review_pid" | tee -a "$log_dir/run.env"
fi

pids=()
for ((worker_index = 0; worker_index < workers; worker_index += 1)); do
  worker_num="$(printf "%02d" "$((worker_index + 1))")"
  (
    exec python3 -u scripts/interlinear/aginti_write_chunks.py \
      --book "$book" \
      --start-chunk "$start_chunk" \
      --max-chunks "$max_chunks_per_worker" \
      --delay "$delay" \
      --api-timeout "$api_timeout" \
      --api-retries "$api_retries" \
      --invalid-retries "$invalid_retries" \
      --max-tokens "$max_tokens" \
      --worker-count "$workers" \
      --worker-index "$worker_index" \
      --retry-failed-passes 0 \
      --compile-every 0
  ) >"$log_dir/worker-${worker_num}.log" 2>&1 &
  pids+=("$!")
  echo "worker-${worker_num} pid=${pids[-1]}" | tee -a "$log_dir/run.env"
done

failed=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    failed=1
  fi
done

touch "$done_file"
if [[ -n "$review_pid" ]]; then
  if ! wait "$review_pid"; then
    failed=1
  fi
fi

python3 scripts/interlinear/aginti_write_chunks.py \
  --book "$book" \
  --promote-existing-only \
  --retry-failed-passes 0 \
  --compile-every 0 \
  >"$log_dir/final-promote-status.log" 2>&1 || failed=1

if [[ "$compile_at_end" == "1" ]]; then
  COMMIT_PROGRESS=0 bash scripts/interlinear/compile_prepared_book_both_previews.sh "$book" \
    >"$log_dir/final-compile.log" 2>&1 || failed=1
fi

echo "finished=$(date -Is) failed=$failed" | tee -a "$log_dir/run.env"
exit "$failed"
