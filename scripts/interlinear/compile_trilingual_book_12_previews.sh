#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/interlinear/compile_trilingual_book_12_previews.sh <book-id>

Compile the 12 standard trilingual pair PDFs from books/<book-id>/book-plan.json:
  zh-en, en-zh, zh-ja, ja-zh, ja-en, en-ja, each in color and blackwhite.

Environment:
  ALLOW_MISSING=1  build previews from available chunks (default)
  ALLOW_MISSING=0  require complete chunk coverage
USAGE
}

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

book_id="$1"
allow_missing_arg=()
if [[ "${ALLOW_MISSING:-1}" != "0" ]]; then
  allow_missing_arg=(--allow-missing)
fi

if [[ ! -f "books/$book_id/book-plan.json" ]]; then
  echo "Missing book plan: books/$book_id/book-plan.json" >&2
  exit 1
fi

plan="books/$book_id/book-plan.json"
manifest="$(jq -r '.chunks_manifest' "$plan")"
chunks_jsonl="$(jq -r '.chunks_jsonl' "$plan")"
chunk_dir="$(jq -r '.raw_chunk_dir' "$plan")"
snapshot_json="books/$book_id/work/trilingual/preview/$book_id.compile-snapshot.json"
mkdir -p "$(dirname "$snapshot_json")"

if [[ "${TRILINGUAL_BACKFILL_GRAMMAR:-1}" != "0" ]]; then
  if find "$chunk_dir" -maxdepth 1 -name '*.json' -print -quit | grep -q .; then
    python scripts/interlinear/backfill_trilingual_grammar_roles.py \
      --chunk-dir "$chunk_dir" \
      --chunks-jsonl "$chunks_jsonl" \
      --overwrite-collapsed
  fi
fi

assemble_args=(
  python scripts/interlinear/assemble_trilingual_json.py
  --manifest "$manifest"
  --chunks-jsonl "$chunks_jsonl"
  --chunk-dir "$chunk_dir"
  --output "$snapshot_json"
)
if [[ "${ALLOW_MISSING:-1}" != "0" ]]; then
  assemble_args+=(--allow-missing)
fi
"${assemble_args[@]}"
python scripts/interlinear/validate_trilingual_interlinear_json.py "$snapshot_json"

compile_one() {
  local main_lang="$1"
  local comment_lang="$2"
  local color_mode="$3"
  bash scripts/interlinear/compile_trilingual_pair_book.sh \
    --book-id "$book_id" \
    --main-lang "$main_lang" \
    --comment-lang "$comment_lang" \
    --color-mode "$color_mode" \
    --input-json "$snapshot_json" \
    "${allow_missing_arg[@]}"
}

for color_mode in color blackwhite; do
  compile_one zh en "$color_mode"
  compile_one en zh "$color_mode"
  compile_one zh ja "$color_mode"
  compile_one ja zh "$color_mode"
  compile_one ja en "$color_mode"
  compile_one en ja "$color_mode"
done
