#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="${BOOK_ID:-${1:-sichuan-folk-stories-vol1}}"
session="${GUARDIAN_SESSION:-zhjpbook-${book_id}-guardian}"
interval="${INTERVAL_SECONDS:-900}"
stall="${STALL_SECONDS:-3600}"
active_stall_repair="${ACTIVE_STALL_REPAIR_SECONDS:-21600}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"
sanitizer_workers="${SANITIZER_WORKERS:-4}"
compile_when_complete="${COMPILE_WHEN_COMPLETE:-1}"
log_dir="books/$book_id/work/guardian"
run_script="$log_dir/${session}.run.sh"
mkdir -p "$log_dir"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "tmux guardian already exists: $session"
  exit 0
fi

quote() {
  printf '%q' "$1"
}

guardian_args=(
  --book-id "$book_id"
  --interval-seconds "$interval"
  --stall-seconds "$stall"
  --active-stall-repair-seconds "$active_stall_repair"
  --model "$model"
  --reasoning "$reasoning"
  --sanitizer-workers "$sanitizer_workers"
  --allow-self-repair
  --once
)
[[ -n "${WORKER_SESSION:-}" ]] && guardian_args+=(--worker-session "$WORKER_SESSION")
[[ -n "${REVIEW_SESSION:-}" ]] && guardian_args+=(--review-session "$REVIEW_SESSION")
[[ -n "${SANITIZER_SESSION:-}" ]] && guardian_args+=(--sanitizer-session "$SANITIZER_SESSION")
[[ -n "${START_COMMAND:-}" ]] && guardian_args+=(--start-command "$START_COMMAND")
[[ -n "${SANITIZER_COMMAND:-}" ]] && guardian_args+=(--sanitizer-command "$SANITIZER_COMMAND")
[[ -n "${COMPILE_COMMAND:-}" ]] && guardian_args+=(--compile-command "$COMPILE_COMMAND")
[[ -n "${COMMIT_COMMAND:-}" ]] && guardian_args+=(--commit-command "$COMMIT_COMMAND")
[[ "$compile_when_complete" == "1" ]] && guardian_args+=(--compile-when-complete)

quoted_args=()
for arg in "${guardian_args[@]}"; do
  quoted_args+=("$(quote "$arg")")
done

log="$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log"
repair_session="${session}-repair"

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -u
cd $(quote "$root")

start_crash_repair() {
  local reason="\$1"
  local stamp prompt runfile repair_log
  stamp="\$(date +%Y%m%d_%H%M%S)"
  prompt="$(quote "$log_dir")/guardian-crash-\$stamp.md"
  runfile="$(quote "$log_dir")/guardian-crash-\$stamp.run.sh"
  repair_log="$(quote "$log_dir")/guardian-crash-\$stamp.log"
  if tmux has-session -t $(quote "$repair_session") 2>/dev/null; then
    echo "repair session already active: $(quote "$repair_session")"
    return 0
  fi
  cat > "\$prompt" <<PROMPT
You are a Codex maintenance agent for /home/lachlan/ProjectsLFS/ZhJpBook.

The autorepair companion shell loop detected that scripts/interlinear/self_healing_guardian.py crashed before it could supervise the book pipeline.

Book id: $book_id
Reason: \$reason
Recent companion log:
\$(tail -200 $(quote "$log") 2>/dev/null || true)

Fix the tracked pipeline scripts conservatively. Do not edit sources/. Do not delete generated work artifacts. Validate touched Python files with python -m py_compile and commit tracked fixes with a short imperative message.
PROMPT
  cat > "\$runfile" <<RUN
#!/usr/bin/env bash
set -euo pipefail
cd $(quote "$root")
codex exec --cd $(quote "$root") -m $(quote "$model") -c $(quote "model_reasoning_effort=\"$reasoning\"") --dangerously-bypass-approvals-and-sandbox - < "\$prompt" 2>&1 | tee "\$repair_log"
RUN
  chmod +x "\$runfile"
  tmux new-session -d -s $(quote "$repair_session") -n repair "bash '\$runfile'"
}

while true; do
  python -u scripts/interlinear/self_healing_guardian.py ${quoted_args[*]} 2>&1 | tee -a $(quote "$log")
  status="\${PIPESTATUS[0]}"
  if [[ "\$status" != "0" ]]; then
    echo "guardian_python_failed=\$status at \$(date -Iseconds)" | tee -a $(quote "$log")
    start_crash_repair "guardian python exited with status \$status"
  fi
  sleep $(quote "$interval")
done
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n guardian "bash '$run_script'"

echo "tmux guardian: $session"
echo "book_id: $book_id"
echo "interval_seconds: $interval"
echo "stall_seconds: $stall"
echo "active_stall_repair_seconds: $active_stall_repair"
echo "compile_when_complete: $compile_when_complete"
echo "model: $model"
echo "reasoning: $reasoning"
echo "log: $log"
echo "run_script: $run_script"
