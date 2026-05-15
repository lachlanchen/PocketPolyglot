#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

monitor_session="${MONITOR_SESSION:-zhjpbook-pipeline-monitor}"
worker_session="${WORKER_SESSION:-zhjpbook-parallel-json}"
interval_seconds="${INTERVAL_SECONDS:-1800}"
stall_seconds="${STALL_SECONDS:-3600}"
workers="${WORKERS:-10}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-xhigh}"
merge_interval="${MERGE_INTERVAL:-180}"
state_dir="books/kokoro/work/monitor"
state_file="$state_dir/kokoro-monitor.state"
lock_dir="$state_dir/repair.lock"
script_path="$root/scripts/interlinear/monitor_kokoro_pipeline_tmux.sh"

mkdir -p "$state_dir"

if [[ "${1:-}" != "--run" ]]; then
  if tmux has-session -t "$monitor_session" 2>/dev/null; then
    echo "tmux monitor already exists: $monitor_session"
    exit 0
  fi
  log="$state_dir/${monitor_session}_$(date +%Y%m%d_%H%M%S).log"
  tmux new-session -d -s "$monitor_session" -n monitor \
    "MONITOR_SESSION='$monitor_session' WORKER_SESSION='$worker_session' INTERVAL_SECONDS='$interval_seconds' STALL_SECONDS='$stall_seconds' WORKERS='$workers' MODEL='$model' REASONING='$reasoning' MERGE_INTERVAL='$merge_interval' bash '$script_path' --run 2>&1 | tee -a '$log'"
  echo "tmux monitor: $monitor_session"
  echo "worker session: $worker_session"
  echo "interval_seconds: $interval_seconds"
  echo "stall_seconds: $stall_seconds"
  echo "log: $log"
  exit 0
fi

progress_report() {
  python scripts/interlinear/report_interlinear_progress.py \
    --manifest books/kokoro/work/bilingual/chunks/manifest.json \
    --chunk-dir books/kokoro/work/bilingual/interlinear/chunks
}

progress_value() {
  awk -F= -v key="$1" '$1 == key {print $2}' <<<"$2"
}

progress_is_complete() {
  local progress="$1"
  local manifest_chunks valid_chunks stale_chunks missing_chunks first_missing
  manifest_chunks="$(progress_value manifest_chunks "$progress")"
  valid_chunks="$(progress_value valid_chunks "$progress")"
  stale_chunks="$(progress_value stale_chunks "$progress")"
  missing_chunks="$(progress_value missing_chunks "$progress")"
  first_missing="$(progress_value first_missing "$progress")"

  [[ -n "$manifest_chunks" ]] \
    && [[ "$manifest_chunks" != "0" ]] \
    && [[ "$manifest_chunks" == "$valid_chunks" ]] \
    && [[ "${stale_chunks:-}" == "0" ]] \
    && [[ "${missing_chunks:-}" == "0" ]] \
    && [[ -z "$first_missing" ]]
}

chunk_number() {
  local chunk_id="$1"
  local n="${chunk_id##*-}"
  n="$(sed 's/^0*//' <<<"$n")"
  if [[ -z "$n" ]]; then
    n=0
  fi
  echo "$n"
}

latest_run_log() {
  find books/kokoro/work/logs -maxdepth 1 -type f -name "${worker_session}_*.log" \
    -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
}

latest_mtime() {
  local latest
  latest="$(find \
    books/kokoro/work/bilingual/parallel-json/logs \
    books/kokoro/work/bilingual/review-backfix/logs \
    books/kokoro/work/bilingual/parallel-json/candidates/accepted \
    books/kokoro/work/bilingual/interlinear/chunks \
    -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1)"
  printf '%s' "${latest:-0}"
}

accepted_count() {
  find books/kokoro/work/bilingual/parallel-json/candidates/accepted \
    -maxdepth 1 -name 'kokoro-chunk-*.json' 2>/dev/null | wc -l | tr -d ' '
}

uncommitted_chunk_count() {
  git status --short -- books/kokoro/work/bilingual/interlinear/chunks \
    | awk '/kokoro-chunk-[0-9]+\.json/ {count++} END {print count + 0}'
}

