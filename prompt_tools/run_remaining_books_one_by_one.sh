#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

check_interval="${CHECK_INTERVAL_SECONDS:-900}"
workers="${WORKERS:-10}"
model="${MODEL:-gpt-5.5}"
reasoning="${REASONING:-low}"
merge_interval="${MERGE_INTERVAL:-120}"
compile_interval="${COMPILE_INTERVAL_SECONDS:-1800}"
codex_timeout="${CODEX_TIMEOUT_SECONDS:-1800}"
prepare_max_chars="${PREPARE_MAX_CHARS:-520}"
main_layers="${MAIN_LAYERS:-wenyan}"

quadrilingual_books=(
  zhanguoce
  shishuo-xinyu
  zizhi-tongjian
)

textbook_books=(
  game-theory
  game-theory-101
  nonlinear-dynamics-and-chaos
  chaos-making-new-science
  qft-gifted-amateur
)

progress_complete() {
  local book_id="$1"
  python scripts/interlinear/report_quadrilingual_progress.py \
    --manifest "books/$book_id/work/quadrilingual/chunks/manifest.json" \
    --chunks-jsonl "books/$book_id/work/quadrilingual/chunks/chunks.jsonl" \
    --chunk-dir "books/$book_id/work/quadrilingual/interlinear/chunks"
}

prepare_quadrilingual() {
  local book_id="$1"
  case "$book_id" in
    shishuo-xinyu)
      python scripts/interlinear/prepare_shishuo_xinyu_quadrilingual.py \
        --max-chars "$prepare_max_chars"
      ;;
    *)
      python scripts/interlinear/prepare_classical_quadrilingual_task.py \
        --book-id "$book_id" \
        --max-chars "$prepare_max_chars"
      ;;
  esac
}

start_quadrilingual_if_needed() {
  local book_id="$1"
  local session="zhjpbook-${book_id}-onebyone"

  # Older manual starts used this exact session for zhanguoce; keep using it if
  # present so a queue runner can attach to in-progress work without restarting.
  if tmux has-session -t "=$session" 2>/dev/null; then
    return 0
  fi

  WORKERS="$workers" \
  MODEL="$model" \
  REASONING="$reasoning" \
  MERGE_INTERVAL="$merge_interval" \
  COMPILE_INTERVAL_SECONDS="$compile_interval" \
  CODEX_TIMEOUT_SECONDS="$codex_timeout" \
  RETRY_FAILED=1 \
  FAILED_RETRY_AGE_SECONDS=900 \
  MAIN_LAYERS="$main_layers" \
    bash scripts/interlinear/start_quadrilingual_wenyan_tmux.sh "$book_id" "$session"
}

finalize_quadrilingual() {
  local book_id="$1"
  local marker="books/$book_id/work/quadrilingual/queue/finalized-and-synced.ok"
  if [[ -f "$marker" ]]; then
    echo "finalize_skipped_already_done=$book_id marker=$marker"
    return 0
  fi

  bash scripts/interlinear/compile_quadrilingual_large_font_variant.sh \
    --book-id "$book_id" \
    --main-layer wenyan \
    --color-mode color
  bash scripts/interlinear/compile_quadrilingual_large_font_variant.sh \
    --book-id "$book_id" \
    --main-layer wenyan \
    --color-mode blackwhite

  python scripts/interlinear/export_max_language_shiji_catalog.py \
    --book "$book_id" \
    --no-readme \
    --no-manifest
  python scripts/books/refresh_lingualleaf_catalog.py
  python scripts/books/sync_max_language_book_to_nutstore.py "$book_id" || true

  mkdir -p "$(dirname "$marker")"
  date -Is > "$marker"
  echo "finalized_and_synced=$book_id marker=$marker"
}

run_quadrilingual_book() {
  local book_id="$1"
  echo "queue_start_quadrilingual=$book_id"
  local plan="books/$book_id/book-plan.json"
  local skip_marker="books/$book_id/work/quadrilingual/queue/skipped-source-prep-required.ok"
  if [[ -f "$plan" ]] && [[ ! -f "books/$book_id/work/quadrilingual/chunks/manifest.json" ]]; then
    local launchable
    launchable="$(jq -r '.launchable // false' "$plan")"
    if [[ "$launchable" != "true" ]]; then
      mkdir -p "$(dirname "$skip_marker")"
      {
        date -Is
        echo "book_id=$book_id"
        echo "reason=book plan is source-prepared only and has no runnable quadrilingual manifest"
        echo "next_step=$(jq -r '.next_step // "prepare source markdown and chunks first"' "$plan")"
      } > "$skip_marker"
      echo "queue_skip_quadrilingual=$book_id marker=$skip_marker"
      return 0
    fi
  fi
  prepare_quadrilingual "$book_id"
  while true; do
    if progress_complete "$book_id"; then
      break
    fi
    start_quadrilingual_if_needed "$book_id"
    sleep "$check_interval"
  done
  finalize_quadrilingual "$book_id"
  echo "queue_done_quadrilingual=$book_id"
}

run_textbook_book() {
  local book_id="$1"
  local marker="books/$book_id/work/exact-tex/queue/finalized.ok"
  echo "queue_start_textbook=$book_id"
  if [[ -f "$marker" ]]; then
    echo "textbook_skipped_already_done=$book_id marker=$marker"
    return 0
  fi

  python scripts/interlinear/compile_textbook_english_pocket.py \
    --book-id "$book_id" \
    --submit-missing \
    --wait \
    --download \
    --passes 2

  mkdir -p "$(dirname "$marker")"
  date -Is > "$marker"
  echo "queue_done_textbook=$book_id marker=$marker"
}

main() {
  for book_id in "${quadrilingual_books[@]}"; do
    run_quadrilingual_book "$book_id"
  done
  for book_id in "${textbook_books[@]}"; do
    run_textbook_book "$book_id"
  done
}

main "$@"
