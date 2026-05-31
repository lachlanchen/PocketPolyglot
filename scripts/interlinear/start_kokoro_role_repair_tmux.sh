#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

session="${1:-zhjpbook-role-repair}"
start_index="${START_INDEX:-1}"
end_index="${END_INDEX:-25}"
max_chunks="${MAX_CHUNKS:-0}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-xhigh}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
resume_after_repair="${RESUME_AFTER_REPAIR:-1}"
resume_start_index="${RESUME_START_INDEX:-26}"
resume_mode="${RESUME_MODE:-parallel-json}"
resume_workers="${RESUME_WORKERS:-10}"
work_dir="books/kokoro/work/bilingual/grammar-role-repair"
log_dir="books/kokoro/work/logs"
mkdir -p "$log_dir" "$work_dir"
log_path="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"
run_script="$work_dir/${session}.run.sh"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

resume_cmd="true"
if [[ "$resume_after_repair" == "1" ]]; then
  if [[ "$resume_mode" == "parallel-json" ]]; then
    resume_cmd="START_INDEX='$resume_start_index' WORKERS='$resume_workers' bash scripts/interlinear/start_kokoro_parallel_json_tmux.sh zhjpbook-parallel-json"
  else
    resume_cmd="RECHUNK=0 START_INDEX='$resume_start_index' bash scripts/interlinear/start_kokoro_repair_tmux.sh zhjpbook-repair"
  fi
fi

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -o pipefail
cd '$root' &&
python -u scripts/interlinear/codex_grammar_role_repair_worker.py \
  --manifest books/kokoro/work/bilingual/chunks/manifest.json \
  --chunks-jsonl books/kokoro/work/bilingual/chunks/chunks.jsonl \
  --chunk-dir books/kokoro/work/bilingual/interlinear/chunks \
  --work-dir '$work_dir' \
  --model '$model' \
  --reasoning '$reasoning' \
  --start-index '$start_index' \
  --end-index '$end_index' \
  --max-chunks '$max_chunks' \
  --codex-timeout-seconds '$codex_timeout_seconds' \
  --retries 3 \
  --after-chunk-command 'bash scripts/interlinear/compile_kokoro_both_previews.sh' \
  2>&1 | tee '$log_path'
status=\${PIPESTATUS[0]}
if [[ \$status -eq 0 ]]; then
  $resume_cmd
fi
exit \$status
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n role-repair "bash '$run_script'"

echo "tmux: $session"
echo "log: $log_path"
echo "run_script: $run_script"
echo "start_index: $start_index"
echo "end_index: $end_index"
echo "max_chunks: $max_chunks"
echo "codex_timeout_seconds: $codex_timeout_seconds"
echo "resume_after_repair: $resume_after_repair"
echo "resume_start_index: $resume_start_index"
echo "resume_mode: $resume_mode"
echo "resume_workers: $resume_workers"
