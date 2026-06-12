#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

discover_books() {
  find books -maxdepth 2 -name book-plan.json -print | sort | while read -r plan; do
    book_id="$(jq -r '.book_id // empty' "$plan")"
    chunk_dir="$(jq -r '.raw_chunk_dir // empty' "$plan")"
    chunk_count="$(jq -r '.chunk_count // 0' "$plan")"
    has_trilingual_fields="$(jq -r '(.chunks_manifest and .chunks_jsonl and .raw_chunk_dir and .book_title_en and .book_title_zh and .book_title_ja) // false' "$plan")"
    if [[ -z "$book_id" || "$has_trilingual_fields" != "true" || -z "$chunk_dir" || "$chunk_count" == "0" ]]; then
      continue
    fi
    actual_count="$(find "$chunk_dir" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "$actual_count" == "$chunk_count" ]]; then
      printf '%s\n' "$book_id"
    fi
  done
}

books=("$@")
if [[ "${#books[@]}" -eq 0 ]]; then
  mapfile -t books < <(discover_books)
fi

if [[ "${#books[@]}" -eq 0 ]]; then
  echo "No complete trilingual books found." >&2
  exit 1
fi

for book_id in "${books[@]}"; do
  echo "== $book_id =="
  for variant in ${VARIANTS:-color blackwhite}; do
    bash scripts/interlinear/compile_trilingual_en_notes_book.sh --book-id "$book_id" --color-mode "$variant"
  done
done
