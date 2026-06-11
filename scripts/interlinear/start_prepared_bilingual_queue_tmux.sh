#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: CURRENT_BOOK_ID=<book-id> BOOK_IDS="book-a book-b" scripts/interlinear/start_prepared_bilingual_queue_tmux.sh [session]

Run launchable prepared bilingual ZH/JP books one by one. Each book is started
with start_prepared_book_parallel_json_tmux.sh, then finalized when reviewed
chunk coverage is complete:
  - compile both directions, color and blackwhite
  - commit durable reviewed chunks through commit_prepared_book_progress.sh
  - sync final PDFs to the Nutstore LinguaLeaf/books export

Environment:
  CURRENT_BOOK_ID            current/first book id, required
  BOOK_IDS                   space-separated queued book ids, optional
  WORKERS                    writer workers, default 10
  REVIEW_WORKERS             reviewer workers, default 6
  MODEL                      model for workers, default gpt-5.5
  REASONING                  reasoning effort, default high
  RETRY_FAILED=1             retry failed chunk records
  INTERVAL_SECONDS           monitor poll interval, default 300
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

current="${CURRENT_BOOK_ID:-}"
book_ids="${BOOK_IDS:-}"
if [[ -z "$current" ]]; then
  usage >&2
  exit 1
fi

session="${1:-zhjpbook-prepared-bilingual-queue}"
if tmux has-session -t "=$session" 2>/dev/null; then
  echo "tmux prepared bilingual queue already exists: $session"
  exit 0
fi

all_books=("$current")
if [[ -n "$book_ids" ]]; then
  read -r -a queued <<< "$book_ids"
  all_books+=("${queued[@]}")
fi

log_dir="books/$current/work/bilingual/queue"
run_script="$log_dir/${session}.run.sh"
mkdir -p "$log_dir"

cat > "$run_script" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

progress_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { print $2 }'
}

book_plan_value() {
  local book_id="$1"
  local key="$2"
  jq -r "$key" "books/$book_id/book-plan.json"
}

writer_session() {
  printf 'zhjpbook-%s-json' "$1"
}

is_active() {
  local book_id="$1"
  local session
  session="$(writer_session "$book_id")"
  tmux has-session -t "=$session" 2>/dev/null
}

report_book() {
  local book_id="$1"
  local manifest reviewed_dir
  manifest="$(book_plan_value "$book_id" '.chunks_manifest')"
  reviewed_dir="$(book_plan_value "$book_id" '.reviewed_chunk_dir')"
  python scripts/interlinear/report_interlinear_progress.py \
    --manifest "$manifest" \
    --chunk-dir "$reviewed_dir" || true
}

is_complete() {
  local book_id="$1"
  local report manifest valid missing stale
  report="$(report_book "$book_id")"
  manifest="$(printf '%s\n' "$report" | progress_value manifest_chunks)"
  valid="$(printf '%s\n' "$report" | progress_value valid_chunks)"
  missing="$(printf '%s\n' "$report" | progress_value missing_chunks)"
  stale="$(printf '%s\n' "$report" | progress_value stale_chunks)"
  [[ -n "$manifest" && "$manifest" != "0" && "$manifest" == "$valid" && "$missing" == "0" && "$stale" == "0" ]]
}

start_book() {
  local book_id="$1"
  local session
  session="$(writer_session "$book_id")"
  if tmux has-session -t "=$session" 2>/dev/null; then
    echo "already_active=$book_id session=$session"
    return 0
  fi
  echo "starting=$book_id session=$session at $(date -Is)"
  WORKERS="${WORKERS:-10}" \
  REVIEW_WORKERS="${REVIEW_WORKERS:-6}" \
  MODEL="${MODEL:-gpt-5.5}" \
  REASONING="${REASONING:-high}" \
  RETRY_FAILED="${RETRY_FAILED:-1}" \
    bash scripts/interlinear/start_prepared_book_parallel_json_tmux.sh "$book_id" "$session"
}

finalize_book() {
  local book_id="$1"
  local marker
  marker="books/$book_id/work/bilingual/queue/finalized-and-synced.ok"
  if [[ -f "$marker" ]]; then
    echo "already_finalized=$book_id"
    return 0
  fi
  mkdir -p "$(dirname "$marker")"
  echo "finalizing=$book_id at $(date -Is)"
  bash scripts/interlinear/compile_prepared_book_both_previews.sh "$book_id"
  bash scripts/interlinear/commit_prepared_book_progress.sh "$book_id"
  python scripts/books/export_flat_build_pdfs.py --no-local
  date -Is > "$marker"
  echo "finalized_and_synced=$book_id at $(cat "$marker")"
}

interval="${INTERVAL_SECONDS:-300}"
books=("$@")

while true; do
  all_done=1
  for book_id in "${books[@]}"; do
    if [[ ! -f "books/$book_id/book-plan.json" ]]; then
      echo "missing_plan=$book_id"
      continue
    fi
    if [[ "$(book_plan_value "$book_id" '.launchable')" != "true" ]]; then
      echo "not_launchable=$book_id"
      continue
    fi

    echo "status=$book_id at $(date -Is)"
    report_book "$book_id"

    if is_complete "$book_id"; then
      finalize_book "$book_id"
      continue
    fi

    all_done=0
    if is_active "$book_id"; then
      echo "waiting_active=$book_id session=$(writer_session "$book_id")"
    else
      start_book "$book_id"
    fi
    break
  done

  if [[ "$all_done" == "1" ]]; then
    echo "prepared_bilingual_queue_complete=1 at $(date -Is)"
    exit 0
  fi
  sleep "$interval"
done
EOF
chmod +x "$run_script"

tmux new-session -d -s "$session" -n prepared-bilingual-queue "\
cd '$root' && \
WORKERS='${WORKERS:-10}' \
REVIEW_WORKERS='${REVIEW_WORKERS:-6}' \
MODEL='${MODEL:-gpt-5.5}' \
REASONING='${REASONING:-high}' \
RETRY_FAILED='${RETRY_FAILED:-1}' \
INTERVAL_SECONDS='${INTERVAL_SECONDS:-300}' \
bash '$run_script' ${all_books[*]} \
2>&1 | tee -a '$log_dir/${session}_$(date +%Y%m%d_%H%M%S).log'"

echo "tmux prepared bilingual queue: $session"
echo "books: ${all_books[*]}"
echo "workers: ${WORKERS:-10}"
echo "review_workers: ${REVIEW_WORKERS:-6}"
echo "model: ${MODEL:-gpt-5.5}"
echo "reasoning: ${REASONING:-high}"
echo "interval_seconds: ${INTERVAL_SECONDS:-300}"
echo "run_script: $run_script"
