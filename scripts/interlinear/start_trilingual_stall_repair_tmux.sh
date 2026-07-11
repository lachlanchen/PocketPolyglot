#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/start_trilingual_stall_repair_tmux.sh <book-id> <writer-session> [repair-session]

Start a lightweight tmux companion for a trilingual writer. It only repairs a
failed chunk when that failed chunk is the first missing manifest item blocking
ordered merge progress.

Environment:
  MODEL=gpt-5.5
  REASONING=medium
  CODEX_TIMEOUT_SECONDS=7200
  REPAIR_SLEEP_SECONDS=300
  WORKER_SCRIPT=scripts/interlinear/codex_trilingual_plain_json_worker.py
  CODEX_EXEC_IGNORE_USER_CONFIG=0
  CODEX_EXEC_IGNORE_RULES=0
  CODEX_EXEC_DISABLE_FEATURES=
  REPAIR_USAGE_LIMIT_MAX_WAIT_SECONDS=900
USAGE
}

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="$1"
writer_session="$2"
session="${3:-zhjpbook-${book_id}-trilingual-repair}"
plan="books/$book_id/book-plan.json"
if [[ ! -f "$plan" ]]; then
  echo "Missing book plan: $plan" >&2
  exit 1
fi

if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux session already exists: $session" >&2
  exit 1
fi

chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
manifest="$(jq -r '.chunks_manifest' "$plan")"
raw_chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-medium}"
codex_timeout_seconds="${CODEX_TIMEOUT_SECONDS:-7200}"
repair_sleep_seconds="${REPAIR_SLEEP_SECONDS:-300}"
worker_script="${WORKER_SCRIPT:-scripts/interlinear/codex_trilingual_plain_json_worker.py}"
codex_exec_ignore_user_config="${CODEX_EXEC_IGNORE_USER_CONFIG:-0}"
codex_exec_ignore_rules="${CODEX_EXEC_IGNORE_RULES:-0}"
codex_exec_disable_features="${CODEX_EXEC_DISABLE_FEATURES:-}"
repair_usage_limit_max_wait_seconds="${REPAIR_USAGE_LIMIT_MAX_WAIT_SECONDS:-900}"

work_root="books/$book_id/work/trilingual/stall-repair"
candidate_dir="books/$book_id/work/trilingual/parallel-json/candidates"
merged_dir="books/$book_id/work/trilingual/parallel-json/merged"
log_dir="books/$book_id/work/logs"
run_script="$work_root/${session}.run.sh"
mkdir -p "$work_root" "$log_dir"

cat > "$run_script" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd '$root'
export CODEX_EXEC_IGNORE_USER_CONFIG='$codex_exec_ignore_user_config'
export CODEX_EXEC_IGNORE_RULES='$codex_exec_ignore_rules'
export CODEX_EXEC_DISABLE_FEATURES='$codex_exec_disable_features'
export CODEX_USAGE_LIMIT_MAX_WAIT_SECONDS='$repair_usage_limit_max_wait_seconds'

merge_once() {
  python scripts/interlinear/merge_trilingual_json_candidates.py \\
    --chunks-jsonl '$chunks_jsonl' \\
    --candidate-dir '$candidate_dir' \\
    --canonical-dir '$raw_chunk_dir' \\
    --merged-dir '$merged_dir'
  if find '$raw_chunk_dir' -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
    python scripts/interlinear/backfill_trilingual_grammar_roles.py \\
      --chunk-dir '$raw_chunk_dir' \\
      --chunks-jsonl '$chunks_jsonl' \\
      --overwrite-collapsed
  fi
}

first_failed_blocker() {
  python - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path('$manifest').read_text(encoding='utf-8'))
chunk_dir = Path('$raw_chunk_dir')
failed_dir = Path('$candidate_dir') / 'failed'
accepted_dir = Path('$candidate_dir') / 'accepted'

for index, item in enumerate(manifest.get('chunks', []), start=1):
    chunk_id = item['chunk_id']
    if (chunk_dir / f'{chunk_id}.json').exists():
        continue
    if (accepted_dir / f'{chunk_id}.json').exists():
        continue
    if (failed_dir / f'{chunk_id}.json').exists():
        print(index, chunk_id)
    break
PY
}

while tmux has-session -t '=$writer_session' 2>/dev/null; do
  echo "repair_check at \$(date -Is)"
  merge_once || true
  python scripts/interlinear/report_trilingual_progress.py --manifest '$manifest' --chunk-dir '$raw_chunk_dir' || true
  blocker="\$(first_failed_blocker || true)"
  if [[ -n "\$blocker" ]]; then
    index="\${blocker%% *}"
    chunk_id="\${blocker#* }"
    echo "repairing_failed_blocker index=\$index chunk=\$chunk_id"
    python -u '$worker_script' \\
      --chunks-jsonl '$chunks_jsonl' \\
      --canonical-dir '$raw_chunk_dir' \\
      --candidate-dir '$candidate_dir' \\
      --work-dir '$work_root/worker' \\
      --worker-id 'stall-repair' \\
      --model '$model' \\
      --reasoning '$reasoning' \\
      --start-index "\$index" \\
      --end-index "\$index" \\
      --max-chunks 1 \\
      --codex-timeout-seconds '$codex_timeout_seconds' \\
      --retries 6 \\
      --retry-failed \\
      --failed-retry-age-seconds 0 || true
    merge_once || true
    python scripts/interlinear/report_trilingual_progress.py --manifest '$manifest' --chunk-dir '$raw_chunk_dir' || true
  fi
  sleep '$repair_sleep_seconds'
done

echo "writer_session_finished=$writer_session"
merge_once || true
python scripts/interlinear/report_trilingual_progress.py --manifest '$manifest' --chunk-dir '$raw_chunk_dir' || true
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n stall-repair "bash '$run_script' 2>&1 | tee '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux: $session"
echo "book_id: $book_id"
echo "writer_session: $writer_session"
echo "codex_exec_ignore_user_config: $codex_exec_ignore_user_config"
echo "codex_exec_ignore_rules: $codex_exec_ignore_rules"
echo "codex_exec_disable_features: $codex_exec_disable_features"
echo "run_script: $run_script"
