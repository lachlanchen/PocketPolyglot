#!/usr/bin/env bash
set -euo pipefail

book="${1:-${BOOK:-sishu-jizhu-aginti}}"
session="${SESSION:-${book}-dynamic-review}"
start_chunk="${START_CHUNK:-1}"
max_chunks="${MAX_CHUNKS:-0}"
review_rounds="${REVIEW_ROUNDS:-2}"
interval="${REVIEW_INTERVAL:-900}"
delay="${DELAY:-1}"
compile_every="${COMPILE_EVERY:-0}"
failed_only="${FAILED_ONLY:-0}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
log_dir="${LOG_DIR:-logs/${book}-dynamic-review-${run_id}}"

mkdir -p "$log_dir"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "session already exists: $session"
  echo "attach with: tmux attach -t $session"
  exit 0
fi

runfile="$log_dir/run-dynamic-review.sh"
cat >"$runfile" <<SH
#!/usr/bin/env bash
set -euo pipefail
cd "$(pwd)"
echo "book=$book"
echo "session=$session"
echo "start_chunk=$start_chunk"
echo "max_chunks=$max_chunks"
echo "review_rounds=$review_rounds"
echo "interval=$interval"
echo "compile_every=$compile_every"
echo "failed_only=$failed_only"
echo "started=\$(date -Is)"
args=(
  python3 -u scripts/interlinear/aginti_dynamic_review_chunks.py
  --book "$book"
  --start-chunk "$start_chunk"
  --max-chunks "$max_chunks"
  --review-rounds "$review_rounds"
  --delay "$delay"
  --sleep "$interval"
  --compile-every "$compile_every"
  --loop
)
case "$failed_only" in
  1|true|TRUE|yes|YES) args+=(--failed-only) ;;
esac
exec "\${args[@]}"
SH
chmod +x "$runfile"

tmux new-session -d -s "$session" -n review "bash '$runfile' 2>&1 | tee '$log_dir/dynamic-review.log'"

echo "started session: $session"
echo "log_dir: $log_dir"
echo "attach: tmux attach -t $session"
