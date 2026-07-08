#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/finalize_trilingual_book_after_complete.sh <book-id> [writer-session]

Wait until a trilingual book reaches full manifest coverage, then compile the
12 pair PDFs with ALLOW_MISSING=0 and sync those PDFs to Nutstore.

Environment:
  POLL_SECONDS=300
  COMMIT_AFTER_SYNC=0
USAGE
}

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="$1"
writer_session="${2:-}"
poll_seconds="${POLL_SECONDS:-300}"
plan="books/$book_id/book-plan.json"

if [[ ! -f "$plan" ]]; then
  echo "missing_plan=$plan" >&2
  exit 1
fi

manifest="$(jq -r '.chunks_manifest' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"

progress_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {print $2; exit}'
}

while true; do
  report="$(python scripts/interlinear/report_trilingual_progress.py --manifest "$manifest" --chunk-dir "$chunk_dir")"
  printf '%s\n' "$report"
  manifest_chunks="$(printf '%s\n' "$report" | progress_value manifest_chunks)"
  valid_chunks="$(printf '%s\n' "$report" | progress_value valid_chunks)"
  stale_chunks="$(printf '%s\n' "$report" | progress_value stale_chunks)"
  missing_chunks="$(printf '%s\n' "$report" | progress_value missing_chunks)"

  if [[ "$manifest_chunks" == "$valid_chunks" && "$missing_chunks" == "0" && "$stale_chunks" == "0" ]]; then
    echo "coverage_complete=$book_id"
    break
  fi

  if [[ -n "$writer_session" ]] && ! tmux has-session -t "=$writer_session" 2>/dev/null; then
    echo "writer_session_not_running=$writer_session incomplete=${valid_chunks}/${manifest_chunks} missing=${missing_chunks} stale=${stale_chunks}"
  fi
  sleep "$poll_seconds"
done

case "$book_id" in
  *poem*|*poetry*|ovid-art-of-love*|tagore-*|gibran-*|keats-*|wilde-*|yeats-*|shelley-*|byron-*|xu-zhimo-*|tsangyang-gyatso-*)
    python scripts/interlinear/prune_numeric_source_units.py --chunk-dir "$chunk_dir"
    python scripts/interlinear/repair_poetry_note_fragments.py --chunk-dir "$chunk_dir"
    python scripts/interlinear/sync_poetry_source_en_from_units.py --chunks-jsonl "$(jq -r '.chunks_jsonl' "$plan")" --chunk-dir "$chunk_dir"
    ;;
esac

python scripts/interlinear/backfill_trilingual_grammar_roles.py \
  --chunk-dir "$chunk_dir" \
  --chunks-jsonl "$(jq -r '.chunks_jsonl' "$plan")" \
  --overwrite-collapsed

case "$book_id" in
  *poem*|*poetry*|ovid-art-of-love*|tagore-*|gibran-*|keats-*|wilde-*|yeats-*|shelley-*|byron-*|xu-zhimo-*|tsangyang-gyatso-*)
    python scripts/interlinear/soften_collapsed_grammar_roles.py --chunk-dir "$chunk_dir"
    python scripts/interlinear/audit_trilingual_book_quality.py --chunk-dir "$chunk_dir" --max-issues 80
    ;;
esac

ALLOW_MISSING=0 bash scripts/interlinear/compile_trilingual_book_12_previews.sh "$book_id"
for color_mode in color blackwhite; do
  case "$book_id" in
    kokin-wakashu|manyoshu)
      bash scripts/interlinear/compile_trilingual_source_notes_book.sh --book-id "$book_id" --color-mode "$color_mode"
      ;;
    *)
      bash scripts/interlinear/compile_trilingual_en_notes_book.sh --book-id "$book_id" --color-mode "$color_mode"
      ;;
  esac
done
python scripts/interlinear/export_max_language_shiji_catalog.py --book "$book_id" --force-compile --force-compress --no-readme --no-manifest
python scripts/books/sync_trilingual_pair_book_to_nutstore.py "$book_id"
python scripts/books/sync_max_language_book_to_nutstore.py "$book_id"

if [[ "${COMMIT_AFTER_SYNC:-0}" == "1" ]]; then
  git add references/book-processing-status.md scripts/books/sync_trilingual_pair_book_to_nutstore.py scripts/interlinear/finalize_trilingual_book_after_complete.sh || true
  if ! git diff --cached --quiet; then
    git commit -m "Finalize $book_id trilingual export"
  fi
fi

echo "finalized=$book_id"