write_snapshot() {
  local reason="$1"
  local snapshot="$state_dir/snapshot_$(date +%Y%m%d_%H%M%S).txt"
  {
    echo "reason=$reason"
    echo "timestamp=$(date -Is)"
    echo "root=$root"
    echo "monitor_session=$monitor_session"
    echo "worker_session=$worker_session"
    echo
    echo "== progress =="
    progress_report || true
    echo
    echo "== pdf pages =="
    for pdf in "build/interlinear-block/心（こころ）.pdf" "build/interlinear-jp-main/こころ（心）.pdf"; do
      if [[ -f "$pdf" ]]; then
        printf '%s ' "$pdf"
        pdfinfo "$pdf" 2>/dev/null | awk '/^Pages:/ {print $2}'
      else
        echo "missing $pdf"
      fi
    done
    echo
    echo "== git =="
    git log --oneline -8 || true
    git status --short | head -160 || true
    echo
    echo "== tmux =="
    tmux ls || true
    echo
    echo "== active project processes =="
    ps -eo pid,ppid,stat,etime,cmd \
      | rg 'codex_bilingual_parallel_json_worker|merge_parallel_json_candidates|review_compile_kokoro_merged|review_backfix_interlinear_chunks|codex exec --cd .*/ZhJpBook|xelatex|commit_kokoro' \
      | rg -v 'rg ' || true
    echo
    echo "== candidate counts =="
    printf 'accepted_candidates='
    accepted_count
    echo "claims:"
    find books/kokoro/work/bilingual/parallel-json/candidates/claims \
      -mindepth 1 -maxdepth 1 -type d -printf '%TY-%Tm-%Td %TH:%TM:%TS %f\n' 2>/dev/null | sort || true
    echo
    echo "== latest run log =="
    local latest_log
    latest_log="$(latest_run_log)"
    if [[ -n "$latest_log" ]]; then
      echo "$latest_log"
      tail -220 "$latest_log" || true
    fi
    echo
    echo "== worker log tails =="
    for f in books/kokoro/work/bilingual/parallel-json/logs/worker-*.log; do
      [[ -f "$f" ]] || continue
      echo "-- $f --"
      tail -40 "$f" || true
    done
    echo
    echo "== review state tail =="
    python - <<'PY' || true
import json
from pathlib import Path
p = Path("books/kokoro/work/bilingual/review-backfix-state.json")
if p.exists():
    data = json.loads(p.read_text(encoding="utf-8"))
    for chunk_id, item in sorted(data.get("chunks", {}).items())[-80:]:
        print(chunk_id, item.get("status"), "issues=", item.get("issue_count", item.get("initial_issue_count")), "attempt=", item.get("attempt"), "time=", item.get("reviewed_at"))
PY
  } >"$snapshot"
  echo "$snapshot"
}

