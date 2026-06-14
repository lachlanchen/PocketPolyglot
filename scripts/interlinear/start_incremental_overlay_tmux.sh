#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-incremental-en-modern-ja}"
workers="${WORKERS:-10}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-high}"
max_chunks_per_worker="${MAX_CHUNKS_PER_WORKER:-0}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
usage_limit_sleep_seconds="${CODEX_USAGE_LIMIT_WAIT_SECONDS:-3600}"
min_codex_remaining_percent="${MIN_CODEX_REMAINING_PERCENT:-0}"
codex_usage_status_file="${CODEX_USAGE_STATUS_FILE:-}"
codex_usage_check_command="${CODEX_USAGE_CHECK_COMMAND:-}"
codex_usage_allow_unknown="${CODEX_USAGE_ALLOW_UNKNOWN:-0}"
work_dir="${WORK_DIR:-books/_incremental-overlays/work/en-modern-ja}"
global_manifest="${GLOBAL_MANIFEST:-data/source-plan/incremental-english-modern-japanese.json}"

if [[ ! -f "$global_manifest" ]]; then
  echo "Missing global manifest: $global_manifest" >&2
  exit 1
fi

if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

include_waiting_arg=()
if [[ "${INCLUDE_WAITING_DEPENDENCIES:-0}" == "1" ]]; then
  include_waiting_arg=(--include-waiting-dependencies)
fi

retry_failed_arg=()
if [[ "${RETRY_FAILED:-0}" == "1" ]]; then
  retry_failed_arg=(--retry-failed)
fi

budget_arg=()
if [[ "$min_codex_remaining_percent" != "0" && "$min_codex_remaining_percent" != "0.0" ]]; then
  budget_arg=(--min-codex-remaining-percent "$min_codex_remaining_percent")
  if [[ -n "$codex_usage_status_file" ]]; then
    budget_arg+=(--codex-usage-status-file "$codex_usage_status_file")
  fi
  if [[ -n "$codex_usage_check_command" ]]; then
    budget_arg+=(--codex-usage-check-command "$codex_usage_check_command")
  fi
  if [[ "$codex_usage_allow_unknown" == "1" ]]; then
    budget_arg+=(--codex-usage-allow-unknown)
  fi
fi
budget_arg_text=""
if [[ "${#budget_arg[@]}" -gt 0 ]]; then
  printf -v budget_arg_text "%q " "${budget_arg[@]}"
fi

run_script="$work_dir/${session}.run.sh"
log_dir="$work_dir/logs"
mkdir -p "$work_dir" "$log_dir"

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
mkdir -p '$log_dir'

pids=()
for i in \$(seq 1 '$workers'); do
  worker_id="\$(printf 'overlay-%02d' "\$i")"
  (
    while true; do
      set +e
      python -u scripts/interlinear/codex_incremental_overlay_worker.py \
        --global-manifest '$global_manifest' \
        --work-dir '$work_dir' \
        --worker-id "\$worker_id" \
        --model '$model' \
        --reasoning '$reasoning' \
        --max-chunks '$max_chunks_per_worker' \
        --codex-timeout-seconds '$codex_timeout_seconds' \
        $budget_arg_text \
        ${include_waiting_arg[*]} \
        ${retry_failed_arg[*]}
      rc="\$?"
      set -e
      if [[ "\$rc" == "86" ]]; then
        echo "\$worker_id: usage limit; sleeping $usage_limit_sleep_seconds seconds before retry" >&2
        sleep '$usage_limit_sleep_seconds'
        continue
      fi
      exit "\$rc"
    done
  ) > "$log_dir/\$worker_id.log" 2>&1 &
  pids+=("\$!")
done

while true; do
  python scripts/interlinear/report_incremental_overlay_progress.py --global-manifest '$global_manifest'
  running=0
  for pid in "\${pids[@]}"; do
    if kill -0 "\$pid" 2>/dev/null; then
      running=\$((running + 1))
    fi
  done
  if [[ "\$running" -eq 0 ]]; then
    break
  fi
  sleep 300
done

status=0
for pid in "\${pids[@]}"; do
  if ! wait "\$pid"; then
    status=1
  fi
done
python scripts/interlinear/report_incremental_overlay_progress.py --global-manifest '$global_manifest'
exit "\$status"
EOF

chmod +x "$run_script"
tmux new-session -d -s "$session" -n overlays "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "workers: $workers"
echo "model: $model"
echo "reasoning: $reasoning"
echo "max_chunks_per_worker: $max_chunks_per_worker"
echo "min_codex_remaining_percent: $min_codex_remaining_percent"
echo "codex_usage_status_file: $codex_usage_status_file"
echo "codex_usage_check_command: $codex_usage_check_command"
echo "codex_usage_allow_unknown: $codex_usage_allow_unknown"
echo "work_dir: $work_dir"
echo "global_manifest: $global_manifest"
echo "run_script: $run_script"
