#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

manifest="${MANIFEST:-data/source-plan/japanese-literature-batch.json}"
workers="${WORKERS:-10}"
review_workers="${REVIEW_WORKERS:-6}"
monitor="${MONITOR:-1}"
monitor_interval="${MONITOR_INTERVAL_SECONDS:-1800}"
stall_seconds="${STALL_SECONDS:-7200}"

if [[ ! -f "$manifest" ]]; then
  echo "Missing manifest: $manifest" >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  book_ids=("$@")
elif [[ -n "${BOOK_IDS:-}" ]]; then
  read -r -a book_ids <<< "$BOOK_IDS"
else
  mapfile -t book_ids < <(python - "$manifest" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for book in data.get("books", []):
    if book.get("status") == "launchable" and book.get("source_language") == "zh":
        print(book["book_id"])
PY
)
fi

if [[ "${#book_ids[@]}" -eq 0 ]]; then
  echo "No launchable book ids selected." >&2
  exit 1
fi

for book_id in "${book_ids[@]}"; do
  session="zhjpbook-${book_id}-json"
  if tmux has-session -t "$session" 2>/dev/null; then
    echo "skip existing tmux session: $session"
  else
    WORKERS="$workers" REVIEW_WORKERS="$review_workers" \
      bash scripts/interlinear/start_prepared_book_parallel_json_tmux.sh "$book_id" "$session"
  fi

  if [[ "$monitor" == "1" ]]; then
    BOOK_ID="$book_id" \
      WORKER_SESSION="$session" \
      REVIEW_SESSION="$session" \
      MONITOR_SESSION="zhjpbook-${book_id}-monitor" \
      INTERVAL_SECONDS="$monitor_interval" \
      STALL_SECONDS="$stall_seconds" \
      START_COMMAND="WORKERS=$workers REVIEW_WORKERS=$review_workers bash scripts/interlinear/start_prepared_book_parallel_json_tmux.sh $book_id $session" \
      COMPILE_COMMAND="bash scripts/interlinear/compile_prepared_book_both_previews.sh $book_id" \
      bash scripts/interlinear/start_interlinear_monitor_tmux.sh "$book_id"
  fi
done
