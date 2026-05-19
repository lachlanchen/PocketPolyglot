#!/usr/bin/env bash
set -euo pipefail

book="${1:-${BOOK:-sishu-jizhu-aginti}}"
session="${SESSION:-${book}-compile-watch}"
interval="${COMPILE_WATCH_INTERVAL:-900}"
min_delta="${COMPILE_WATCH_MIN_DELTA:-50}"
max_interval="${COMPILE_WATCH_MAX_INTERVAL:-3600}"
run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
log_dir="${LOG_DIR:-logs/${book}-compile-watch-${run_id}}"

mkdir -p "$log_dir"

if tmux has-session -t "$session" 2>/dev/null; then
  echo "session already exists: $session"
  echo "attach with: tmux attach -t $session"
  exit 0
fi

runfile="$log_dir/run-compile-watch.sh"
cat >"$runfile" <<SH
#!/usr/bin/env bash
set -euo pipefail
cd "$(pwd)"
echo "book=$book"
echo "session=$session"
echo "interval=$interval"
echo "min_delta=$min_delta"
echo "max_interval=$max_interval"
echo "started=\$(date -Is)"
exec python3 -u scripts/interlinear/watch_aginti_compile.py \\
  --book "$book" \\
  --interval "$interval" \\
  --min-delta "$min_delta" \\
  --max-interval "$max_interval"
SH
chmod +x "$runfile"

tmux new-session -d -s "$session" -n compile "bash '$runfile' 2>&1 | tee '$log_dir/compile-watch.log'"

echo "started session: $session"
echo "log_dir: $log_dir"
echo "attach: tmux attach -t $session"
