#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_quadrilingual_wenyan_tmux.sh <book-id> [session]

Environment:
  WORKERS=6
  MODEL=gpt-5.5
  REASONING=high
  WORKER_PREFIX=quad-worker
  START_INDEX=1
  END_INDEX=0
  MAX_CHUNKS_PER_WORKER=0
  MERGE_INTERVAL=180
  COMPILE_INTERVAL_SECONDS=1800
  MAIN_LAYERS="wenyan"
  CLAIM_TTL_SECONDS=1800
  CODEX_TIMEOUT_SECONDS=1200
  CODEX_EXEC_IGNORE_USER_CONFIG=1
  CODEX_EXEC_IGNORE_RULES=1
  RETRY_FAILED=0
  FAILED_RETRY_AGE_SECONDS=1800
  CHUNKS_JSONL_OVERRIDE=
  MANIFEST_OVERRIDE=
  RAW_CHUNK_DIR_OVERRIDE=
  WORK_ROOT_OVERRIDE=
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

chunks_jsonl="${CHUNKS_JSONL_OVERRIDE:-$(jq -r '.chunks_jsonl' "$plan")}"
manifest="${MANIFEST_OVERRIDE:-$(jq -r '.chunks_manifest' "$plan")}"
raw_chunk_dir="${RAW_CHUNK_DIR_OVERRIDE:-$(jq -r '.raw_chunk_dir' "$plan")}"
workers="${WORKERS:-6}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-high}"
worker_prefix="${WORKER_PREFIX:-quad-worker}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-0}"
max_chunks="${MAX_CHUNKS_PER_WORKER:-0}"
merge_interval="${MERGE_INTERVAL:-180}"
compile_interval="${COMPILE_INTERVAL_SECONDS:-1800}"
main_layers="${MAIN_LAYERS:-wenyan}"
claim_ttl="${CLAIM_TTL_SECONDS:-1800}"
timeout="${CODEX_TIMEOUT_SECONDS:-1200}"
retry_failed="${RETRY_FAILED:-0}"
failed_retry_age="${FAILED_RETRY_AGE_SECONDS:-1800}"
ignore_user_config="${CODEX_EXEC_IGNORE_USER_CONFIG:-1}"
ignore_rules="${CODEX_EXEC_IGNORE_RULES:-1}"

work_root="${WORK_ROOT_OVERRIDE:-books/$book_id/work/quadrilingual/parallel-json}"
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
export CODEX_EXEC_IGNORE_USER_CONFIG='$ignore_user_config'
export CODEX_EXEC_IGNORE_RULES='$ignore_rules'

pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf '$worker_prefix-%03d' "\$i")"
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
    --claim-ttl-seconds '$claim_ttl' \
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
    # Exited children can remain as zombies until the final wait loop reaps
    # them.  kill -0 still succeeds for those PIDs, so exclude Z states here
    # to avoid keeping long-running tmux monitors alive forever after all
    # workers have completed.
    local stat
    stat="\$(ps -o stat= -p "\$pid" 2>/dev/null || true)"
    if [[ -n "\$stat" && "\$stat" != Z* ]] && kill -0 "\$pid" 2>/dev/null; then
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

shell_quote() {
  printf '%q' "$1"
}

if [[ "${START_AUTOREPAIR_COMPANION:-1}" != "0" ]]; then
  companion_session="${AUTOREPAIR_SESSION:-${session}-autorepair}"
  restart_cmd="START_AUTOREPAIR_COMPANION=0 RETRY_FAILED=1 WORKERS=$(shell_quote "$workers") MODEL=$(shell_quote "$model") REASONING=$(shell_quote "$reasoning") WORKER_PREFIX=$(shell_quote "$worker_prefix") CLAIM_TTL_SECONDS=$(shell_quote "$claim_ttl") CODEX_TIMEOUT_SECONDS=$(shell_quote "$timeout") MERGE_INTERVAL=$(shell_quote "$merge_interval") COMPILE_INTERVAL_SECONDS=$(shell_quote "$compile_interval") MAIN_LAYERS=$(shell_quote "$main_layers") bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh $(shell_quote "$book_id") $(shell_quote "$session")"
  bash scripts/interlinear/start_autorepair_companion_tmux.sh \
    --name "$session" \
    --session "$companion_session" \
    --state-dir "$work_root/autorepair" \
    --primary-session "$session" \
    --health-command "python scripts/interlinear/report_quadrilingual_progress.py --manifest $(shell_quote "$manifest") --chunks-jsonl $(shell_quote "$chunks_jsonl") --chunk-dir $(shell_quote "$raw_chunk_dir")" \
    --health-nonzero-ok \
    --complete-ratio valid \
    --complete-key missing=0 \
    --complete-key stale=0 \
    --watch "$raw_chunk_dir" \
    --watch "$candidate_dir" \
    --log "$work_root/logs/*.log" \
    --log "$log_dir/${session}_*.log" \
    --py-compile scripts/interlinear/codex_quadrilingual_wenyan_worker.py \
    --py-compile scripts/interlinear/backfill_quadrilingual_grammar_roles.py \
    --py-compile scripts/interlinear/assemble_quadrilingual_json.py \
    --py-compile scripts/interlinear/validate_quadrilingual_interlinear_json.py \
    --start-command "$restart_cmd" \
    --allow-repair
fi

echo "tmux: $session"
echo "book_id: $book_id"
echo "workers: $workers"
echo "model: $model"
echo "reasoning: $reasoning"
echo "worker_prefix: $worker_prefix"
echo "claim_ttl_seconds: $claim_ttl"
echo "codex_timeout_seconds: $timeout"
echo "main_layers: $main_layers"
echo "retry_failed: $retry_failed"
echo "run_script: $run_script"