run_repair_agent() {
  local reason="$1"
  if ! mkdir "$lock_dir" 2>/dev/null; then
    echo "repair already running: $lock_dir"
    return 0
  fi
  trap 'rm -rf "$lock_dir"' RETURN

  local snapshot prompt message latest_log
  snapshot="$(write_snapshot "$reason")"
  prompt="$state_dir/repair_prompt_$(date +%Y%m%d_%H%M%S).md"
  message="$state_dir/repair_message_$(date +%Y%m%d_%H%M%S).md"
  latest_log="$(latest_run_log)"

  cat >"$prompt" <<PROMPT
You are Codex supervising /home/lachlan/ProjectsLFS/ZhJpBook.

Reason this repair monitor invoked you:
$reason

Project background:
- The goal is a complete, robust Kokoro Chinese/Japanese interlinear pocket book.
- Chinese-main and Japanese-main PDFs must both compile.
- JSON is generated chunk by chunk from books/kokoro/work/bilingual/chunks/chunks.jsonl.
- Canonical chunks live in books/kokoro/work/bilingual/interlinear/chunks.
- Accepted parallel candidates live in books/kokoro/work/bilingual/parallel-json/candidates/accepted.
- The ordered merge must not skip chunks. Use the current canonical/candidate artifacts; do not restart from zero.
- Review/backfix must catch missing text, wrong Japanese source, bad pinyin/furigana, overlong lines, broken sentence alignment, and one-color grammar role collapse.
- sources/ is intentionally ignored. Do not add original source files to git.
- Do not revert user changes. Do not run git reset --hard or destructive checkout.
- If you edit code, commit that code fix separately.
- After progress artifacts/PDFs change, run the normal progress commit.
- Always leave the pipeline running again unless the book is complete or a real blocker remains.

Expected recovery workflow:
1. Inspect the snapshot below, git status, latest run log, review logs, worker logs, and claims.
2. If a review failed because the reviewer logic is too strict, patch the reviewer narrowly, validate the failing chunk, and commit the code fix.
3. If a repaired candidate already passes, promote it into the canonical chunk file rather than asking the model to redo it.
4. If there is an uncommitted contiguous canonical batch, run:
   ZHJPBOOK_MERGED_CHUNKS="<chunk ids>" MODEL=gpt-5.5 REASONING=xhigh REVIEW_RETRIES=2 bash scripts/interlinear/review_compile_kokoro_merged.sh
5. If no project worker processes are active, stale claim directories may be removed before restarting.
6. Resume with:
   START_INDEX=<first missing chunk number> WORKERS=10 MERGE_INTERVAL=180 MODEL=gpt-5.5 REASONING=xhigh bash scripts/interlinear/start_kokoro_parallel_json_tmux.sh zhjpbook-parallel-json
7. Verify with report_interlinear_progress.py, pdfinfo for both PDFs, git log/status, and tmux/worker process checks.

Useful latest run log:
${latest_log:-none}

Snapshot:
\`\`\`
$(cat "$snapshot")
\`\`\`
PROMPT

  echo "starting Codex repair agent: $message"
  codex exec --cd "$root" -m "$model" -c model_reasoning_effort="$reasoning" \
    --dangerously-bypass-approvals-and-sandbox \
    --output-last-message "$message" - <"$prompt" || true
}

maybe_restart_worker() {
  local progress first_missing start_index
  progress="$(progress_report || true)"
  first_missing="$(progress_value first_missing "$progress")"
  if [[ -z "$first_missing" ]]; then
    echo "no first_missing; not restarting"
    return 0
  fi
  if tmux has-session -t "$worker_session" 2>/dev/null; then
    echo "worker session already active"
    return 0
  fi
  if [[ "$(uncommitted_chunk_count)" -gt 0 ]]; then
    echo "uncommitted canonical chunks exist; leaving restart decision to repair agent"
    return 0
  fi
  start_index="$(chunk_number "$first_missing")"
  find books/kokoro/work/bilingual/parallel-json/candidates/claims \
    -mindepth 1 -maxdepth 1 -type d -name 'kokoro-chunk-*' -exec rm -rf {} + 2>/dev/null || true
  echo "restarting worker session from $first_missing index $start_index"
  START_INDEX="$start_index" WORKERS="$workers" MERGE_INTERVAL="$merge_interval" MODEL="$model" REASONING="$reasoning" \
    bash scripts/interlinear/start_kokoro_parallel_json_tmux.sh "$worker_session" || true
}

echo "monitor started at $(date -Is)"
echo "interval_seconds=$interval_seconds stall_seconds=$stall_seconds worker_session=$worker_session"

while true; do
  now="$(date +%s)"
  progress="$(progress_report || true)"
  last_valid="$(progress_value last_valid "$progress")"
  first_missing="$(progress_value first_missing "$progress")"
  accepted="$(accepted_count)"
  active_mtime="$(latest_mtime)"
  head_commit="$(git rev-parse --short HEAD 2>/dev/null || true)"
  marker="${last_valid:-none}|${first_missing:-none}|$accepted|$active_mtime|$head_commit"
  previous_marker=""
  previous_since="$now"
  if [[ -f "$state_file" ]]; then
    # shellcheck disable=SC1090
    source "$state_file" || true
  fi

  if [[ "$marker" != "${previous_marker:-}" ]]; then
    previous_marker="$marker"
    previous_since="$now"
    {
      printf 'previous_marker=%q\n' "$previous_marker"
      printf 'previous_since=%q\n' "$previous_since"
    } >"$state_file"
  fi

  unchanged_for=$((now - previous_since))
  echo
  echo "===== $(date -Is) ====="
  echo "$progress"
  echo "accepted_candidates=$accepted"
  echo "latest_commit=$(git log -1 --oneline 2>/dev/null || true)"
  echo "marker=$marker"
  echo "unchanged_for=${unchanged_for}s"
  if progress_is_complete "$progress"; then
    echo "book_complete=1"
    echo "monitor exiting; no worker restart needed"
    exit 0
  fi

  if tmux has-session -t "$worker_session" 2>/dev/null; then
    echo "worker_session=active"
  else
    echo "worker_session=missing"
    run_repair_agent "worker tmux session $worker_session is missing"
    maybe_restart_worker
  fi

  if [[ "$unchanged_for" -ge "$stall_seconds" ]]; then
    run_repair_agent "pipeline marker unchanged for ${unchanged_for}s, exceeding stall threshold ${stall_seconds}s"
  fi

  sleep "$interval_seconds"
done
